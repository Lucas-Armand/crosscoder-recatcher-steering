# Qualitative analysis of steering features 8994, 11586, and 2562

## Scope and method

This report compares the exact postprocessed code submitted to BigCodeBench at
`alpha=0` with every nonzero traditional-steering arm. It combines:

- unified code diffs;
- BigCodeBench verdicts and exception details;
- an AST comparison after removing docstrings;
- task group (new-control failure or new-control success);
- dose and residual-stream diagnostics.

An `executable AST` change means that executable Python structure changed after
docstrings were removed. A `non-executable` change contains only comments,
docstrings, formatting, or other text that does not change the stripped AST.
Repeated doses for one task are not independent observations.

The semantic labels below are hypotheses, not identified ground-truth concepts.
Traditional residual steering can expose a direction's behavioral influence,
but it is not equivalent to setting the CrossCoder latent that originally
selected the feature.

## Executive conclusion

None of the three directions behaves like a clean, local
"success/failure mechanism."

- **8994** is most consistent with a direction affecting solution continuity,
  alternative-solution restart, and preservation of the initial implementation.
  High positive steering can replace or truncate functional code, but it does
  not repair the pre-existing regression error.
- **11586** is most consistent with code-form/API-choice and implementation
  rewriting. It sometimes changes resource-management or library choices and
  sometimes triggers the same alternative-solution behavior seen for 8994.
  Evidence for one coherent semantic concept is weak.
- **2562** is most consistent with verbose explanatory/example continuation and
  presentation-level elaboration. Negative steering predominantly changes
  comments, usage examples, whitespace, and equivalent high-level API forms.
  It leaves the actual causes of failure unchanged.

The most important scientific implication is that the PR-AUC associations may
partly identify **generation-state or completion-style proxies**, rather than
causal algorithmic variables. Maximum activation over the evaluated sequence
can be high because the model entered a verbose, duplicative, or example-writing
state after an earlier semantic mistake.

## Feature 8994

### Observed changes

Across the five regressions and five controls over four stronger doses:

| Group | Identical | Non-executable change | Executable AST change |
|---|---:|---:|---:|
| Regressions | 16/20 | 2/20 | 2/20 |
| Controls | 5/20 | 7/20 | 8/20 |

The direction affected successful controls much more often than target
regressions.

Representative cases:

1. **BigCodeBench/756, alpha 3-4 — destructive alternative solution**

   The original `task_func` was renamed to `task_func_2`; imports and the file
   moving loop were removed. The original failure was
   `TypeError: object of type 'generator' has no len()`. Steering did not fix
   that logic. It changed the failure to missing definitions such as `List`.

2. **BigCodeBench/861 — loss/restart of an implementation**

   Depending on dose, the generated code removed the first implementation,
   retained or rewrote a second `task_func_2`, duplicated long explanatory
   blocks, or lost a return path. The passing control became a failure. This is
   the clearest behavioral effect, but it is destructive rather than restorative.

3. **BigCodeBench/536, alpha 3-4 — formatting-only change**

   Steering inserted blank lines around existing statements. The regression
   still failed because the evaluator expected `task_func`, while the generation
   defined `task_func_2`.

4. **BigCodeBench/272 — docstring indentation only**

   All strong doses merely changed indentation inside JSON examples in a
   docstring. The program remained correct.

### Semantic hypothesis

**Primary hypothesis, moderate confidence:** feature 8994 participates in a
generation state related to **solution continuity versus restarting/replacing a
solution**, including duplicate implementations and `task_func_2`-style
continuations.

**Secondary hypothesis, low confidence:** it may encode preservation of
imports, signature, and implementation context across a long completion.

Evidence against a clean "useful algorithm" interpretation:

- most regressions were textually identical;
- changed regressions did not move toward their actual test failure;
- controls were affected more often;
- high doses introduced new structural failures.

## Feature 11586

### Observed changes

| Group | Identical | Non-executable change | Executable AST change |
|---|---:|---:|---:|
| Regressions | 18/20 | 0/20 | 2/20 |
| Controls | 8/20 | 3/20 | 9/20 |

Again, controls changed more frequently than regressions.

Representative cases:

1. **BigCodeBench/536, alpha 3-4 — signature and output-path rewrite**

   Steering removed the optional `csv_path`, wrote the CSV to `table_name`, and
   returned that path. This is a genuine semantic rewrite, but it did not repair
   the existing missing-`task_func` failure.

2. **BigCodeBench/455, all doses — library/API substitution**

   `np.histogram(samples)` became `stats.histogram(samples)`, accompanied by
   docstring rewrites. The selected task still passed, suggesting the modified
   helper was not decisive for the tested entry point or path.

