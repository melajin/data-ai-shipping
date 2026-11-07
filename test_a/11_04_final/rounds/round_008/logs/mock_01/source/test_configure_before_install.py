"""Pure standard-library mock for the round008 configure-before-install sequence."""

from __future__ import annotations

from collections import OrderedDict
from types import SimpleNamespace

from column_chunk import install_column_chunk_adapter


class FakeTensor:
    def __init__(self, shape, values=None, storage=None, indices=None):
        self.shape = tuple(int(size) for size in shape)
        count = 1
        for size in self.shape:
            count *= size
        self._storage = (list(values) if values is not None else [None] * count) if storage is None else storage
        self._indices = list(range(count)) if indices is None else list(indices)
        if len(self._storage) != count and indices is None:
            raise ValueError("fake tensor storage size does not match shape")
        if len(self._indices) != count:
            raise ValueError("fake tensor view size does not match shape")

    @property
    def values(self):
        return [self._storage[index] for index in self._indices]

    def narrow(self, axis, start, length):
        if axis < 0:
            axis += len(self.shape)
        if axis < 0 or axis >= len(self.shape) or start < 0 or length < 0 \
                or start + length > self.shape[axis]:
            raise IndexError("invalid fake narrow")
        inner = 1
        for size in self.shape[axis + 1:]:
            inner *= size
        outer = 1
        for size in self.shape[:axis]:
            outer *= size
        selected = []
        for outer_index in range(outer):
            base = outer_index * self.shape[axis] * inner
            selected.extend(self._indices[base + start * inner:base + (start + length) * inner])
        shape = list(self.shape)
        shape[axis] = length
        return FakeTensor(shape, storage=self._storage, indices=selected)

    def new_empty(self, shape):
        count = 1
        for size in shape:
            count *= size
        return FakeTensor(shape, values=[None] * count)

    def copy_(self, source):
        if len(self._indices) != len(source.values):
            raise ValueError("fake copy size mismatch")
        for destination, value in zip(self._indices, source.values):
            self._storage[destination] = value
        return self


class FakeManager:
    def __init__(self, enc_name):
        self.enc_name = enc_name
        self.exe_device = SimpleNamespace(type="cpu")
        self._is_configured = False
        self.use_amp = None
        self.use_fa3 = None
        self.offload_mode = None
        self.configure_calls = []
        self.prepared_shapes = []
        self.forward_shapes = []

    def configure(self, **kwargs):
        self.configure_calls.append(dict(kwargs))
        self.exe_device = SimpleNamespace(type=kwargs.get("device", "cpu"))
        self.use_amp = kwargs.get("use_amp", True)
        self.use_fa3 = kwargs.get("use_fa3", True)
        self.offload_mode = SimpleNamespace(name="AUTO" if kwargs.get("offload") == "auto" else "GPU")
        self._is_configured = True

    def _prepare_inputs(self, inputs):
        self.prepared_shapes.append(inputs["features"].shape)
        return inputs

    def _run_forward(self, forward_fn, inputs):
        self.forward_shapes.append(inputs["features"].shape)
        return forward_fn(**inputs)


def identity_forward(features, train_size, y_train, embed_with_test):
    assert train_size == 2
    assert embed_with_test is False
    assert y_train.shape == (features.shape[0], 2)
    for column in range(features.shape[0]):
        assert y_train.values[column * 2] == features.values[column * features.shape[1]] * 10
        assert y_train.values[column * 2 + 1] == y_train.values[column * 2] + 1
    return features


def run_mock() -> None:
    config = {"device": "cpu", "use_amp": False, "use_fa3": False, "offload": "auto"}
    col_manager = FakeManager("tf_col")
    row_manager = FakeManager("tf_row")
    icl_manager = FakeManager("tf_icl")
    col_embedder = SimpleNamespace(inference_mgr=col_manager)
    estimator = SimpleNamespace(
        fit_returned=True,
        inference_config_=SimpleNamespace(COL_CONFIG=config),
        model_=SimpleNamespace(
            col_embedder=col_embedder,
            row_interactor=SimpleNamespace(inference_mgr=row_manager),
            icl_predictor=SimpleNamespace(inference_mgr=icl_manager),
        ),
    )
    assert estimator.fit_returned is True
    assert col_embedder.inference_mgr is col_manager
    assert col_manager._is_configured is False

    lifecycle = ["fit_returned"]
    col_manager.configure(**estimator.inference_config_.COL_CONFIG)
    lifecycle.append("original_manager_configured")
    assert col_manager.configure_calls == [config]
    assert col_manager._is_configured is True
    assert col_manager.exe_device.type == "cpu"
    assert col_manager.use_amp is False and col_manager.use_fa3 is False
    assert col_manager.offload_mode.name == "AUTO"

    events = []
    installation = install_column_chunk_adapter(estimator, on_event=events.append)
    lifecycle.append("adapter_installed")
    assert col_embedder.inference_mgr is installation.adapter
    assert col_embedder.inference_mgr.manager is col_manager

    # ColEmbedding configures on every inference call. The already configured
    # original manager is reached through the installed wrapper with the same map.
    try:
        col_embedder.inference_mgr.configure(**estimator.inference_config_.COL_CONFIG)
        lifecycle.append("wrapped_manager_configured_for_call")
        columns, sequence = 19, 3
        features = FakeTensor((columns, sequence, 1),
                              values=[float(column) for column in range(columns) for _ in range(sequence)])
        targets = FakeTensor((columns, 2),
                             values=[float(column * 10 + step) for column in range(columns) for step in range(2)])
        inputs = OrderedDict((
            ("features", features),
            ("train_size", 2),
            ("y_train", targets),
            ("embed_with_test", False),
        ))
        result = col_embedder.inference_mgr(identity_forward, inputs, output_repeat=3)
        lifecycle.append("chunked_forward_completed")
        assert result.shape == features.shape and result.values == features.values
        assert col_manager.configure_calls == [config, config]
        assert col_manager.prepared_shapes == [(16, 3, 1), (3, 3, 1)]
        assert col_manager.forward_shapes == [(16, 3, 1), (3, 3, 1)]
        started = [event for event in events if event["event"] == "column_chunk_started"]
        completed = [event for event in events if event["event"] == "column_chunk_completed"]
        assert [(event["column_start"], event["column_stop_exclusive"]) for event in started] == [(0, 16), (16, 19)]
        assert [(event["column_start"], event["column_stop_exclusive"]) for event in completed] == [(0, 16), (16, 19)]
        assert col_embedder.inference_mgr is installation.adapter
        assert estimator.model_.row_interactor.inference_mgr is row_manager
        assert estimator.model_.icl_predictor.inference_mgr is icl_manager
    finally:
        installation.restore()
        lifecycle.append("adapter_restored")

    assert lifecycle == ["fit_returned", "original_manager_configured", "adapter_installed",
                         "wrapped_manager_configured_for_call", "chunked_forward_completed", "adapter_restored"]
    assert col_embedder.inference_mgr is col_manager
    assert installation.restored is True
    assert col_manager.configure_calls == [config, config]
    assert estimator.model_.row_interactor.inference_mgr is row_manager
    assert estimator.model_.icl_predictor.inference_mgr is icl_manager
    print("configure-before-install pure mock passed")


if __name__ == "__main__":
    run_mock()
