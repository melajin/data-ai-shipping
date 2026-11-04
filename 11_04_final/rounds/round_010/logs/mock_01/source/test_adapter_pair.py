"""Callable pure-standard-library checks for round010 COL+ROW adapter coexistence."""

from __future__ import annotations

from collections import OrderedDict
from types import SimpleNamespace

from column_chunk import CHUNK_COLUMNS, install_column_chunk_adapter
from row_chunk import CHUNK_ROWS, RowChunkManager, install_row_chunk_adapter
from icl_observer import install_icl_call_observer, verify_full_context


def _numel(shape):
    result = 1
    for size in shape:
        result *= size
    return result


class FakeTensor:
    def __init__(self, shape, values=None, storage=None, indices=None, dtype="fake-fp32", device="cpu"):
        self.shape = tuple(int(size) for size in shape)
        self.dtype = dtype
        self.device = device
        count = _numel(self.shape)
        self._storage = (list(values) if values is not None else [None] * count) if storage is None else storage
        self._indices = list(range(count)) if indices is None else list(indices)
        if len(self._indices) != count:
            raise ValueError("fake tensor view size does not match shape")
        if storage is None and len(self._storage) != count:
            raise ValueError("fake tensor storage size does not match shape")

    @property
    def values(self):
        return [self._storage[index] for index in self._indices]

    def narrow(self, axis, start, length):
        if axis < 0:
            axis += len(self.shape)
        if axis < 0 or axis >= len(self.shape) or start < 0 or length < 0 \
                or start + length > self.shape[axis]:
            raise IndexError("invalid fake narrow")
        inner = _numel(self.shape[axis + 1:])
        outer = _numel(self.shape[:axis])
        selected = []
        for outer_index in range(outer):
            base = outer_index * self.shape[axis] * inner
            selected.extend(self._indices[base + start * inner:base + (start + length) * inner])
        shape = list(self.shape)
        shape[axis] = length
        return FakeTensor(shape, storage=self._storage, indices=selected,
                          dtype=self.dtype, device=self.device)

    def new_empty(self, shape):
        return FakeTensor(shape, dtype=self.dtype, device=self.device)

    def copy_(self, source):
        if len(self._indices) != len(source.values):
            raise ValueError("fake copy size mismatch")
        for destination, value in zip(self._indices, source.values):
            self._storage[destination] = value
        return self


class FakeManager:
    def __init__(self, enc_name="tf_row"):
        self.enc_name = enc_name
        self.exe_device = SimpleNamespace(type="cpu")
        self._is_configured = False
        self.configure_calls = []
        self.prepared_shapes = []
        self.forward_shapes = []
        self.call_arguments = []

    def configure(self, **kwargs):
        self.configure_calls.append(dict(kwargs))
        self.exe_device = SimpleNamespace(type=kwargs.get("device", "cpu"))
        self._is_configured = True
        return self

    def _prepare_inputs(self, inputs):
        self.prepared_shapes.append(inputs["embeddings"].shape)
        return inputs

    def _run_forward(self, forward_fn, inputs):
        self.forward_shapes.append(inputs["embeddings"].shape)
        return forward_fn(**inputs)

    def __call__(self, forward_fn, inputs, auto_batch=True, output_repeat=1):
        self.call_arguments.append((auto_batch, output_repeat))
        return self._run_forward(forward_fn, self._prepare_inputs(inputs))


def _make_embeddings():
    batch, rows, sequence, width = 2, 19, 3, 2
    values = [
        float(table * 10000 + row * 100 + seq * 10 + channel)
        for table in range(batch)
        for row in range(rows)
        for seq in range(sequence)
        for channel in range(width)
    ]
    return FakeTensor((batch, rows, sequence, width), values)


def _aggregate(embeddings, shared_marker=None):
    assert shared_marker is SHARED_MARKER
    batch, rows, sequence, width = embeddings.shape
    output = []
    values = embeddings.values
    for table in range(batch):
        for row in range(rows):
            start = (table * rows + row) * sequence * width
            total = sum(values[start:start + sequence * width])
            output.extend((total, total + 1.0))
    return FakeTensor((batch, rows, 2), output)


SHARED_MARKER = object()
CONFIG = {"device": "cpu", "use_amp": False, "use_fa3": False, "offload": False}


