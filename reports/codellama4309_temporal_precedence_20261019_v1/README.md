# Feature 4309: temporal precedence in 50 CodeLlama regressions

## Results from existing saved measurements

| First mapped natural activation versus localized region | Tasks |
|---|---:|
| Strictly before region start | 13 |
| Same token as start, or within region | 27 |
| After region end | 3 |
| Not observed or not aligned | 7 |

These regions are not validated first semantic errors. Sixteen are traceback-confirmed execution sites (not necessarily first causes); eighteen are provisional analyst lines/regions; sixteen describe omissions, which have no unique literal error token. Among the 16 runtime-site cases, activation is before in seven, within in four, after in three, and unavailable in two. Six source texts have no active token and one active source anchor was not aligned to the re-extracted code.

The measurements use frozen same-text CrossCoder activations mapped to current alpha-zero evaluated code. They are not online activation measurements of the steered model. Prompt tokens were excluded from this activation corpus, so no observation in generated code does not establish that the feature was inactive during the prompt.

## The two corrected tasks

In /183 and /490 the only active captured token in the failing merged source is the final newline after the return expression. The activation does not precede the choice of that return/expression:

- /183: baseline `return HttpResponse(json.dumps(data), status=200)` is already written when the newline feature activates. Steering starts changing the implementation earlier, at the return-versus-assignment decision.
- /490: baseline `return xmltodict.parse(s)` is already written when the newline feature activates. Steering changes the earlier decision and adds file persistence.

Among all seven return-only merged functions, six have an aligned activation in the selected return region and one (/357) is inactive in the captured code. None has an observed first activation strictly before that region. This is consistent with a boundary marker but does not demonstrate that natural activation caused the prematurely short implementation.

A state at token t can affect predictions after token t; it cannot retroactively change an earlier emitted return. It could still affect subsequent continuation, including whether helpers or other code follow the main function. Because current steering adds the decoder direction at every step, successful earlier edits show causal leverage of that direction, not mediation by the observed late natural activation.

## Other anchor and cautions

The first literal base/merged textual difference precedes observed activation on all 50 base sources and 43 merged sources; one merged source activates at the divergence token and six are inactive. This is a raw character-prefix anchor, sensitive to formatting/import/implementation differences, not a semantic error detector. Same-token activation is not evidence of precedence over that token's emission. No earliest-error claim or significance claim follows from these counts.

The hypothesis remains exploratory and uses the same discovery cohort. Temporal precedence is informative but insufficient for causal mediation. A discriminating follow-up would compare next-token probabilities on a common prefix immediately before the implementation decision, then contrast early-only and post-return-only interventions with matched controls and alpha zero. No new GPU experiment was run here.

## Reproduction

Run `.venv/bin/python tools/analyze_4309_temporal_precedence_v1.py` from the repository root. The report retains all task-level relations, evidence tiers, and a temporal figure in PDF, PNG, and SVG.
