---
description: Run the 10-agent article-review network on an uploaded PDF and print a point-by-point Comments to the Authors review letter.
argument-hint: <path-to-pdf>
---

You are orchestrating an article appraisal. The PDF path is: $ARGUMENTS

1. **Validate.** If `$ARGUMENTS` is empty, ask for a PDF path and stop. Run
   `test -f "$ARGUMENTS" && file "$ARGUMENTS"` — if the file does not exist or is
   not a PDF, tell the user and stop. Do NOT dispatch any agent until the path is valid.

2. **Triage (adaptive lens selection — you are the manager).** Before
   dispatching, read enough of the PDF yourself (abstract, the Methods headings,
   and a scan of the section structure) to classify the paper: study design,
   quantitative vs. purely qualitative/theoretical, clinical vs. basic-science,
   and whether it has a substantive bibliography. Then choose which lenses to run:
   - **Always run:** appraisal-methodologist, appraisal-claims-auditor,
     appraisal-integrity, appraisal-writing, appraisal-plausibility,
     appraisal-scope.
   - **appraisal-statistician:** run unless the paper contains no quantitative
     analysis at all (pure qualitative/theoretical).
   - **appraisal-clinical-relevance:** run for clinical/applied papers; skip only
     when there is no clinical or applied claim whatsoever.
   - **appraisal-novelty and appraisal-references (web-enabled):** run when web
     access is available. If a quick check shows egress is blocked (e.g. a 403
     from the proxy on a test fetch), you may still run them but note they will
     degrade to "could not verify," or skip them with that reason.
   **When in doubt, run the lens.** A deliberately skipped lens is NOT a *partial*
   run — it is an intentional skip recorded with a one-line reason.

3. **Fan out (in parallel, one message, one Task call per selected lens — up to
   ten).** Dispatch each selected agent with the same absolute PDF path in its
   prompt; never dispatch a lens you decided to skip. Full roster:
   appraisal-methodologist, appraisal-statistician, appraisal-claims-auditor,
   appraisal-clinical-relevance, appraisal-integrity, appraisal-writing,
   appraisal-novelty, appraisal-references, appraisal-plausibility,
   appraisal-scope.

4. **Collect** every dispatched report. A lens you *dispatched* that returns
   nothing is a **missing** lens → mark the recommendation *partial* and name it.
   A lens you deliberately **skipped** in triage is not missing — record it under
   "Lenses run" as skipped-with-reason. Never silently drop a dispatched lens.

5. **Synthesize** into a point-by-point **Comments to the Authors** review letter
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
   Lenses run: <n>/10 (<list any skipped as "skipped: <lens> — <reason>", or "all applicable">)

   <One short opening paragraph to the authors: thank them, and restate in one or
   two sentences what the paper did and found (primary result + effect) to show it
   was read in full.>

   ## Overall recommendation
   **<Accept / Minor revisions / Major revisions / Reject>.** <2–4 sentences,
   addressed to the authors: apply the Editorial decision rule below, state the
   deciding salvageability question and your answer, and give GRADE-style
   certainty of the current evidence. Weigh the soundness of the clinical/
   biological rationale and background (from the plausibility lens) alongside
   design and statistics.>

   ## Major points
   Numbered. Each is ONE substantive issue that changes interpretation — drawn from
   the statistician, claims-auditor, methodologist, integrity, clinical-relevance,
   novelty, and plausibility lenses (plus any clarity issue that makes a result
   uninterpretable). A weak clinical rationale, an absent or implausible mechanism,
   or a domain-implausible key predictor is a Major point.
   For each: state the problem, anchor it (section/page/table), and give a
   concrete, actionable request the authors can act on.
   1. <problem — anchor — requested change>

   ## Minor points
   Numbered smaller issues, each anchored and paired with a concrete fix.
   1. <issue — anchor — requested change>

   ## Writing & presentation
   - Clarity/coherence: <issues that impede comprehension, or "reads clearly">
   - Typos & grammar: <line-referenced list, or "none of note">

   ## Structure & scope
   From the scope lens: length vs. content, breadth (too broad/narrow), section
   balance, and article-type fit — each anchored to a section, never a vibe.
   ("- well-proportioned; no structural concerns" if clean.)

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

6. **Quality-control pass (manager, before printing).** Re-read the raw lens
   reports against your drafted letter and check: (a) every Serious-concern or
   load-bearing finding made it into a Major/Minor point or the recommendation —
   nothing dropped; (b) genuine cross-lens disagreements were surfaced, not
   smoothed away; (c) the union of "could not assess" items is complete; (d) the
   recommendation follows the Editorial decision rule and is capped correctly for
   any partial run; (e) "Lenses run" honestly lists skips. Fix the letter for any
   gap you find, then print. This QC pass is silent — only the final letter is
   printed.
