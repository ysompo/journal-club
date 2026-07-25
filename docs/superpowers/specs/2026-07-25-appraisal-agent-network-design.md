# Design: Article-Review Agent Network

**Date:** 2026-07-25
**Status:** Approved (design), pending implementation plan
**Branch:** `claude/article-review-agents-86hzih`

## Purpose

Provide a set of Claude Code subagents that produce a rigorous, peer-review-style
critique of a single academic/medical article for journal-club preparation. The
user runs one command against a PDF they have already uploaded and receives one
coherent review with comments and a final decision.

This is developer/personal tooling (Claude Code subagents in `.claude/`), not a
feature shipped inside the Flask app. Nothing is written to the app DB.

## Scope

- **In scope:** deep multi-lens review of ONE paper at a time; seven specialist
  agents; a thin orchestration command; synthesis into a peer-review report
  printed to the terminal.
- **Out of scope:** batch triage across many papers; DOI resolution / PDF
  download automation (the user uploads the PDF); persistence to
  `journal_club.db` or the reading list; any change to the Flask app.
- **Web access:** exactly ONE agent (`appraisal-novelty`) may search the web,
  solely to place the paper's claimed contribution against existing literature.
  The other six agents are strictly paper-only.

## Substrate constraints (fixed by Claude Code)

These shaped the architecture and must be respected by the plan:

1. **Subagents start cold.** Each subagent gets only its prompt + the PDF path;
   it does not see the conversation or sibling agents' output.
2. **No peer-to-peer.** Agents cannot message each other. All cross-agent
   reasoning (agreement, conflict, synthesis) happens at the hub (main thread).
3. **No nested spawning.** Only the main thread spawns `Task` subagents; a
   subagent cannot fan out to sub-subagents. Therefore the orchestrator is the
   main thread driven by a slash command, NOT an "orchestrator agent."

## Architecture

Hub-and-spoke:

```
/appraise <pdf-path>            (main thread = hub)
      │  validate path is an existing PDF
      ├──▶ appraisal-methodologist      ┐
      ├──▶ appraisal-statistician       │
      ├──▶ appraisal-claims-auditor     │  7 Task subagents,
      ├──▶ appraisal-clinical-relevance │  dispatched in parallel,
      ├──▶ appraisal-integrity          │  each given the same PDF path
      ├──▶ appraisal-writing            │  (novelty may also search the web)
      └──▶ appraisal-novelty  (web)     ┘
      │  collect 7 structured reports
      ▼
   synthesis (hub) ──▶ peer-review report printed to terminal
```

## Components

### The seven spoke agents

All are `.claude/agents/<name>.md`, read-only. Six use tools `Read, Grep, Glob,
Bash` and are paper-only (no web). The seventh, `appraisal-novelty`, additionally
gets `WebSearch, WebFetch`. Each has exactly one job so lenses do not overlap and
produce contradictory verdicts.

| Agent | Owns | Does NOT do |
|---|---|---|
| `appraisal-methodologist` | Study-design classification; framework selection + justification (CONSORT/STROBE/PRISMA/STARD/CARE/ARRIVE/TRIPOD); bias & internal validity; GRADE certainty | Claims-vs-evidence; deep stats; COI/ethics |
| `appraisal-statistician` | Power/sample size; multiplicity; effect size vs. p-values; test appropriateness; missing-data handling; results-integrity (do the numbers agree?) | Design framework; clinical meaning |
| `appraisal-claims-auditor` | Extract headline conclusions; test each against Results; flag overreach, spin, causal language from non-causal designs, overgeneralization | Methods quality; stats mechanics |
| `appraisal-clinical-relevance` | Applicability to practice; population; patient-important vs. surrogate outcomes; actionability | Methods/stats verdicts; novelty vs. literature |
| `appraisal-integrity` | Funding source & conflicts of interest; IRB/ethics approval & consent; pre-registration & protocol adherence (outcome switching vs. registry); data/code availability | Scientific validity of the results |
| `appraisal-writing` | Prose coherence & clarity (unreadable/ambiguous sentences); internal inconsistencies between sections; undefined acronyms/terms; figure/table-vs-text mismatches; typos & grammar. Leads with clarity; typos secondary since papers are usually copyedited | Scientific validity; statistics; claims |
| `appraisal-novelty` *(web-enabled)* | The paper's claimed contribution vs. existing literature: is it novel, incremental, or redundant? Finds prior/similar work, related trials, existing reviews. **Only web-enabled agent.** | Methods/stats/claims validity; clinical applicability |