def test_fixed_chunk_order_shape_config_and_output_repeat():
    manager = FakeManager()
    embeddings = _make_embeddings()
    input_before = embeddings.values
    interactor = SimpleNamespace(inference_mgr=manager)
    estimator = SimpleNamespace(model_=SimpleNamespace(row_interactor=interactor))
    manager.configure(**CONFIG)  # Baseline prediction configures the original manager first.
    events = []
    installation = install_row_chunk_adapter(estimator, on_event=events.append)
    inputs = OrderedDict((
        ("embeddings", embeddings),
        ("shared_marker", SHARED_MARKER),
    ))
    try:
        adapter = interactor.inference_mgr
        adapter.configure(**CONFIG)
        output = adapter(_aggregate, inputs, auto_batch=True, output_repeat=4)
        assert output.shape == (2, 19, 2)
        assert output.values == _aggregate(embeddings, SHARED_MARKER).values
        assert embeddings.values == input_before
        assert inputs["shared_marker"] is SHARED_MARKER
        assert manager.configure_calls == [CONFIG, CONFIG]
        assert manager.prepared_shapes == [(2, 8, 3, 2), (2, 8, 3, 2), (2, 3, 3, 2)]
        assert manager.forward_shapes == manager.prepared_shapes
        started = [event for event in events if event["event"] == "row_chunk_started"]
        completed = [event for event in events if event["event"] == "row_chunk_completed"]
        assert [(event["row_start"], event["row_stop_exclusive"]) for event in started] == [
            (0, 8), (8, 16), (16, 19)
        ]
        assert [(event["row_start"], event["row_stop_exclusive"]) for event in completed] == [
            (0, 8), (8, 16), (16, 19)
        ]
        summary = [event for event in events if event["event"] == "row_chunk_call_completed"]
        assert len(summary) == 1
        assert summary[0]["output_repeat_preserved"] == 4
        assert summary[0]["feature_class_sequence_preserved"] == 3
        assert summary[0]["embedding_width_preserved"] == 2
        assert interactor.inference_mgr is installation.adapter
    finally:
        installation.restore()
    assert interactor.inference_mgr is manager
    assert installation.restored is True
    assert CHUNK_ROWS == 8


def test_non_auto_batch_forwards_original_arguments():
    manager = FakeManager()
    manager.configure(**CONFIG)
    adapter = RowChunkManager(manager)
    embeddings = _make_embeddings()
    result = adapter(_aggregate, OrderedDict((("embeddings", embeddings),
                                               ("shared_marker", SHARED_MARKER))),
                     auto_batch=False, output_repeat=7)
    assert result.shape == (2, 19, 2)
    assert manager.call_arguments == [(False, 7)]


def test_rejects_unknown_tensor_and_bad_rank():
    manager = FakeManager()
    adapter = RowChunkManager(manager)
    embeddings = _make_embeddings()
    bad_tensor_inputs = OrderedDict((
        ("embeddings", embeddings),
        ("unknown_tensor", FakeTensor((2, 19), [0.0] * 38)),
    ))
    try:
        adapter(_aggregate, bad_tensor_inputs)
    except ValueError as exc:
        assert "unsupported tensor input" in str(exc)
    else:
        raise AssertionError("unrecognized tensor input was silently treated as shared")

    bad_rank = OrderedDict((("embeddings", FakeTensor((19, 3, 2), [0.0] * 114)),))
    try:
        adapter(_aggregate, bad_rank)
    except ValueError as exc:
        assert "(B,T,H+C,E)" in str(exc)
    else:
        raise AssertionError("non-contract ROW input rank was accepted")


def test_rejects_bad_output_and_restores_after_forward_error():
    manager = FakeManager()
    manager.configure(**CONFIG)
    interactor = SimpleNamespace(inference_mgr=manager)
    estimator = SimpleNamespace(model_=SimpleNamespace(row_interactor=interactor))
    installation = install_row_chunk_adapter(estimator)
    try:
        adapter = interactor.inference_mgr
        inputs = OrderedDict((("embeddings", _make_embeddings()),))

        def wrong_rows(embeddings):
            return FakeTensor((2, embeddings.shape[1] + 1, 2),
                              [0.0] * (2 * (embeddings.shape[1] + 1) * 2))

        try:
            adapter(wrong_rows, inputs)
        except ValueError as exc:
            assert "ROW output" in str(exc)
        else:
            raise AssertionError("output with changed row count was accepted")

        call_count = 0

        def changed_dtype(embeddings):
            nonlocal call_count
            call_count += 1
            batch, rows, _, _ = embeddings.shape
            return FakeTensor((batch, rows, 2), [0.0] * (batch * rows * 2),
                              dtype="fake-fp64" if call_count == 2 else "fake-fp32")

        try:
            adapter(changed_dtype, inputs)
        except ValueError as exc:
            assert "dtype/device changed" in str(exc)
        else:
            raise AssertionError("changed output dtype was accepted")

        def fail_forward(embeddings):
            raise RuntimeError("injected fake forward failure")

        try:
            adapter(fail_forward, inputs)
        except RuntimeError as exc:
            assert "injected fake forward failure" in str(exc)
        else:
            raise AssertionError("injected failure did not propagate")
    finally:
        installation.restore()
    assert interactor.inference_mgr is manager
    assert installation.restored is True


