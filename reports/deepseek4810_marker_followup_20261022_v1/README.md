# DeepSeek 4810: marker distribution, executable contamination and steering

The five-page PDF `DEEPSEEK4810_MARKER_DISTRIBUTION_AND_STEERING.pdf` addresses three different questions: temporal distance to a lexical marker, whether that marker is itself erroneous, and what actually changes under intervention. All data are pre-existing; no inference or benchmark execution was performed.

## Temporal distance

The reference is the first non-whitespace character of the first matching marker line, not the original regex's potentially earlier blank-line prefix. Signed distance is first activation minus marker token. Negative means before.

- 119 original failing base texts: 48 first activations before, 33 at the marker token, 38 after. All positive distances are exactly +1 token.
- 77/119 lie within one token, 82 within five, 86 within ten. Median is zero; range -268 to +1 tokens. Negative tails are retained in the full empirical distribution.
- Of the 107 whose first marker is a test-file comment: 36 activate before its visible line, 71 inside the comment text, none after the line. The remaining 12 start with an import/class marker instead.
- In all 96 frozen texts containing the lexical `from task_func import` pattern, first activation precedes that import token. This lexical observation alone does not prove execution or causal mediation.

## Comments versus failures

`#tests/...` and `#test_task...` are comments, not executable errors. A generated program may remain valid after such a comment, and the comment does not irrevocably commit the continuation to failure. Conversely, comments can signal a test-file-generation mode that precedes a bad module import. Evaluations execute after generation: temporal positions here mean order of text emission, not the moment an interpreter crashes during generation.

Among all 14 alpha-minus-five successes, the saved alpha-zero evaluator reports a missing module: `task_func` in 11 and `task` in 3. The earliest textual import matching that missing module occurs 4 to 29 tokens AFTER the first natural activation in each of those 14 original frozen texts. This links the activation to a precursor of an observed failure, rather than calling the comment itself the error. It is not a full traceback localization or an activation-gated mediation experiment.

## Matched intervention comparison

We compare alpha-zero and steering programs using the SAME current extraction path. Natural activation positions instead refer to the original frozen capture source; these must not be silently interchanged.

At alpha -5:

| Population | Matching test-file comment before | Comment removed | Comment retained | No matching comment before |
|---|---:|---:|---:|---:|
| All 57 changed programs | 52 | 19 | 33 | 5 |
| All 14 official corrections | 11 | 11 | 0 | 3 |

All 14 successes lose every specific marker detected by this heuristic, but not necessarily every comment, test-like example or trailing continuation. Twenty-three tasks lose all heuristic markers; nine of those still fail. Marker removal is not a sufficient correctness criterion.

Eight successes preserve the first `task_func` body's AST ignoring comments/docstrings. This does not establish unchanged global behavior, helper behavior, or later function redefinitions. Six change that AST too; their repair cannot be attributed solely to removing a trailing block.

Examples:

- /695 removes test/import code while preserving the main-body AST; the original error is missing `task_func`; a commented example remains and the program passes.
- /666 removes the test-file import but retains executable print/examples; main-body AST is unchanged and official tests pass. This is not immediate stopping.
- /1115 replaces tests/imports with many repeated `# Write your code here` comments; the code passes despite continuing to generate repetitive commentary.
- /25 removes the test-file marker but creates another implementation; the result still fails. The first main-body AST being unchanged is not enough when later code can redefine the function.

## Interpretation and limits

The feature is temporally associated with entry into a test-like continuation. In the corrected cases it activates before text corresponding to the observed missing-module failure, and steering removes that import/test pattern. This supports a behaviorally coherent causal intervention, not proof that the natural feature is the necessary cause or that its effect is simply to stop generation. Restricted-timing / activation-gated interventions and common-prefix probability comparisons remain separate future tests.

The first-marker cohort is already selected for contamination; these frequencies do not validate heuristic specificity on arbitrary passing code. Natural activations are joint same-text CrossCoder measurements, with prompt tokens excluded, rather than online measurements in the intervention arm.

## Contents and reproduce

Five figures in PDF/PNG/SVG, combined PDF, all 119 temporal records, all 595 task-dose marker transitions, official baseline failure evidence for 14 successes, and complete before/after/diffs for all 57 changed alpha-minus-five programs. `dose_summary.json` covers alpha -1 through -5.

Run `tools/analyze_deepseek4810_marker_followup_v1.py` from the repository root using its existing Python environment. The exact marker regex is imported from `tools/plot_deepseek4810_marker_precedence_v1.py`. Source activations and evaluated programs are unchanged.
