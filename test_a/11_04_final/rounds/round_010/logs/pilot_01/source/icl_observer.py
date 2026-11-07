"""Standard-library transparent observer for the existing ICL manager call."""

from __future__ import annotations

from typing import Any, Callable


class ICLCallObserver:
    def __init__(self, manager: Any, on_event: Callable[[dict], None]):
        if not callable(manager):
            raise TypeError("ICL manager must be callable")
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
        return self.manager.configure(*args, **kwargs)

    @staticmethod
    def input_summary(args: tuple[Any, ...], kwargs: dict[str, Any]) -> list[dict]:
        values = list(args[1:])
        values.extend(kwargs.values())
        summary = []
        for value in values:
            keys = list(value.keys()) if hasattr(value, "keys") else None
            shapes = {}
            if hasattr(value, "items"):
                for key, item in value.items():
                    shape = getattr(item, "shape", None)
                    if shape is not None:
                        shapes[str(key)] = [int(size) for size in shape]
            train_size = value.get("train_size") if hasattr(value, "get") else None
            if train_size is not None:
                try:
                    train_size = int(train_size)
                except (TypeError, ValueError):
                    pass
            if keys is not None or shapes or train_size is not None:
                summary.append({"keys": [str(key) for key in keys] if keys is not None else None,
                                "tensor_shapes": shapes, "train_size": train_size})
        return summary

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        call_id = self.calls
        self.calls += 1
        self.on_event({"event": "icl_forward_enter", "call_id": call_id,
                       "inputs": self.input_summary(args, kwargs)})
        try:
            result = self.manager(*args, **kwargs)
        except BaseException as exc:
            self.on_event({"event": "icl_forward_complete", "call_id": call_id,
                           "completed": False, "error_type": type(exc).__name__,
                           "error": str(exc)})
            raise
        shape = getattr(result, "shape", None)
        self.on_event({"event": "icl_forward_complete", "call_id": call_id,
                       "completed": True,
                       "output_shape": [int(size) for size in shape] if shape is not None else None})
        return result


class ICLObserverInstallation:
    def __init__(self, predictor: Any, original_manager: Any, observer: ICLCallObserver):
        self.predictor = predictor
        self.original_manager = original_manager
        self.observer = observer
        self.restored = False

    def restore(self) -> None:
        if self.restored:
            return
        if getattr(self.predictor, "inference_mgr", None) is not self.observer:
            raise RuntimeError("ICL inference manager changed while observer was installed")
        self.predictor.inference_mgr = self.original_manager
        self.restored = self.predictor.inference_mgr is self.original_manager
        if not self.restored:
            raise RuntimeError("could not restore original ICL inference manager")


def install_icl_call_observer(estimator: Any, on_event: Callable[[dict], None]) -> ICLObserverInstallation:
    predictor = getattr(getattr(estimator, "model_", None), "icl_predictor", None)
    if predictor is None:
        raise AttributeError("fitted estimator does not expose model_.icl_predictor")
    original = getattr(predictor, "inference_mgr", None)
    if original is None:
        raise AttributeError("model_.icl_predictor has no inference_mgr")
    observer = ICLCallObserver(original, on_event)
    predictor.inference_mgr = observer
    return ICLObserverInstallation(predictor, original, observer)


def verify_full_context(inputs: list[dict], expected_total_rows: int, expected_train_rows: int) -> dict:
    """Validate the pinned ICL mapping R+y_train and report inferred train_size."""
    candidates = [item for item in inputs if "R" in item.get("tensor_shapes", {})
                  or "y_train" in item.get("tensor_shapes", {})]
    if len(candidates) != 1:
        raise ValueError("ICL inputs must expose exactly one R/y_train mapping")
    shapes = candidates[0].get("tensor_shapes", {})
    r_shape = shapes.get("R")
    y_shape = shapes.get("y_train")
    if (not isinstance(r_shape, list) or len(r_shape) != 3
            or not isinstance(y_shape, list) or len(y_shape) != 2):
        raise ValueError("ICL input contract requires R=(B,T,D) and y_train=(B,train_size)")
    train_size = y_shape[1]
    full_context = (r_shape[0] == y_shape[0] and r_shape[1] == expected_total_rows
                    and train_size == expected_train_rows)
    if not full_context:
        raise ValueError("ICL input does not preserve full FIT+query T and FIT-derived train_size")
    return {"R_shape": r_shape, "y_train_shape": y_shape,
            "inferred_train_size": train_size, "expected_total_rows": expected_total_rows,
            "full_context_preserved": True}
