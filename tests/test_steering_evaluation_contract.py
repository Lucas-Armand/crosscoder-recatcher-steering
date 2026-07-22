import ast
import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools" / "prepare_evaluation_input.py"
SPEC = importlib.util.spec_from_file_location("prepare_evaluation_input", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SteeringEvaluationContractTest(unittest.TestCase):
    def test_new_completion_replaces_baseline_candidate(self):
        baseline = {
            "prompt": "def answer():\n",
            "candidate_code": "def answer():\n    return 'baseline'\n",
            "correct": True,
        }
        completion = "    return 'steered'\n"
        candidate = baseline["prompt"] + completion
        ast.parse(candidate)
        self.assertNotEqual(candidate, baseline["candidate_code"])
        self.assertEqual(candidate, "def answer():\n    return 'steered'\n")

    def test_normalizer_overwrites_stale_baseline_fields(self):
        row = {
            "task_idx": 3,
            "task_id": "HumanEval/3",
            "prompt": "def answer():\n",
            "completion": "    return 'steered'\n",
            "candidate_code": "def answer():\n    return 'baseline'\n",
            "correct": True,
        }
        normalized = MODULE.normalize_row(row, "humanevalplus", "steered", 0)
        self.assertEqual(normalized["candidate_code"], "def answer():\n    return 'steered'\n")
        self.assertEqual(normalized["raw_completion"], "    return 'steered'\n")
        self.assertIsNone(normalized["correct"])
        self.assertTrue(normalized["syntax_ok"])


if __name__ == "__main__":
    unittest.main()
