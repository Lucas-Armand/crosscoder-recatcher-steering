# DeepSeek 4810: first activation versus first lexical test/import marker

The three-page `DEEPSEEK4810_MARKER_PRECEDENCE_REVIEW.pdf` retains exactly the first and fourth DeepSeek boxplots' quantities, adds a paired task-level scatter, reports precedence and per-task signed distance, and audits sensitivity to whitespace anchoring. No new inference was performed.

## Populations and units

119 original failing base-generated programs in the contamination improvement cohort. Activations are offline joint same-text CrossCoder latents for feature 4810. Both positions use that same original evaluated text; prompt tokens are excluded. Token index i is normalized as i / max(1, n-1). A positive marker-minus-activation difference means first activation earlier. Units of the difference are percentage points, not percent reduction.

## Exact original heuristic

```python
re.search(r'(?im)^\s*(?:#\s*tests?[/\\]|#\s*test_task|from\s+task_func\s+import|class\s+Test\w*\s*\()', code_after_prompt)
```

It takes the earliest match, ignoring case, at a line boundary, allowing leading whitespace, for one of:

- A comment starting `#test/`, `#tests/`, or the corresponding backslash path, allowing whitespace after `#`.
- A comment whose beginning is `#test_task`, allowing whitespace after `#`.
- `from task_func import` with flexible whitespace.
- A class declaration starting `class Test...(` with flexible whitespace.

It does NOT mean the first arbitrary import, `import unittest`, or a verified test; nor does it validate scope or semantic correctness. The first matches are test-file comments in 107 cases, task_func imports in 10, and Test-class declarations in 2. This is a lexical proxy for generated test continuation, not an annotated earliest harmful token. Legitimate imports/helpers after the main function are possible.

The original anchor is `match.start()`. Because `\s` includes newlines, leading whitespace can start on earlier blank lines. Position is mapped to the first captured token whose ending character offset exceeds the anchor. This faithfully reproduces the old plot but should not silently be interpreted as the visible marker token.

## Paired results

| First activation | Original anchor | First non-whitespace sensitivity |
|---|---:|---:|
| Before | 42/119 (35.3%) | 48/119 (40.3%) |
| Same token | 6/119 (5.0%) | 33/119 (27.7%) |
| After | 71/119 (59.7%) | 38/119 (31.9%) |

Sensitivity moves the anchor to the first non-whitespace character of the matched marker line; it changes no programs or activations. It is an explicit additional definition, not a retroactive replacement of the published boxplots. Same-token activation is not available before that token's emission.

Original-anchor median lead: -0.221 percentage points (slightly after). Within +/-1 point: 72/119; +/-5: 88/119; +/-10: 99/119. Earlier-looking marginal medians do not establish paired precedence.

The supported descriptive claim is temporal proximity to this lexical boundary, not universal anticipation or causal mediation. The cohort already selects contamination cases and marker prevalence here is not an independent validation of the heuristic. Continuous steering is not naturally activation-gated.

## Files

- `paired_positions.csv` / `.json`: each task's positions, signed distances in tokens and percentage points, both anchor definitions.
- `marker_audit_contexts.json`: matched marker line/context, whitespace prefix and source hashes.
- `SUMMARY.json`: all counts and original CSV hash.
- Three figures in PDF, PNG and SVG, and their combined PDF.

Reproduce using `tools/plot_deepseek4810_marker_precedence_v1.py`; the marker audit uses the original frozen evaluated source and saved token offsets, without re-encoding activations.
