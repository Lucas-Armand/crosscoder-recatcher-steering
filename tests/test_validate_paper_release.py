import importlib.util
import json
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools" / "validate_paper_release.py"
SPEC = importlib.util.spec_from_file_location("validate_paper_release", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ValidationHelpersTest(unittest.TestCase):
    def test_parse_jsonl_ignores_blank_lines(self):
        self.assertEqual(MODULE.parse_jsonl('{"a": 1}\n\n{"a": 2}\n'), [{"a": 1}, {"a": 2}])

    def test_expected_seed(self):
        self.assertEqual(MODULE.expected_seed({"task_idx": 12, "gen_idx": 0}), 2200)

    def test_declared_activation_exception(self):
        manifest = {
            "benchmarks": {"bigcodebench": {"expected_tasks": 1140}},
            "activation_exceptions": [
                {
                    "benchmark": "bigcodebench",
                    "models": ["deepseek_base"],
                    "task_idx": 764,
                }
            ],
        }
        expected, omitted = MODULE.activation_expected_count(
            manifest, "bigcodebench", "deepseek_base"
        )
        self.assertEqual(expected, 1139)
        self.assertEqual(omitted, [764])
        self.assertTrue(
            MODULE.is_declared_activation_omission(
                manifest, "bigcodebench", "deepseek_base", 764
            )
        )
        self.assertFalse(
            MODULE.is_declared_activation_omission(
                manifest, "bigcodebench", "deepseek_base", 765
            )
        )

    def test_float_contract_comparison(self):
        self.assertTrue(MODULE.values_equal("0.0001", 0.0001))
        self.assertFalse(MODULE.values_equal("0.001", 0.0001))

    def test_manifest_is_valid_json(self):
        path = Path(__file__).parents[1] / "manifests" / "paper_v1.json"
        manifest = json.loads(path.read_text())
        self.assertEqual(len(manifest["crosscoders"]), 4)
        self.assertEqual(manifest["generation_contract"]["required_activation_layer"], 16)


if __name__ == "__main__":
    unittest.main()