3. **BigCodeBench/1109, alpha 4 — resource-management style**

   A `with open(...)` context manager became explicit `open`, `readlines`, and
   `close`. This changed coding style while preserving the verdict.

4. **BigCodeBench/861 — alternative-solution behavior**

   As with 8994, steering removed or rewrote the first implementation and
   changed `task_func`/`task_func_2` structure, causing the control to fail.

### Relationship to feature 8994

The merged-side decoder vectors are nearly orthogonal:

```text
cosine(decoder_8994, decoder_11586) = -0.0183
```

Nevertheless, on four shared prompts, some generated completions were exactly
identical across the two feature interventions at the same dose. This suggests
that those prompts were close to discrete sampling boundaries: distinct small
logit perturbations can select the same alternative continuation. Similar
outputs therefore do not imply that the latent directions have the same
semantic meaning.

### Semantic hypothesis

**Primary hypothesis, low-to-moderate confidence:** feature 11586 influences
**implementation form and API choice**, including helper selection,
resource-management style, and argument/output conventions.

**Secondary hypothesis, low confidence:** like 8994, it may influence whether
the model continues the first solution or emits an alternative implementation.

There is not enough repeated evidence to label it as a specific library,
algorithm, or error-handling feature.

## Feature 2562

### Observed changes

| Group | Identical | Non-executable change | Executable AST change |
|---|---:|---:|---:|
| Regressions | 10/20 | 8/20 | 2/20 |
| Controls | 9/20 | 9/20 | 2/20 |

Although 7-8 of ten raw completions changed at each dose, most changes were
non-executable.

Representative cases:

1. **BigCodeBench/238 — output comments and usage notes**

   Negative steering changed alignment in an example output and rewrote notes
   about displaying a plot. The true failure remained
   `AssertionError: 4 != 10`; the data-selection logic was untouched.

2. **BigCodeBench/133 — tutorial wording only**

   The final note changed from a generic instruction to replace the example
   DataFrame to a more explicit `df = pd.DataFrame(...)` instruction. The
   failure remained `name 'np' is not defined`.

3. **BigCodeBench/134, alpha -2/-3 — equivalent plotting API**

   `df[last_column].plot.hist(...)` became
   `df[last_column].hist(...)`, followed by an extra expected-output comment.
   The failure remained `name 'np' is not defined`, which occurs before this
   choice can matter.

4. **BigCodeBench/923 — whitespace around validation blocks**

   Blank-line formatting changed, with no semantic or verdict effect.

5. **BigCodeBench/106, alpha -3/-4 — compact implementation plus example**

   Separate `LinearRegression()` construction and `.fit()` calls became
   `LinearRegression().fit(...)`; an executable usage example was appended.
   The task continued to pass.

6. **BigCodeBench/362 — explanatory tail rewrite**

   Notes about test files and running the script were shortened or replaced by
   tutorial text. Core Excel-handling logic and the passing verdict remained
   unchanged.

### Semantic hypothesis

**Primary hypothesis, relatively high confidence:** feature 2562 is associated
with **explanatory/tutorial continuation**, including usage examples, expected
output, comments about plotting, and post-solution guidance.

**Secondary hypothesis, moderate confidence:** it may also influence preference
for explicit multi-step code versus compact high-level API expressions.

This offers a plausible explanation for its historical failure association:
the feature may be a marker of a verbose post-solution generation state, or of
tasks involving plotting/data-science exposition, rather than the cause of the
underlying error. Suppression changes presentation but leaves missing imports,
bad external URLs, and incorrect data selection intact.

## Cross-feature interpretation

The three experiments reveal two broader patterns:

1. **The original errors usually predate the changed region.**

   Examples include missing `np`/`plt`, wrong function names, incorrect
   validation expressions, invalid URLs, and an incorrect number of plotted
   points. Steering commonly changes later comments, helpers, or alternative
   continuations and therefore cannot repair the causal error.

2. **Sequence-level max aggregation does not identify when a feature matters.**

   A feature can rank highly because it activates after the model has already
   committed to a failing implementation. The current PR-AUC screen is useful
   for candidate discovery, but it does not establish temporal precedence.

## Recommended next analysis

Before more generation experiments:

1. For each candidate task, plot per-token feature activation/contribution
   against decoded tokens.
2. Mark the first token where the failing semantic decision appears.
3. Retain candidates only when the feature difference occurs before that
   decision.
4. Separate activation in executable code from activation in docstrings,
   comments, and post-implementation examples.
5. Repeat the screening with temporally restricted aggregations, such as:
   - maximum over the function body before the first return;
   - maximum before the first divergent token between paired models;
   - maximum over executable-token spans only, as a sensitivity analysis.

For causal testing, activation-matched clamping at the temporally relevant
tokens is more interpretable than adding a constant decoder vector at every
generation step.

