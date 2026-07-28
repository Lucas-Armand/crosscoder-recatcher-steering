import importlib.util
import sys
import unittest
from pathlib import Path


PATH = Path(__file__).parents[1] / "tools" / "code_extraction.py"
SPEC = importlib.util.spec_from_file_location("code_extraction", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class CodeExtractionTest(unittest.TestCase):
    def test_leading_python_beats_larger_later_non_python_fence(self):
        prompt = "def below_zero(xs):\n"
        raw = (
            "   return any(x < 0 for x in xs)\n"
            "```\n```below_zero explanation that is much longer than the code\n"
            "```kotlin\nfun main() { println(1) }\n```\n"
        )
        result = MODULE.extract_python_candidate(prompt, raw, "below_zero")
        self.assertEqual(result.strategy, "leading_literal_prefix")
        self.assertIn("return any", result.code)
        self.assertNotIn("kotlin", result.code)
        compile(result.code.replace("   return", "    return"), "<test>", "exec")

    def test_helper_definition_is_not_truncated(self):
        prompt = "def answer(x):\n"
        raw = "    return helper(x)\n\n\ndef helper(x):\n    return x + 1\n"
        result = MODULE.extract_python_candidate(prompt, raw, "answer")
        self.assertIn("def helper", result.code)
        namespace = {}
        exec(result.code, namespace)
        self.assertEqual(namespace["answer"](2), 3)

    def test_first_python_fence_when_response_starts_fenced(self):
        result = MODULE.extract_python_candidate(
            "def answer():\n",
            "```python\n    return 7\n```\nExplanation\n```json\n{}\n```",
            "answer",
        )
        self.assertEqual(result.strategy, "fenced_block_0")
        self.assertEqual(result.generated_spans, [(10, 22)])

    def test_main_guard_is_removed_but_helpers_before_it_remain(self):
        raw = (
            "    return helper()\n\n"
            "def helper():\n    return 1\n\n"
            "if __name__ == '__main__':\n    print(helper())\n"
        )
        result = MODULE.extract_python_candidate("def answer():\n", raw, "answer")
        self.assertIn("def helper", result.code)
        self.assertNotIn("__main__", result.code)

    def test_incomplete_trailing_definition_is_removed_after_complete_helper(self):
        raw = (
            "    return helper(x)\n\n"
            "def helper(x):\n    return x + 1\n\n"
            "def unfinished(\n"
        )
        result = MODULE.extract_python_candidate("def answer(x):\n", raw, "answer")
        self.assertIn("def helper", result.code)
        self.assertNotIn("unfinished", result.code)
        compile(result.code, "<test>", "exec")


if __name__ == "__main__":
    unittest.main()