class FakeColumnManager:
    def __init__(self):
        self.enc_name = "tf_col"
        self.exe_device = SimpleNamespace(type="cpu")
        self._is_configured = False
        self.configure_calls = []
        self.prepared_shapes = []
        self.forward_shapes = []

    def configure(self, **kwargs):
        self.configure_calls.append(dict(kwargs))
        self.exe_device = SimpleNamespace(type=kwargs.get("device", "cpu"))
        self._is_configured = True
        return self

    def _prepare_inputs(self, inputs):
        self.prepared_shapes.append(inputs["features"].shape)
        return inputs

    def _run_forward(self, forward_fn, inputs):
        self.forward_shapes.append(inputs["features"].shape)
        return forward_fn(**inputs)

    def __call__(self, forward_fn, inputs, auto_batch=True, output_repeat=1):
        return self._run_forward(forward_fn, self._prepare_inputs(inputs))


def _column_features():
    batch, columns, sequence, width = 2, 35, 4, 3
    values = [float(table * 100000 + column * 1000 + seq * 10 + channel)
              for table in range(batch) for column in range(columns)
              for seq in range(sequence) for channel in range(width)]
    return FakeTensor((batch, columns, sequence, width), values)


def _column_target():
    batch, columns, train_size = 2, 35, 2
    values = [float(table * 1000 + column * 10 + row)
              for table in range(batch) for column in range(columns)
              for row in range(train_size)]
    return FakeTensor((batch, columns, train_size), values)


def _column_forward(features, y_train, train_size, embed_with_test, shared_marker):
    assert train_size == 2
    assert embed_with_test is False
    assert shared_marker is SHARED_MARKER
    assert y_train.shape == (features.shape[0], features.shape[1], train_size)
    return features


def test_column_row_adapters_coexist_configure_tail_order_unknown_tensor_and_recovery():
    col_manager = FakeColumnManager()
    row_manager = FakeManager()
    col_config = {"device": "cpu", "use_amp": False, "use_fa3": False, "offload": "auto"}
    row_config = {"device": "cpu", "use_amp": False, "use_fa3": False, "offload": False}
    col_manager.configure(**col_config)
    row_manager.configure(**row_config)
    col_embedder = SimpleNamespace(inference_mgr=col_manager)
    row_interactor = SimpleNamespace(inference_mgr=row_manager)
    estimator = SimpleNamespace(model_=SimpleNamespace(col_embedder=col_embedder,
                                                       row_interactor=row_interactor))
    col_installation = install_column_chunk_adapter(estimator)
    row_installation = install_row_chunk_adapter(estimator)
    try:
        assert col_embedder.inference_mgr is col_installation.adapter
        assert row_interactor.inference_mgr is row_installation.adapter
        col_embedder.inference_mgr.configure(**col_config)
        row_interactor.inference_mgr.configure(**row_config)
        assert col_manager.configure_calls == [col_config, col_config]
        assert row_manager.configure_calls == [row_config, row_config]

        features = _column_features()
        target = _column_target()
        features_before, target_before = features.values, target.values
        col_inputs = OrderedDict((
            ("features", features), ("y_train", target), ("train_size", 2),
            ("embed_with_test", False), ("shared_marker", SHARED_MARKER),
        ))
        col_output = col_embedder.inference_mgr(_column_forward, col_inputs, output_repeat=4)
        assert col_output.shape == (2, 35, 4, 3)
        assert col_output.values == features_before
        assert target.values == target_before
        assert col_manager.prepared_shapes == [(2, 16, 4, 3), (2, 16, 4, 3), (2, 3, 4, 3)]
        assert col_manager.forward_shapes == col_manager.prepared_shapes

        col_events = col_installation.adapter
        assert col_events.calls == 1
        bad_col_inputs = OrderedDict(col_inputs)
        bad_col_inputs["unknown_tensor"] = FakeTensor((2, 35), [0.0] * 70)
        try:
            col_embedder.inference_mgr(_column_forward, bad_col_inputs)
        except ValueError as exc:
            assert "unsupported tensor input" in str(exc)
        else:
            raise AssertionError("column adapter accepted an unrecognized tensor")

        row_embeddings = _make_embeddings()
        row_inputs = OrderedDict((("embeddings", row_embeddings), ("shared_marker", SHARED_MARKER)))
        row_output = row_interactor.inference_mgr(_aggregate, row_inputs, output_repeat=5)
        assert row_output.shape == (2, 19, 2)
        assert row_output.values == _aggregate(row_embeddings, SHARED_MARKER).values
        assert row_manager.prepared_shapes == [(2, 8, 3, 2), (2, 8, 3, 2), (2, 3, 3, 2)]
        assert row_manager.forward_shapes == row_manager.prepared_shapes
        assert row_installation.adapter.calls == 1

        bad_row_inputs = OrderedDict(row_inputs)
        bad_row_inputs["unknown_tensor"] = FakeTensor((2, 19), [0.0] * 38)
        try:
            row_interactor.inference_mgr(_aggregate, bad_row_inputs)
        except ValueError as exc:
            assert "unsupported tensor input" in str(exc)
        else:
            raise AssertionError("row adapter accepted an unrecognized tensor")

        def fail_column(**kwargs):
            raise RuntimeError("injected column failure")

        def fail_row(embeddings, shared_marker=None):
            raise RuntimeError("injected row failure")

        for invoke, message in (
                (lambda: col_embedder.inference_mgr(fail_column, col_inputs), "injected column failure"),
                (lambda: row_interactor.inference_mgr(fail_row, row_inputs), "injected row failure")):
            try:
                invoke()
            except RuntimeError as exc:
                assert message in str(exc)
            else:
                raise AssertionError(f"{message} did not propagate")
    finally:
        row_installation.restore()
        col_installation.restore()
    assert col_embedder.inference_mgr is col_manager
    assert row_interactor.inference_mgr is row_manager
    assert col_installation.restored is True
    assert row_installation.restored is True
    assert CHUNK_COLUMNS == 16
    assert CHUNK_ROWS == 8


