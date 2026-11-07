"""Pure mock checks for the column adapter; importing this file does not import torch."""

from __future__ import annotations

from collections import OrderedDict
from types import SimpleNamespace
from typing import List, Optional, Sequence, Tuple

from column_chunk import CHUNK_COLUMNS, ColumnChunkManager, install_column_chunk_adapter


def _numel(shape: Sequence[int]) -> int:
    result = 1
    for size in shape:
        result *= size
    return result


class FakeTensor:
    """Small flat-storage tensor mock supporting only shape/narrow/copy/new_empty."""

    def __init__(self, shape: Sequence[int], values: Optional[Sequence[object]] = None,
                 storage: Optional[List[object]] = None, indices: Optional[List[int]] = None):
        self.shape = tuple(int(size) for size in shape)
        if storage is None:
            storage = list(values if values is not None else [None] * _numel(self.shape))
        if len(storage) != _numel(self.shape) and indices is None:
            raise ValueError("fake storage length does not match shape")
        self._storage = storage
        self._indices = list(range(len(storage))) if indices is None else indices
        if len(self._indices) != _numel(self.shape):
            raise ValueError("fake view length does not match shape")
        self.dtype = "fake-fp32"
        self.device = "cpu"

    @property
    def values(self) -> List[object]:
        return [self._storage[index] for index in self._indices]

    def narrow(self, axis: int, start: int, length: int) -> "FakeTensor":
        if axis < 0:
            axis += len(self.shape)
        if axis < 0 or axis >= len(self.shape) or start < 0 or length < 0 or start + length > self.shape[axis]:
            raise IndexError("invalid fake narrow")
        inner = _numel(self.shape[axis + 1:])
        outer = _numel(self.shape[:axis])
        selected: List[int] = []
        for outer_index in range(outer):
            base = outer_index * self.shape[axis] * inner
            lo = base + start * inner
            hi = base + (start + length) * inner
            selected.extend(self._indices[lo:hi])
        shape = list(self.shape)
        shape[axis] = length
        return FakeTensor(shape, storage=self._storage, indices=selected)

    def new_empty(self, shape: Sequence[int]) -> "FakeTensor":
        return FakeTensor(shape)

    def copy_(self, source: "FakeTensor") -> "FakeTensor":
        if len(self._indices) != len(source.values):
            raise ValueError("fake copy size mismatch")
        for destination, value in zip(self._indices, source.values):
            self._storage[destination] = value
        return self


class FakeManager:
    def __init__(self):
        self.exe_device = SimpleNamespace(type="cpu")
        self.enc_name = "tf_col"
        self.prepare_shapes = []
        self.forward_shapes = []
        self.configure_calls = []

    def configure(self, **kwargs):
        self.configure_calls.append(dict(kwargs))
        return self

    def __call__(self, forward_fn, inputs, auto_batch=True, output_repeat=1):
        return self._run_forward(forward_fn, self._prepare_inputs(inputs))

    def _prepare_inputs(self, inputs):
        self.prepare_shapes.append((inputs["features"].shape,
                                    None if inputs.get("y_train") is None else inputs["y_train"].shape))
        return inputs

    def _run_forward(self, forward_fn, inputs):
        self.forward_shapes.append(inputs["features"].shape)
        return forward_fn(**inputs)


def _make_pair(rank: int) -> Tuple[FakeTensor, FakeTensor]:
    if rank == 3:
        columns, sequence, width = 19, 3, 1
        feature_values = [float(column) for column in range(columns) for _ in range(sequence * width)]
        target_values = [float(column * 10 + step) for column in range(columns) for step in range(2)]
        return FakeTensor((columns, sequence, width), feature_values), FakeTensor((columns, 2), target_values)
    if rank == 4:
        tables, columns, sequence, width = 2, 19, 3, 1
        feature_values = [float(table * 100 + column) for table in range(tables)
                          for column in range(columns) for _ in range(sequence * width)]
        target_values = [float((table * 100 + column) * 10 + step) for table in range(tables)
                         for column in range(columns) for step in range(2)]
        return (FakeTensor((tables, columns, sequence, width), feature_values),
                FakeTensor((tables, columns, 2), target_values))
    raise ValueError(rank)


def _paired_forward(features, train_size, y_train, embed_with_test, shared_token=None):
    shape = features.shape
    column_axis = len(shape) - 3
    columns = shape[column_axis]
    tables = 1 if column_axis == 0 else shape[0]
    for table in range(tables):
        for column in range(columns):
            feature_slice = features.narrow(column_axis, column, 1).values
            target_slice = y_train.narrow(column_axis, column, 1).values
            feature_offset = table * shape[-2]
            target_offset = table * train_size
            identity = feature_slice[feature_offset]
            assert target_slice[target_offset] == identity * 10
            assert target_slice[target_offset + 1] == identity * 10 + 1
    assert train_size == 2
    assert embed_with_test is False
    return features


