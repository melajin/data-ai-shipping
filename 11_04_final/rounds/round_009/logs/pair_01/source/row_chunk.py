"""Fixed row-batch chunking for TabICL's independent leading ROW axis.

This module does not import torch. It wraps one configured CPU ``tf_row``
InferenceManager and splits only the T axis of ``(B,T,H+C,E)`` embeddings.
Feature/class-token sequence ``H+C`` and embedding width ``E`` stay whole in
every call; ICL is outside this module and retains its complete FIT context.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Callable, Dict, Optional, Tuple


CHUNK_ROWS = 8


def _shape(value: Any, name: str) -> Tuple[int, ...]:
    shape = getattr(value, "shape", None)
    if shape is None:
        raise TypeError(f"{name} must be tensor-like and expose shape")
    try:
        result = tuple(int(dimension) for dimension in shape)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name}.shape is not a concrete integer shape") from exc
    if not result or any(dimension < 0 for dimension in result):
        raise ValueError(f"{name} has an invalid shape {result!r}")
    return result


class RowChunkManager:
    """Wrap a configured CPU ``tf_row`` manager with fixed chunks of 8 rows."""

    def __init__(self, manager: Any, on_event: Optional[Callable[[dict], None]] = None):
        if getattr(getattr(manager, "exe_device", None), "type", None) != "cpu":
            raise ValueError("RowChunkManager only supports the pinned CPU execution path")
        if getattr(manager, "enc_name", None) != "tf_row":
            raise ValueError("RowChunkManager may wrap only the tf_row inference manager")
        if not callable(getattr(manager, "_prepare_inputs", None)) or not callable(
            getattr(manager, "_run_forward", None)
        ):
            raise TypeError("pinned manager lacks _prepare_inputs or _run_forward")
        if not callable(getattr(manager, "configure", None)):
            raise TypeError("pinned manager lacks configure")
        if not callable(manager):
            raise TypeError("pinned manager is not callable")
        self.manager = manager
        self.original_call = manager
        self.on_event = on_event
        self.calls = 0

    def __getattr__(self, name: str) -> Any:
        manager = self.__dict__.get("manager")
        if manager is None:
            raise AttributeError(name)
        return getattr(manager, name)

    def configure(self, *args: Any, **kwargs: Any) -> Any:
        result = self.manager.configure(*args, **kwargs)
        if getattr(getattr(self.manager, "exe_device", None), "type", None) != "cpu":
            raise RuntimeError("row manager was configured for a non-CPU device")
        return result

    def _emit(self, event: dict) -> None:
        if self.on_event is not None:
            self.on_event(event)

    def __call__(
        self,
        forward_fn: Callable[..., Any],
        inputs: OrderedDict,
        auto_batch: bool = True,
        output_repeat: int = 1,
    ) -> Any:
        if not auto_batch:
            return self.original_call(
                forward_fn, inputs, auto_batch=auto_batch, output_repeat=output_repeat
            )
        if getattr(getattr(self.manager, "exe_device", None), "type", None) != "cpu":
            return self.original_call(
                forward_fn, inputs, auto_batch=auto_batch, output_repeat=output_repeat
            )
        if not hasattr(inputs, "items") or not inputs:
            raise ValueError("inputs must be a non-empty ordered mapping")
        if next(iter(inputs)) != "embeddings" or "embeddings" not in inputs:
            raise ValueError("the first manager input must be 'embeddings'")

        embeddings = inputs["embeddings"]
        input_shape = _shape(embeddings, "embeddings")
        if not callable(getattr(embeddings, "narrow", None)):
            raise TypeError("embeddings must support narrow() for row-axis slicing")
        if len(input_shape) != 4:
            raise ValueError(
                "ROW embeddings must have (B,T,H+C,E) shape; "
                f"got {input_shape}"
            )
        batch_size, rows, sequence_length, embedding_width = input_shape
        if min(input_shape) < 1:
            raise ValueError(f"ROW embedding dimensions must be positive, got {input_shape}")

        for name, value in inputs.items():
            if name != "embeddings" and hasattr(value, "shape"):
                raise ValueError(f"unsupported tensor input {name!r}; source contract is unresolved")

        call_id = self.calls
        self.calls += 1
        call_record: Dict[str, Any] = {
            "event": "row_chunk_call_started",
            "call_id": call_id,
            "chunk_rows": CHUNK_ROWS,
            "input_shape": list(input_shape),
            "row_axis": 1,
            "row_count": rows,
            "batch_size_preserved": batch_size,
            "feature_class_sequence_preserved": sequence_length,
            "embedding_width_preserved": embedding_width,
            "output_repeat_preserved": output_repeat,
            "chunks": [],
        }
        self._emit(call_record)

        result_buffer = None
        expected_output_shape = None
        expected_dtype = None
        expected_device = None
        chunk_count = (rows + CHUNK_ROWS - 1) // CHUNK_ROWS
        for chunk_index, start in enumerate(range(0, rows, CHUNK_ROWS)):
            stop = min(start + CHUNK_ROWS, rows)
            width = stop - start
            chunk_inputs = OrderedDict()
            for name, value in inputs.items():
                if name == "embeddings":
                    chunk_inputs[name] = value.narrow(1, start, width)
                else:
                    chunk_inputs[name] = value

            chunk_shape = _shape(chunk_inputs["embeddings"], "chunk embeddings")
            chunk_record = {
                "chunk_index": chunk_index,
                "chunk_count": chunk_count,
                "row_start": start,
                "row_stop_exclusive": stop,
                "input_shape": list(chunk_shape),
            }
            self._emit({"event": "row_chunk_started", "call_id": call_id, **chunk_record})

            prepared = self.manager._prepare_inputs(chunk_inputs)
            chunk_output = self.manager._run_forward(forward_fn, prepared)
            output_shape = _shape(chunk_output, "ROW forward output")
            output_dtype = getattr(chunk_output, "dtype", None)
            output_device = getattr(chunk_output, "device", None)
            if output_dtype is None or output_device is None:
                raise TypeError("ROW forward output must expose dtype and device")
            if (len(output_shape) != 3 or output_shape[0] != batch_size
                    or output_shape[1] != width or output_shape[2] < 1):
                raise ValueError(
                    "ROW output must have (B,chunk_T,C*E) shape and preserve its leading batch axis; "
                    f"expected B={batch_size}, chunk_T={width}, got {output_shape}"
                )
            if result_buffer is None:
                expected_output_shape = (batch_size, rows, output_shape[2])
                expected_dtype = output_dtype
                expected_device = output_device
                if not callable(getattr(chunk_output, "new_empty", None)):
                    raise TypeError("ROW forward output must support new_empty() for reconstruction")
                if not callable(getattr(chunk_output, "narrow", None)):
                    raise TypeError("ROW forward output must support narrow() for reconstruction")
                result_buffer = chunk_output.new_empty(expected_output_shape)
            else:
                if output_shape != (batch_size, width, expected_output_shape[2]):
                    raise ValueError(
                        "ROW output trailing representation width changed across chunks; "
                        f"expected {(batch_size, width, expected_output_shape[2])}, got {output_shape}"
                    )
                if output_dtype != expected_dtype or output_device != expected_device:
                    raise ValueError(
                        "ROW output dtype/device changed across chunks; "
                        f"expected {(expected_dtype, expected_device)}, got {(output_dtype, output_device)}"
                    )

            result_buffer.narrow(1, start, width).copy_(chunk_output)
            chunk_record["output_shape"] = list(output_shape)
            call_record["chunks"].append(chunk_record)
            self._emit({"event": "row_chunk_completed", "call_id": call_id, **chunk_record})

        if result_buffer is None:
            raise RuntimeError("row chunk plan produced no output")
        self._emit({
            "event": "row_chunk_call_completed",
            "call_id": call_id,
            "input_shape": list(input_shape),
            "output_shape": list(expected_output_shape),
            "row_axis": 1,
            "chunk_count": chunk_count,
            "max_chunk_rows": min(CHUNK_ROWS, rows),
            "feature_class_sequence_preserved": sequence_length,
            "embedding_width_preserved": embedding_width,
            "output_repeat_preserved": output_repeat,
        })
        return result_buffer


class RowChunkInstallation:
    """Reversible installation on only ``estimator.model_.row_interactor``."""

    def __init__(self, row_interactor: Any, original_manager: Any, adapter: RowChunkManager):
        self.row_interactor = row_interactor
        self.original_manager = original_manager
        self.adapter = adapter
        self.restored = False

    def restore(self) -> None:
        if self.restored:
            return
        if getattr(self.row_interactor, "inference_mgr", None) is not self.adapter:
            raise RuntimeError("row inference manager changed while adapter was installed")
        self.row_interactor.inference_mgr = self.original_manager
        self.restored = self.row_interactor.inference_mgr is self.original_manager
        if not self.restored:
            raise RuntimeError("could not restore original row inference manager")


def install_row_chunk_adapter(
    estimator: Any, on_event: Optional[Callable[[dict], None]] = None
) -> RowChunkInstallation:
    """Replace only a fitted estimator's ROW manager and return its restore handle."""
    model = getattr(estimator, "model_", None)
    row_interactor = getattr(model, "row_interactor", None)
    if row_interactor is None:
        raise AttributeError("fitted estimator does not expose model_.row_interactor")
    original = getattr(row_interactor, "inference_mgr", None)
    if original is None:
        raise AttributeError("model_.row_interactor has no inference_mgr")
    if getattr(getattr(original, "exe_device", None), "type", None) != "cpu":
        raise ValueError("fitted ROW manager is not configured for CPU")
    if getattr(original, "_is_configured", False) is not True:
        raise ValueError("fitted ROW manager must be configured before adapter installation")
    if getattr(original, "enc_name", None) != "tf_row":
        raise ValueError("fitted manager is not the tf_row manager")
    adapter = RowChunkManager(original, on_event=on_event)
    row_interactor.inference_mgr = adapter
    return RowChunkInstallation(row_interactor, original, adapter)
