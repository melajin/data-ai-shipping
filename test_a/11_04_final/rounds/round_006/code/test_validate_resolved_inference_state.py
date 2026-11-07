"""Pure mock check for the pilot diagnostic validator; never imports TabICL or loads weights."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path


SOURCE = Path(__file__).with_name("replay_inner_pilot.py")
_FUNCTION_NAMES = {"resolved_inference_state", "validate_resolved_inference_state"}
_tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
_functions = [node for node in _tree.body
              if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
              and node.name in _FUNCTION_NAMES]
if {node.name for node in _functions} != _FUNCTION_NAMES:
    raise RuntimeError("could not extract the exact diagnostic functions")
_namespace: dict[str, object] = {}
exec(compile(ast.Module(body=_functions, type_ignores=[]), str(SOURCE), "exec"), _namespace)
validate = _namespace["validate_resolved_inference_state"]


class Stage:
    def __init__(self, *, device="cpu", use_amp=False, use_fa3=False, offload=False):
        self._values = {"device": device, "use_amp": use_amp, "use_fa3": use_fa3,
                        "offload": offload, "disk_offload_dir": None, "verbose": False}

    def items(self):
        return self._values.items()


class Config:
    def __init__(self, *, device="cpu", use_amp=False, use_fa3=False,
                 col_offload="auto", row_offload=False, icl_offload=False):
        self.COL_CONFIG = Stage(device=device, use_amp=use_amp, use_fa3=use_fa3, offload=col_offload)
        self.ROW_CONFIG = Stage(device=device, use_amp=use_amp, use_fa3=use_fa3, offload=row_offload)
        self.ICL_CONFIG = Stage(device=device, use_amp=use_amp, use_fa3=use_fa3, offload=icl_offload)


class Model:
    def __init__(self, *, config=None, offload_mode="auto", kv_cache=False,
                 model_kv_cache=None, expose_model_kv_cache=True, cache_mode_marker="absent"):
        self.inference_config_ = config or Config()
        self.offload_mode = offload_mode
        self.kv_cache = kv_cache
        if expose_model_kv_cache:
            self.model_kv_cache_ = model_kv_cache
        if cache_mode_marker != "absent":
            self.cache_mode_ = cache_mode_marker


class ValidatorMockTests(unittest.TestCase):
    def test_absent_cache_mode_is_accepted_and_reported_as_absent(self):
        result = validate(Model())
        scope = result["estimator_scope"]
        self.assertIs(scope["cache_mode_present"], False)
        self.assertIsNone(scope["cache_mode"])

    def test_explicit_none_cache_mode_is_accepted_and_distinguished(self):
        result = validate(Model(cache_mode_marker=None))
        scope = result["estimator_scope"]
        self.assertIs(scope["cache_mode_present"], True)
        self.assertIsNone(scope["cache_mode"])

    def test_incorrect_cpu_amp_fa3_offload_and_kv_settings_are_rejected(self):
        cases = {
            "CPU": Model(config=Config(device="cuda")),
            "AMP": Model(config=Config(use_amp=True)),
            "FA3": Model(config=Config(use_fa3=True)),
            "column offload": Model(config=Config(col_offload=False)),
            "row offload": Model(config=Config(row_offload="auto")),
            "estimator offload": Model(offload_mode="cpu"),
            "KV enabled": Model(kv_cache=True, cache_mode_marker="kv"),
            "KV state allocated": Model(model_kv_cache={"cache": object()}),
            "missing required model KV state": Model(expose_model_kv_cache=False),
            "unexpected non-None cache mode": Model(cache_mode_marker="kv"),
        }
        for label, model in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(RuntimeError):
                    validate(model)


if __name__ == "__main__":
    unittest.main()