def test_rank3_incomplete_chunk_order_targets_and_shared_values() -> None:
    features, targets = _make_pair(3)
    shared_token = object()
    manager = FakeManager()
    events = []
    adapter = ColumnChunkManager(manager, on_event=events.append)
    inputs = OrderedDict((
        ("features", features),
        ("train_size", 2),
        ("y_train", targets),
        ("embed_with_test", False),
        ("shared_token", shared_token),
    ))
    output = adapter(_paired_forward, inputs, output_repeat=8)
    assert output.shape == features.shape
    assert output.values == features.values
    assert manager.forward_shapes == [(16, 3, 1), (3, 3, 1)]
    assert [entry[1] for entry in manager.prepare_shapes] == [(16, 2), (3, 2)]
    assert len([event for event in events if event["event"] == "column_chunk_completed"]) == 2
    completed = [event for event in events if event["event"] == "column_chunk_call_completed"]
    assert len(completed) == 1 and completed[0]["output_repeat_preserved"] == 8
    assert completed[0]["sequence_length_preserved"] == 3
    assert shared_token is inputs["shared_token"]


def test_rank4_only_column_axis_is_sliced() -> None:
    features, targets = _make_pair(4)
    manager = FakeManager()
    adapter = ColumnChunkManager(manager)
    inputs = OrderedDict((
        ("features", features),
        ("train_size", 2),
        ("y_train", targets),
        ("embed_with_test", False),
    ))
    output = adapter(_paired_forward, inputs, output_repeat=2)
    assert output.shape == (2, 19, 3, 1)
    assert output.values == features.values
    assert manager.forward_shapes == [(2, 16, 3, 1), (2, 3, 3, 1)]
    assert [entry[1] for entry in manager.prepare_shapes] == [(2, 16, 2), (2, 3, 2)]
    assert all(shape[-2] == 3 for shape in manager.forward_shapes)


def test_rejects_bad_target_axis_and_unsupported_tensor() -> None:
    features, targets = _make_pair(3)
    manager = FakeManager()
    adapter = ColumnChunkManager(manager)
    bad_target_inputs = OrderedDict((
        ("features", features),
        ("train_size", 2),
        ("y_train", FakeTensor((19, 3), [0.0] * 57)),
        ("embed_with_test", False),
    ))
    try:
        adapter(_paired_forward, bad_target_inputs)
    except ValueError as exc:
        assert "y_train" in str(exc)
    else:
        raise AssertionError("malformed target sequence was accepted")

    bad_shared_inputs = OrderedDict((
        ("features", features),
        ("train_size", 2),
        ("y_train", targets),
        ("embed_with_test", False),
        ("unknown_tensor", FakeTensor((19, 1), [0.0] * 19)),
    ))
    try:
        adapter(_paired_forward, bad_shared_inputs)
    except ValueError as exc:
        assert "unsupported tensor input" in str(exc)
    else:
        raise AssertionError("unknown tensor input was silently treated as shared")


def test_rejects_forward_output_that_changes_sequence_axis() -> None:
    features, targets = _make_pair(3)
    manager = FakeManager()
    adapter = ColumnChunkManager(manager)
    inputs = OrderedDict((
        ("features", features),
        ("train_size", 2),
        ("y_train", targets),
        ("embed_with_test", False),
    ))

    def invalid_forward(features, train_size, y_train, embed_with_test):
        return FakeTensor((features.shape[0], 2, 2), [0.0] * (features.shape[0] * 4))

    try:
        adapter(invalid_forward, inputs)
    except ValueError as exc:
        assert "sequence axis" in str(exc)
    else:
        raise AssertionError("forward output that changed T was accepted")


def test_fixed_chunk_size_is_16() -> None:
    assert CHUNK_COLUMNS == 16


def test_install_configure_call_and_restore_only_column_manager() -> None:
    features, targets = _make_pair(3)
    manager = FakeManager()
    col_embedder = SimpleNamespace(inference_mgr=manager)
    estimator = SimpleNamespace(model_=SimpleNamespace(col_embedder=col_embedder))
    original_row_manager = object()
    estimator.model_.row_manager = original_row_manager
    installation = install_column_chunk_adapter(estimator)
    try:
        wrapped = col_embedder.inference_mgr
        wrapped.configure(offload="auto", device="cpu")
        inputs = OrderedDict((
            ("features", features),
            ("train_size", 2),
            ("y_train", targets),
            ("embed_with_test", False),
        ))
        result = wrapped(_paired_forward, inputs, output_repeat=3)
        assert result.values == features.values
        assert manager.configure_calls == [{"offload": "auto", "device": "cpu"}]
        assert estimator.model_.row_manager is original_row_manager
    finally:
        installation.restore()
    assert col_embedder.inference_mgr is manager
    assert installation.restored is True


if __name__ == "__main__":
    for test in (
        test_rank3_incomplete_chunk_order_targets_and_shared_values,
        test_rank4_only_column_axis_is_sliced,
        test_rejects_bad_target_axis_and_unsupported_tensor,
        test_rejects_forward_output_that_changes_sequence_axis,
        test_fixed_chunk_size_is_16,
        test_install_configure_call_and_restore_only_column_manager,
    ):
        test()
    print("pure mock checks passed")
