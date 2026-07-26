---
description: Run the 8-agent article-review network on an uploaded PDF and print a point-by-point Comments to the Authors review letter.
argument-hint: <path-to-pdf>
---

You are orchestrating an article appraisal. The PDF path is: $ARGUMENTS

1. **Validate.** If `$ARGUMENTS` is empty, ask for a PDF path and stop. Run
   `test -f "$ARGUMENTS" && file "$ARGUMENTS"` — if the file does not exist or is
   not a PDF, tell the user and stop. Do NOT dispatch any agent until the path is valid.

2. **Fan out (in parallel, one message, eight Task calls).** Dispatch all eight
   agents, each with the same absolute PDF path in its prompt:
   appraisal-methodologist, appraisal-statistician, appraisal-claims-auditor,
   appraisal-clinical-relevance, appraisal-integrity, appraisal-writing,
   appraisal-novelty, appraisal-references.

3. **Collect** all eight reports. If an agent returns nothing, note which lens is
   missing and mark the final decision *partial* — never silently drop a lens.

4. **Synthesize** into a point-by-point **Comments to the Authors** review letter
   and print exactly this structure to the terminal. This author-facing letter —
   numbered points, each one actionable and anchored to a section/page/table — is
   the deliverable of this command. Address the authors directly and
   constructively throughout ("Please…" / "The authors should…"), turning each
   lens's findings into changes they can act on rather than a verdict about them.
   For `<title>`, use the paper's title as quoted by whichever agent surfaced it
   (e.g. the claims-auditor quotes headline conclusions and often the title;
   the methodologist and references lenses also see it) — if no agent
   surfaced a title, fall back to the PDF filename.

   # Comments to the Authors — <title>
   Source: <path>   |   Full text read: Yes/No

   <One short opening paragraph to the authors: thank them, and restate in one or
   two sentences what the paper did and found (primary result + effect) to show it
   was read in full.>

   ## Overall recommendation
   **<Accept / Minor revisions / Major revisions / Reject>.** <2–4 sentences,
   addressed to the authors: apply the Editorial decision rule below, state the
   deciding salvageability question and your answer, and give GRADE-style
   certainty of the current evidence.>

   ## Major points
   Numbered. Each is ONE substantive issue that changes interpretation — drawn from
   the statistician, claims-auditor, methodologist, integrity, clinical-relevance,
   and novelty lenses (plus any clarity issue that makes a result uninterpretable).
   For each: state the problem, anchor it (section/page/table), and give a
   concrete, actionable request the authors can act on.
   1. <problem — anchor — requested change>

   ## Minor points
   Numbered smaller issues, each anchored and paired with a concrete fix.
   1. <issue — anchor — requested change>

   ## Writing & presentation
   - Clarity/coherence: <issues that impede comprehension, or "reads clearly">
   - Typos & grammar: <line-referenced list, or "none of note">

   ## Citations
   Verified <n>/<total>.
   - Discrepancy: <ref> — <what disagrees> (retrieved: <DOI/URL>)
   - ⚠ Please verify: <ref as printed> — not located after DOI + title/author search
   (or, if clean: "Bibliography checks out; <n>/<total> verified.")

   ## Points we could not assess (please provide)
   Author-facing requests for what would let a reviewer finish the appraisal — the
   union of every lens's "could not assess" (e.g. numeric values for figure-only
   results, the missing supplementary table, whether nested CV was used).
   ("- none" if empty.)

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

Never rate above what the available evidence supports: if `Full text read: No`,
or if any lens did not report (a *partial* run), the recommendation is capped — a
paper you could not fully read, or fully review, cannot be Accepted, and a
decisive Reject-level defect found by even one reporting lens still governs.

**Synthesis rules:** Do not invent content beyond the agents' reports. Where two
lenses disagree, resolve into major/minor comments and, if the tension is
genuine and unresolved, state it plainly in the body.
