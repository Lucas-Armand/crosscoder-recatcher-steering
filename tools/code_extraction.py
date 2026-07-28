#!/usr/bin/env python3
"""Deterministic, test-independent extraction of executable Python candidates."""

from __future__ import annotations

import ast
import builtins
import difflib
import re
from dataclasses import asdict, dataclass


SAFE_SUFFIX_MARKERS = (
    "\n\nif __name__", "\nif __name__",
    "\n\n# Test", "\n# Test", "\n\n# test", "\n# test",
    "\n\nprint(", "\nprint(", "\n\nassert ", "\nassert ",
    "\n\nExplanation:", "\nExplanation:",
    "\n\nThe function", "\nThe function",
    "\n\nThis function", "\nThis function",
)
FENCE_RE = re.compile(r"```(?P<language>[^\n`]*)\n?")


@dataclass(frozen=True)
class Extraction:
    code: str
    generated_text: str
    generated_spans: list[tuple[int, int]]
    strategy: str
    language: str
    candidate_count: int
    ambiguous: bool

    def metadata(self) -> dict:
        return asdict(self)


def _trial_normalize(code: str) -> str:
    for source, target in (("Ċ", "\n"), ("ĉ", "\t"), ("Ġ", " ")):
        code = code.replace(source, target)
    return re.sub(r"(?m)^( {3})(\S)", r"    \2", code)


def _compiles(code: str) -> bool:
    try:
        ast.parse(_trial_normalize(code))
        return True
    except (SyntaxError, ValueError):
        return False


def _safe_cut(text: str) -> int:
    positions = [text.find(marker) for marker in SAFE_SUFFIX_MARKERS]
    return min((position for position in positions if position >= 0), default=len(text))


def _compose(prompt: str, generated: str, entry_point: str | None) -> tuple[str, int]:
    generated = generated.rstrip()
    if entry_point:
        marker = f"def {entry_point}"
        position = generated.find(marker)
        if position >= 0:
            return generated[position:].rstrip() + "\n", position
    return prompt.rstrip() + "\n" + generated + "\n", 0


def _longest_compilable_prefix(
    prompt: str, generated: str, entry_point: str | None
) -> tuple[str, str, int] | None:
    """Return the longest line-aligned literal prefix that compiles after trial repair."""
    boundaries = [match.end() for match in re.finditer(r"\n", generated)]
    if not boundaries or boundaries[-1] != len(generated):
        boundaries.append(len(generated))
    for end in reversed(boundaries):
        piece = generated[:end].rstrip()
        if not piece:
            continue
        code, offset = _compose(prompt, piece, entry_point)
        if _compiles(code):
            return code, piece[offset:], offset
    return None


def _fenced_blocks(text: str) -> list[tuple[int, int, str, str]]:
    markers = list(FENCE_RE.finditer(text))
    blocks = []
    for left, right in zip(markers[0::2], markers[1::2]):
        blocks.append((
            left.end(), right.start(), left.group("language").strip().lower(),
            text[left.end():right.start()],
        ))
    return blocks


def _literal_spans(source: str, selected: str) -> list[tuple[int, int]] | None:
    selected = selected.rstrip()
    matcher = difflib.SequenceMatcher(a=source, b=selected, autojunk=False)
    blocks = [block for block in matcher.get_matching_blocks() if block.size]
    if sum(block.size for block in blocks) != len(selected):
        return None
    return [(block.a, block.a + block.size) for block in blocks]


def _unresolved_names(code: str) -> set[str]:
    try:
        tree = ast.parse(_trial_normalize(code))
    except SyntaxError:
        return set()
    loaded = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    defined = {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    defined.update(
        alias.asname or alias.name.split(".")[0]
        for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    )
    defined.update(dir(builtins))
    return loaded - defined


def _defined_names(code: str) -> set[str]:
    try:
        tree = ast.parse(_trial_normalize(code))
    except SyntaxError:
        return set()
    return {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


def extract_python_candidate(
    prompt: str, raw_completion: str, entry_point: str | None,
    historical_candidate: str | None = None,
) -> Extraction:
    """Choose code by deterministic format precedence, never evaluator outcome.

    A literal leading continuation is preferred because benchmark prompts normally
    end at the function signature/docstring. If the response begins with a fence,
    the first compilable Python-labelled block is preferred, then an unlabelled
    block. A second ``def`` is never a cutoff: helper definitions are retained.
    """
    text = str(raw_completion)
    blocks = _fenced_blocks(text)
    first_fence = text.find("```")
    prefix_end = first_fence if first_fence >= 0 else len(text)
    prefix_end = min(prefix_end, _safe_cut(text[:prefix_end]))
    prefix = text[:prefix_end].rstrip()

    candidates: list[tuple[str, str, int, int, str]] = []
    if prefix.strip():
        candidates.append(("leading_literal_prefix", prefix, 0, prefix_end, "python"))

    for language_group in ({"python", "py", "python3"}, {""}):
        for index, (start, end, language, block) in enumerate(blocks):
            if language in language_group:
                cut = _safe_cut(block)
                candidates.append((
                    f"fenced_block_{index}", block[:cut].rstrip(),
                    start, start + cut, language or "unlabelled",
                ))

    if not candidates:
        cut = _safe_cut(text)
        candidates.append(("unfenced_completion", text[:cut].rstrip(), 0, cut, "python"))

    composed = []
    for strategy, generated, start, end, language in candidates:
        if not generated.strip():
            continue
        longest = _longest_compilable_prefix(prompt, generated, entry_point)
        if longest is None:
            code, generated_offset = _compose(prompt, generated, entry_point)
            retained = generated[generated_offset:]
        else:
            code, retained, generated_offset = longest
        composed.append((
            strategy, retained, start + generated_offset,
            start + generated_offset + len(retained), language, code,
        ))
    compilable = [item for item in composed if _compiles(item[5])]
    selected = (compilable or composed)[0]
    strategy, generated, start, end, language, code = selected
    selected_spans = [(start, end)]

    historical = None
    if historical_candidate:
        historical_code = str(historical_candidate)
        prompt_prefix = prompt.rstrip() + "\n"
        historical_generated = (
            historical_code[len(prompt_prefix):]
            if historical_code.startswith(prompt_prefix)
            else historical_code
        ).rstrip()
        spans = _literal_spans(text, historical_generated)
        if spans:
            historical = (
                "historical_candidate_preserved", historical_generated,
                spans, "python", historical_code,
            )

    if historical is not None:
        hist_strategy, hist_generated, hist_spans, hist_language, hist_code = historical
        leading_discarded = (
            first_fence >= 0 and bool(prefix.strip())
            and not text.startswith(hist_generated)
            and _compiles(code)
        )
        helper_was_removed = bool(
            _unresolved_names(hist_code) & _defined_names(code)
        )
        if not leading_discarded and not helper_was_removed and _compiles(hist_code):
            strategy, generated, selected_spans, language, code = historical
        elif helper_was_removed:
            strategy = "dependency_preserving_prefix"

    return Extraction(
        code=code,
        generated_text=generated,
        generated_spans=selected_spans,
        strategy=strategy,
        language=language,
        candidate_count=len(composed),
        ambiguous=len(compilable) > 1,
    )
