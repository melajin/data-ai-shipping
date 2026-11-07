"""Local, CPU-only chunk adapter for TabICL's independent column batch axis.

This module intentionally has no torch dependency. It operates on the small
tensor protocol used by the pinned InferenceManager and keeps that manager's
input preparation and forward execution methods as the only execution path.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Callable, Dict, Optional, Tuple


CHUNK_COLUMNS = 16


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


def _is_tensor_like(value: Any) -> bool:
    return value is not None and hasattr(value, "shape") and callable(getattr(value, "narrow", None))


def _column_axis(feature_shape: Tuple[int, ...]) -> int:
    # ColEmbedding passes (columns,T,in_dim) or (table_batch,columns,T,group_size).
    # More leading batch dimensions, if supplied, remain intact; the last
    # leading dimension immediately before T/in_dim is the independent column axis.
    if len(feature_shape) < 3:
        raise ValueError(f"features must have (..., columns, T, in_dim) shape, got {feature_shape}")
    axis = len(feature_shape) - 3
    if axis < 0 or axis >= len(feature_shape) - 2:
        raise ValueError(f"could not identify a leading column axis in {feature_shape}")
    if feature_shape[axis] < 1 or feature_shape[-2] < 1 or feature_shape[-1] < 1:
        raise ValueError(f"features dimensions must be positive, got {feature_shape}")
    return axis


class ColumnChunkManager:
    """Wrap one configured CPU ``tf_col`` manager with fixed chunks of 16 columns."""

    def __init__(self, manager: Any, on_event: Optional[Callable[[dict], None]] = None):
        if getattr(getattr(manager, "exe_device", None), "type", None) != "cpu":
            raise ValueError("ColumnChunkManager only supports the pinned CPU execution path")
        if getattr(manager, "enc_name", None) != "tf_col":
            raise ValueError("ColumnChunkManager may wrap only the tf_col inference manager")
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
        # ColEmbedding configures the manager at each inference call and some
        # diagnostics read manager attributes. Delegate those public/private
        # attributes to this one wrapped manager; __call__ remains local here.
        manager = self.__dict__.get("manager")
        if manager is None:
            raise AttributeError(name)
        return getattr(manager, name)

    def configure(self, *args: Any, **kwargs: Any) -> Any:
        result = self.manager.configure(*args, **kwargs)
        if getattr(getattr(self.manager, "exe_device", None), "type", None) != "cpu":
            raise RuntimeError("column manager was configured for a non-CPU device")
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
            return self.original_call(forward_fn, inputs, auto_batch=auto_batch, output_repeat=output_repeat)

        # On non-CPU devices the original pinned manager retains full control.
        if getattr(getattr(self.manager, "exe_device", None), "type", None) != "cpu":
            return self.original_call(forward_fn, inputs, auto_batch=auto_batch, output_repeat=output_repeat)

        if not hasattr(inputs, "items") or not inputs:
            raise ValueError("inputs must be a non-empty ordered mapping")
        if next(iter(inputs)) != "features" or "features" not in inputs:
            raise ValueError("the first manager input must be 'features'")
        features = inputs["features"]
        feature_shape = _shape(features, "features")
        column_axis = _column_axis(feature_shape)
        columns = feature_shape[column_axis]
        train_size = inputs.get("train_size")
        if isinstance(train_size, bool) or not isinstance(train_size, int) or train_size < 1:
            raise ValueError("train_size must be a positive Python integer and remains shared")
        if feature_shape[-2] < train_size:
            raise ValueError("train_size exceeds the preserved sequence dimension")

        target = inputs.get("y_train")
        if target is not None:
            target_shape = _shape(target, "y_train")
            expected_target_shape = feature_shape[:-2] + (train_size,)
            if target_shape != expected_target_shape:
                raise ValueError(
                    "target-aware y_train must match the feature leading axes and FIT sequence; "
                    f"expected {expected_target_shape}, got {target_shape}"
                )

        # The pinned CPU path ignores output_repeat for allocation/offload. Keep it
        # unchanged and report it so callers can verify the shuffle optimization path.
        call_id = self.calls
        self.calls += 1
        call_record: Dict[str, Any] = {
            "event": "column_chunk_call_started",
            "call_id": call_id,
            "chunk_columns": CHUNK_COLUMNS,
            "feature_shape": list(feature_shape),
            "column_axis": column_axis,
            "column_count": columns,
            "sequence_length_preserved": feature_shape[-2],
            "feature_group_size_preserved": feature_shape[-1],
            "train_size_shared": train_size,
            "embed_with_test_shared": inputs.get("embed_with_test"),
            "output_repeat_preserved": output_repeat,
            "chunks": [],
        }
        self._emit(call_record)

        result_buffer = None
        expected_output_shape = None
        chunk_count = (columns + CHUNK_COLUMNS - 1) // CHUNK_COLUMNS
        for chunk_index, start in enumerate(range(0, columns, CHUNK_COLUMNS)):
            stop = min(start + CHUNK_COLUMNS, columns)
            width = stop - start
            chunk_inputs = OrderedDict()
            for name, value in inputs.items():
                if name == "features":
                    chunk_inputs[name] = value.narrow(column_axis, start, width)
                elif name == "y_train" and value is not None:
                    chunk_inputs[name] = value.narrow(column_axis, start, width)
                elif _is_tensor_like(value):
                    # No other tensor input is documented for this call. Reject it
                    # rather than guessing whether it is shared, broadcast, or sliced.
                    raise ValueError(f"unsupported tensor input {name!r}; source contract is unresolved")
                else:
                    chunk_inputs[name] = value

            chunk_record = {
                "chunk_index": chunk_index,
                "chunk_count": chunk_count,
                "column_start": start,
                "column_stop_exclusive": stop,
                "feature_shape": list(_shape(chunk_inputs["features"], "chunk features")),
                "target_shape": None if chunk_inputs.get("y_train") is None else list(
                    _shape(chunk_inputs["y_train"], "chunk y_train")
                ),
            }
            self._emit({"event": "column_chunk_started", "call_id": call_id, **chunk_record})

            prepared = self.manager._prepare_inputs(chunk_inputs)
            chunk_output = self.manager._run_forward(forward_fn, prepared)
            output_shape = _shape(chunk_output, "forward output")
            if (len(output_shape) != len(feature_shape)
                    or output_shape[:column_axis] != feature_shape[:column_axis]
                    or output_shape[-2] != feature_shape[-2]
                    or column_axis >= len(output_shape) or output_shape[column_axis] != width):
                raise ValueError(
                    "forward output must preserve all non-column leading axes and the sequence axis; "
                    f"expected column width {width} on axis {column_axis}, got {output_shape}"
                )
            if result_buffer is None:
                expected_output_shape = list(output_shape)
                expected_output_shape[column_axis] = columns
                result_buffer = chunk_output.new_empty(tuple(expected_output_shape))
            else:
                expected_chunk_shape = list(expected_output_shape)
                expected_chunk_shape[column_axis] = width
                if list(output_shape) != expected_chunk_shape:
                    raise ValueError(
                        f"chunk output shape changed: expected {expected_chunk_shape}, got {list(output_shape)}"
                    )

            result_buffer.narrow(column_axis, start, width).copy_(chunk_output)
            chunk_record["output_shape"] = list(output_shape)
            call_record["chunks"].append(chunk_record)
            self._emit({"event": "column_chunk_completed", "call_id": call_id, **chunk_record})

        if result_buffer is None:
            raise RuntimeError("column chunk plan produced no output")
        self._emit(
            {
                "event": "column_chunk_call_completed",
                "call_id": call_id,
                "input_shape": list(feature_shape),
                "output_shape": list(expected_output_shape),
                "column_axis": column_axis,
                "chunk_count": chunk_count,
                "max_chunk_columns": min(CHUNK_COLUMNS, columns),
                "sequence_length_preserved": feature_shape[-2],
                "train_size_shared": train_size,
                "output_repeat_preserved": output_repeat,
            }
        )
        return result_buffer


class ColumnChunkInstallation:
    """Reversible installation for only ``estimator.model_.col_embedder``."""

    def __init__(self, col_embedder: Any, original_manager: Any, adapter: ColumnChunkManager):
        self.col_embedder = col_embedder
        self.original_manager = original_manager
        self.adapter = adapter
        self.restored = False

    def restore(self) -> None:
        if self.restored:
            return
        if getattr(self.col_embedder, "inference_mgr", None) is not self.adapter:
            raise RuntimeError("column inference manager changed while adapter was installed")
        self.col_embedder.inference_mgr = self.original_manager
        self.restored = self.col_embedder.inference_mgr is self.original_manager
        if not self.restored:
            raise RuntimeError("could not restore original column inference manager")


def install_column_chunk_adapter(estimator: Any, on_event: Optional[Callable[[dict], None]] = None) -> ColumnChunkInstallation:
    """Replace only the fitted estimator's column manager, returning a restore handle."""
    model = getattr(estimator, "model_", None)
    col_embedder = getattr(model, "col_embedder", None)
    if col_embedder is None:
        raise AttributeError("fitted estimator does not expose model_.col_embedder")
    original = getattr(col_embedder, "inference_mgr", None)
    if original is None:
        raise AttributeError("model_.col_embedder has no inference_mgr")
    # InferenceManager is initialized by the estimator on CPU, then configured
    # again at each ColEmbedding call. Enforce CPU both here and after configure.
    if getattr(getattr(original, "exe_device", None), "type", None) != "cpu":
        raise ValueError("fitted column manager is not configured for CPU")
    if getattr(original, "enc_name", None) != "tf_col":
        raise ValueError("fitted manager is not the tf_col manager")
    adapter = ColumnChunkManager(original, on_event=on_event)
    col_embedder.inference_mgr = adapter
    return ColumnChunkInstallation(col_embedder, original, adapter)