class FakeICLManager:
    def __init__(self):
        self.configure_calls = []
        self.call_args = None
        self.call_kwargs = None
        self.return_value = object()

    def configure(self, **kwargs):
        self.configure_calls.append(dict(kwargs))
        return self

    def __call__(self, *args, **kwargs):
        self.call_args = args
        self.call_kwargs = kwargs
        return self.return_value


def test_icl_observer_is_transparent_and_checks_full_context():
    manager = FakeICLManager()
    predictor = SimpleNamespace(inference_mgr=manager)
    estimator = SimpleNamespace(model_=SimpleNamespace(icl_predictor=predictor))
    events = []
    installation = install_icl_call_observer(estimator, on_event=events.append)
    config = {"device": "cpu", "use_amp": False, "use_fa3": False}
    input_mapping = OrderedDict((
        ("R", SimpleNamespace(shape=(3, 3146, 20))),
        ("y_train", SimpleNamespace(shape=(3, 3144))),
    ))
    forward = object()
    try:
        observer = predictor.inference_mgr
        assert observer.configure(**config) is manager
        result = observer(forward, inputs=input_mapping, auto_batch=True)
        assert result is manager.return_value
        assert manager.configure_calls == [config]
        assert manager.call_args == (forward,)
        assert manager.call_kwargs["inputs"] is input_mapping
        assert manager.call_kwargs["auto_batch"] is True
        assert observer.calls == 1
        assert [event["event"] for event in events] == ["icl_forward_enter", "icl_forward_complete"]

        context = verify_full_context(events[0]["inputs"], expected_total_rows=3146,
                                     expected_train_rows=3144)
        assert context == {"R_shape": [3, 3146, 20], "y_train_shape": [3, 3144],
                           "inferred_train_size": 3144, "expected_total_rows": 3146,
                           "full_context_preserved": True}
        for bad_shapes in (
                {"R": [3, 3145, 20], "y_train": [3, 3144]},
                {"R": [3, 3146, 20], "y_train": [3, 3143]},
                {"R": [3, 3146, 20]},
                {"R": [3, 3146, 20], "y_train": [2, 3144]}):
            try:
                verify_full_context([{"tensor_shapes": bad_shapes}], 3146, 3144)
            except ValueError:
                pass
            else:
                raise AssertionError(f"invalid ICL context was accepted: {bad_shapes}")
    finally:
        installation.restore()
    assert predictor.inference_mgr is manager
    assert installation.restored is True


def run_mock():
    test_fixed_chunk_order_shape_config_and_output_repeat()
    test_non_auto_batch_forwards_original_arguments()
    test_rejects_unknown_tensor_and_bad_rank()
    test_rejects_bad_output_and_restores_after_forward_error()
    test_column_row_adapters_coexist_configure_tail_order_unknown_tensor_and_recovery()
    test_icl_observer_is_transparent_and_checks_full_context()
    print("round010 COL+ROW/ICL observer pure mock passed")


if __name__ == "__main__":
    run_mock()