`appraisal-methodologist` is the **refactor** of the existing
`.claude/agents/critical-appraisal.md`: claim-checking and deep-stats
responsibilities are removed (moved to the auditor and statistician), leaving a
focused methodology lens. The old file is renamed accordingly.

Each agent returns its own structured report (design-, stats-, claims-,
relevance-, integrity-, writing-, novelty-specific), including an explicit
**"could not assess"** list. Agents must anchor findings to the paper
(section/page) and never confabulate; unverifiable items go to "could not
assess," not into findings.

**`appraisal-novelty` web rules:** every novelty claim ("X already reported
this") must cite a real URL the agent actually retrieved via WebFetch — never a
citation from memory. If web is unavailable (proxy failure, no results), it
falls back to a paper-only judgment of the *stated* contribution and explicitly
flags that it could not verify against the live literature.

### The hub command

`.claude/commands/appraise.md` — a project slash command that:

1. Takes one argument: a path to an already-uploaded PDF.
2. Validates the path exists and is a readable PDF; if not, stops and asks.
3. Dispatches the seven agents in parallel via `Task`, each given the same
   absolute path.
4. Collects the seven reports.
5. Synthesizes them into the peer-review output (below) using a fixed template
   embedded in the command, so every paper gets an identical report shape.
6. Prints the report to the terminal.

The command performs orchestration only — no DOI resolution, no download.

## Output format (peer-review report, terminal only)

```
# Review: <title>
Source: <pdf-path>   |   Full text: Yes/No

## Summary
<2–3 sentences: what the paper did and found, incl. primary result + effect>

## Assessment
<narrative: design appropriateness, framework used, overall credibility>

## Major comments
1. <substantive issue that would change interpretation> ...

## Minor comments
1. <smaller issue> ...

## Writing & presentation
- **Clarity/coherence:** <ambiguous sentence, contradiction between sections, undefined term> ...
- **Typos & grammar:** <line-referenced list; may be "none of note">

## Unable to assess
- <item the agents could not evaluate from the text>

## Final decision
**<Accept / Minor revisions / Major revisions / Reject>.**
<one-paragraph justification, incl. GRADE-style certainty>
```

Mapping of lenses → sections: methodologist → Assessment + design comments;
statistician → stats major/minor comments; claims auditor → conclusion/spin
comments; clinical relevance → effect-size/patient-importance framing in the
decision; integrity → COI/ethics/registration comments (major if they threaten
validity, minor otherwise); writing → the dedicated Writing & presentation
section (kept separate so a typo/clarity list never drowns the scientific
comments; a clarity issue is promoted to a Major comment only when it makes a
result genuinely uninterpretable); novelty → the Assessment (framing the paper's
contribution) and, when the claimed novelty is contradicted by cited prior work,
a Major comment.

Verdict vocabulary: **peer-review style** — Accept / Minor revisions /
Major revisions / Reject.

## Failure handling (honest degradation)

- **PDF missing/unreadable** → stop before dispatch; ask the user for a valid path.
- **Abstract-only / full text unavailable** → header shows `Full text: No`; the
  verdict is explicitly caveated (cannot Accept a paper that could not be fully
  read). Individual agents already refuse to fabricate a full appraisal.
- **An agent returns nothing / errors** → synthesis notes which lens is missing
  and marks the decision *partial*; the lens is never silently dropped.
- **Novelty web unavailable** → the novelty lens degrades to a paper-only
  contribution judgment and flags it could not verify against live literature;
  the run still completes.
- **Agents conflict** → hub resolves into major/minor comments; genuine
  unresolved tension is stated in the review body rather than smoothed away.

## Testing / verification

These are prompt artifacts; verification is human judgment on known papers, not
unit tests.

- **Run #1:** a paper the user knows well → judge framework justification,
  honesty of "Unable to assess," and zero confabulation.
- **Run #2:** a paper of a different design (e.g. observational → must switch to
  STROBE, not default to CONSORT) → confirms the methodologist re-classifies.

## Files

- `.claude/agents/appraisal-methodologist.md` (renamed/refactored from
  `critical-appraisal.md`)
- `.claude/agents/appraisal-statistician.md` (new)
- `.claude/agents/appraisal-claims-auditor.md` (new)
- `.claude/agents/appraisal-clinical-relevance.md` (new)
- `.claude/agents/appraisal-integrity.md` (new)
- `.claude/agents/appraisal-writing.md` (new)
- `.claude/agents/appraisal-novelty.md` (new; adds `WebSearch, WebFetch` tools)
- `.claude/commands/appraise.md` (new)
- `.gitignore` already un-ignores `.claude/agents/`; add `!.claude/commands/`
  so the command is tracked too.
