---
description: Run the 9-agent article-review network on an uploaded PDF and print a peer-review report.
argument-hint: <path-to-pdf>
---

You are orchestrating an article appraisal. The PDF path is: $ARGUMENTS

1. **Validate.** If `$ARGUMENTS` is empty, ask for a PDF path and stop. Run
   `test -f "$ARGUMENTS" && file "$ARGUMENTS"` — if the file does not exist or is
   not a PDF, tell the user and stop. Do NOT dispatch any agent until the path is valid.

2. **Fan out (in parallel, one message, nine Task calls).** Dispatch all nine
   agents, each with the same absolute PDF path in its prompt:
   appraisal-methodologist, appraisal-statistician, appraisal-claims-auditor,
   appraisal-clinical-relevance, appraisal-integrity, appraisal-writing,
   appraisal-novelty, appraisal-references, appraisal-plausibility.

3. **Collect** all nine reports. If an agent returns nothing, note which lens is
   missing and mark the final decision *partial* — never silently drop a lens.

4. **Synthesize** into exactly this report and print it to the terminal. For
   `<title>`, use the paper's title as quoted by whichever agent surfaced it
   (e.g. the claims-auditor quotes headline conclusions and often the title;
   the methodologist and references lenses also see it) — if no agent
   surfaced a title, fall back to the PDF filename.

   # Review: <title>
   Source: <path>   |   Full text: Yes/No

   ## Summary
   <2–3 sentences: what the paper did and found, incl. primary result + effect>

   ## Assessment
   <design appropriateness, framework used (from methodologist), novelty framing
   (from novelty), soundness of the clinical/biological rationale and background
   (from plausibility), overall credibility. A weak clinical rationale, an absent
   or implausible mechanism, or a domain-implausible key predictor becomes a
   Major comment.>

   ## Major comments
   1. <substantive issues that change interpretation — drawn from statistician,
      claims auditor, integrity, and any clarity issue that makes a result
      uninterpretable>

   ## Minor comments
   1. <smaller issues>

   ## Writing & presentation
   - Clarity/coherence: <...>
   - Typos & grammar: <... or "none of note">

   ## Reference check
   Verified <n>/<total>.
   - Discrepancy: <ref> — <what disagrees> (retrieved: <DOI/URL>)
   - ⚠ Unverified — please verify online: <ref as printed>

   ## Unable to assess
   - <union of every lens's "could not assess">

   ## Final decision
   **<Accept / Minor revisions / Major revisions / Reject>.**
   <one-paragraph justification: apply the Editorial decision rule below,
   state the deciding salvageability question and your answer, and include
   GRADE-style certainty>

**Editorial decision rule (you are the editor — do NOT just average the lens
severities).** Choose the verdict by the salvageability test — *can the paper's
central claim survive a reanalysis of the dataset already in hand?*

- **Reject** when fixing the core problem needs NEW data (a new/external or
  larger cohort, or measurements never taken) or when the headline result rests
  on a defect that reanalysis of the current data cannot cure — e.g. label/outcome
  leakage, or outcome-derived imputation of a large share of the key inputs — or
  when a confirmed prior work makes the contribution redundant. "Reject but
  resubmit after collecting new data" is editorially a **Reject** — do NOT
  downgrade it to Major revisions to match a journal's revise-and-resubmit
  culture; if venue convention matters, note it as a separate sentence, but let
  the scientific call stand.
- **Major revisions** when there are serious flaws BUT the central claim can
  survive reanalysis of the EXISTING data (re-run without the leaky feature,
  redo the stats, add CIs, restructure) with no new data collection.
- **Minor revisions** when issues are real but correctable and none threatens the
  central result.
- **Accept** only when the full text was read and no material issue remains.

Never rate above what the available evidence supports: if `Full text: No`, or if
any lens did not report (a *partial* run), the verdict is capped — a paper you
could not fully read, or fully review, cannot be Accepted, and a decisive
Reject-level defect found by even one reporting lens still governs.

**Synthesis rules:** Do not invent content beyond the agents' reports. Where two
lenses disagree, resolve into major/minor comments and, if the tension is
genuine and unresolved, state it plainly in the body.
