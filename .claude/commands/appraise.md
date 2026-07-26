---
description: Run the 8-agent article-review network on an uploaded PDF and print a peer-review report.
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
   (from novelty), overall credibility>

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
   <one-paragraph justification, incl. GRADE-style certainty>

**Synthesis rules:** Do not invent content beyond the agents' reports. Where two
lenses disagree, resolve into major/minor comments and, if the tension is
genuine and unresolved, state it plainly in the body. If `Full text: No`, caveat
the verdict explicitly (a paper you could not fully read cannot be Accepted).
