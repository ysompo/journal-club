# Article-Review Agent Network Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an 8-agent Claude Code subagent network plus a `/appraise` command that turns one uploaded PDF into a single peer-review-style report printed to the terminal.

**Architecture:** Hub-and-spoke. A thin `/appraise` slash command (main thread = hub) validates a PDF path, dispatches eight specialist subagents in parallel via `Task`, collects their reports, and synthesizes them into one peer-review report. Six agents are paper-only; two (`appraisal-novelty`, `appraisal-references`) additionally get web tools. Subagents never see each other's output — all reconciliation happens at the hub.

**Tech Stack:** Claude Code subagents (`.claude/agents/*.md`), a project slash command (`.claude/commands/appraise.md`), Python 3.11 + PyYAML for a structural validator, pytest for the validator's tests. No changes to the Flask app.

## Global Constraints

- **Branch:** `claude/article-review-agents-86hzih`. Never push elsewhere.
- **Commit identity:** `git config user.email noreply@anthropic.com && git config user.name Claude` before committing.
- **Every commit message ends with this trailer (verbatim):**
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01T8pvryA5zsqQVhjc1TEFiE
  ```
- **Agent file location:** `.claude/agents/<name>.md`. The `name:` in frontmatter MUST equal the filename without `.md`.
- **Frontmatter keys:** `name`, `description`, `tools`. Do NOT set `model` (agents inherit the session model).
- **Tools — paper-only agents (6):** `tools: Read, Grep, Glob, Bash`.
- **Tools — web agents (2):** `tools: Read, Grep, Glob, Bash, WebSearch, WebFetch`.
- **No confabulation (all agents):** every finding is anchored to the paper (section name and, where visible, page/figure/table). Anything not verifiable from the text goes under `### Could not assess`, never into findings. Never invent values (power calcs, registrations, citations).
- **Shared return schema (every agent's report to the hub ends with exactly this shape):**
  ```
  ## Lens: <lens name>
  **Verdict:** <one line>

  ### Findings
  - [Adequate|Concern|Serious concern|Not reported] <finding> — <section/page>

  ### Could not assess
  - <item>   (or: "- none")
  ```
  The two web agents append a final `### Sources` list of URLs they actually retrieved.
- **Shared input-handling block (paste into every agent, under a `## Input` heading):**
  ```
  You are given a path to a PDF (or a DOI/title). If only an identifier is given,
  locate the file: PDFs are saved to the app's output_dir (see config.yaml /
  OUTPUT_DIR) as slugify(article_url).pdf, and recorded in journal_club.db
  (articles table). Use Glob on the output dir for *.pdf, or Bash `sqlite3
  journal_club.db` to match title/DOI -> pdf_path, then Read the PDF. Read the
  FULL text (Methods, Results, supplements) via page ranges for long PDFs — never
  appraise from the abstract alone. If you cannot obtain full text, say so and do
  not fabricate an appraisal.
  ```
- **Verdict vocabulary (final report only):** Accept / Minor revisions / Major revisions / Reject.
- **Validator gate:** every agent/command file must pass `python3 scripts/validate_appraisal_agent.py <file> [flags]` (built in Task 1) before its task's commit.

---

### Task 1: Structural validator + tests

**Files:**
- Create: `scripts/validate_appraisal_agent.py`
- Test: `tests/test_validate_appraisal_agent.py`

**Interfaces:**
- Produces: `validate(path: str, require_web: bool = False, required: list[str] | None = None) -> list[str]` returning a list of human-readable error strings (empty = valid). CLI: `python3 scripts/validate_appraisal_agent.py <file> [--web] [--require "SUBSTR" ...]`, exit 0 if valid, 1 otherwise.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_validate_appraisal_agent.py
import textwrap
from scripts.validate_appraisal_agent import validate

GOOD = textwrap.dedent("""\
    ---
    name: appraisal-demo
    description: A demo agent.
    tools: Read, Grep, Glob, Bash
    ---
    ## Input
    body text
    ### Findings
    - [Adequate] ok — Methods p.2
    ### Could not assess
    - none
    """)

def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return str(p)

def test_good_file_has_no_errors(tmp_path):
    path = _write(tmp_path, "appraisal-demo.md", GOOD)
    assert validate(path) == []

def test_name_must_match_filename(tmp_path):
    path = _write(tmp_path, "wrong-name.md", GOOD)
    errors = validate(path)
    assert any("name" in e for e in errors)

def test_missing_tool_flagged(tmp_path):
    text = GOOD.replace("tools: Read, Grep, Glob, Bash", "tools: Read")
    path = _write(tmp_path, "appraisal-demo.md", text)
    errors = validate(path)
    assert any("Grep" in e for e in errors)

def test_web_flag_requires_web_tools(tmp_path):
    path = _write(tmp_path, "appraisal-demo.md", GOOD)
    errors = validate(path, require_web=True)
    assert any("WebSearch" in e for e in errors)

def test_required_substring_missing(tmp_path):
    path = _write(tmp_path, "appraisal-demo.md", GOOD)
    errors = validate(path, required=["### Sources"])
    assert any("### Sources" in e for e in errors)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pip install pytest && python3 -m pytest tests/test_validate_appraisal_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: scripts.validate_appraisal_agent`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/validate_appraisal_agent.py
"""Structural validator for appraisal agent/command markdown files."""
import argparse
import os
import sys
import yaml

PAPER_TOOLS = ["Read", "Grep", "Glob", "Bash"]
WEB_TOOLS = ["WebSearch", "WebFetch"]


def _split_frontmatter(text):
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    return parts[1], parts[2]


def validate(path, require_web=False, required=None):
    errors = []
    text = open(path, encoding="utf-8").read()
    fm_text, body = _split_frontmatter(text)
    if fm_text is None:
        return ["no YAML frontmatter (--- ... ---) found"]
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as e:
        return [f"frontmatter is not valid YAML: {e}"]

    stem = os.path.basename(path)[:-3] if path.endswith(".md") else os.path.basename(path)
    if fm.get("name") != stem:
        errors.append(f"name '{fm.get('name')}' must equal filename stem '{stem}'")
    if not fm.get("description"):
        errors.append("missing or empty description")

    tools = fm.get("tools") or ""
    for t in PAPER_TOOLS:
        if t not in tools:
            errors.append(f"tools missing required tool '{t}'")
    if require_web:
        for t in WEB_TOOLS:
            if t not in tools:
                errors.append(f"web agent tools missing '{t}'")

    for sub in (required or []):
        if sub not in body:
            errors.append(f"body missing required content: '{sub}'")
    return errors


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--web", action="store_true")
    ap.add_argument("--require", action="append", default=[])
    args = ap.parse_args(argv)
    errors = validate(args.path, require_web=args.web, required=args.require)
    if errors:
        print(f"INVALID {args.path}:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"OK {args.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Also create empty `scripts/__init__.py` if imports require it (the test imports `scripts.validate_appraisal_agent`; add `scripts/__init__.py` so it is a package).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_validate_appraisal_agent.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git config user.email noreply@anthropic.com && git config user.name Claude
git add scripts/validate_appraisal_agent.py scripts/__init__.py tests/test_validate_appraisal_agent.py
git commit  # message: "test: add structural validator for appraisal agents" + trailer
```

---

### Task 2: `appraisal-methodologist` (refactor of `critical-appraisal`)

**Files:**
- Rename+rewrite: `.claude/agents/critical-appraisal.md` -> `.claude/agents/appraisal-methodologist.md`

**Interfaces:**
- Produces: a subagent whose report follows the shared return schema, `## Lens: Methodology`.

**Content requirements (the rewritten body MUST contain):**
- Frontmatter: `name: appraisal-methodologist`, a description covering design classification + framework selection/justification + bias/GRADE, `tools: Read, Grep, Glob, Bash`.
- The shared `## Input` block.
- `## Phase 1 — Classify the study design` — the design list and "state design + textual evidence" rule (reuse the existing critical-appraisal content).
- `## Phase 2 — Select and JUSTIFY the framework` — the CONSORT/STROBE/PRISMA/STARD/CARE/ARRIVE/TRIPOD mapping table and one-sentence justification rule.
- `## Phase 3 — Bias & internal validity` — randomization/allocation/blinding (RCT), confounding/selection/attrition (observational), plus GRADE certainty.
- **REMOVE** the old claim-vs-evidence phase and the deep-statistics domain (these now belong to `appraisal-claims-auditor` and `appraisal-statistician`). The methodologist may note "see statistics/claims lenses" but must not issue those verdicts.
- End with the shared return schema (`## Lens: Methodology`).

- [ ] **Step 1: Rename the file**

```bash
git mv .claude/agents/critical-appraisal.md .claude/agents/appraisal-methodologist.md
```

- [ ] **Step 2: Rewrite the body** per the content requirements above (edit frontmatter `name`, strip claims + deep-stats sections, keep design/framework/bias/GRADE, append the shared return schema).

- [ ] **Step 3: Validate**

Run:
```bash
python3 scripts/validate_appraisal_agent.py .claude/agents/appraisal-methodologist.md \
  --require "## Phase 1" --require "Select and JUSTIFY" --require "## Lens: Methodology" \
  --require "Could not assess"
```
Expected: `OK ...`. If INVALID, fix and re-run.

- [ ] **Step 4: Confirm claims/stats were removed**

Run: `grep -in "claim vs\|p-value\|multiplicity" .claude/agents/appraisal-methodologist.md || echo "clean"`
Expected: `clean` (or only incidental mentions that defer to other lenses).

- [ ] **Step 5: Commit**

```bash
git add .claude/agents/appraisal-methodologist.md
git commit  # "refactor: narrow critical-appraisal into appraisal-methodologist" + trailer
```

---

### Task 3: `appraisal-statistician`

**Files:**
- Create: `.claude/agents/appraisal-statistician.md`

**Content requirements:**
- Frontmatter: `name: appraisal-statistician`, description (stats-only scrutiny), `tools: Read, Grep, Glob, Bash`.
- Shared `## Input` block.
- `## What to scrutinize` covering: a-priori sample-size/power; multiplicity across secondary endpoints; effect size + confidence intervals vs. bare p-values; appropriateness of the statistical tests to the data; missing-data handling (e.g. LOCF vs. multiple imputation, sensitivity analyses); results-integrity (do numbers in text, tables, and figures agree; is participant flow accounted for).
- Explicit rule: does NOT judge study design framework or clinical meaning — defer those.
- Shared return schema (`## Lens: Statistics`).

- [ ] **Step 1: Write the file** per requirements above.
- [ ] **Step 2: Validate**

Run:
```bash
python3 scripts/validate_appraisal_agent.py .claude/agents/appraisal-statistician.md \
  --require "## Lens: Statistics" --require "multiplicity" --require "Could not assess"
```
Expected: `OK ...`.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/appraisal-statistician.md
git commit  # "feat: add appraisal-statistician agent" + trailer
```

---

### Task 4: `appraisal-claims-auditor`

**Files:**
- Create: `.claude/agents/appraisal-claims-auditor.md`

**Content requirements:**
- Frontmatter: `name: appraisal-claims-auditor`, description (claim-vs-evidence), `tools: Read, Grep, Glob, Bash`.
- Shared `## Input` block.
- `## Method`: extract the paper's 2–4 headline conclusions (Abstract/Discussion), then test each against what the Results actually show. Flag: overreach beyond the data, spin (emphasizing a non-significant trend), causal language from non-causal designs, and generalization beyond the studied population. For each: quote the claim, state supported / overreach / spin, and give the reason.
- Explicit rule: does NOT re-derive statistics or re-classify design.
- Shared return schema (`## Lens: Claims vs evidence`); findings list uses the claim → assessment format.

- [ ] **Step 1: Write the file** per requirements.
- [ ] **Step 2: Validate**

Run:
```bash
python3 scripts/validate_appraisal_agent.py .claude/agents/appraisal-claims-auditor.md \
  --require "## Lens: Claims vs evidence" --require "overreach" --require "Could not assess"
```
Expected: `OK ...`.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/appraisal-claims-auditor.md
git commit  # "feat: add appraisal-claims-auditor agent" + trailer
```

---

### Task 5: `appraisal-clinical-relevance`

**Files:**
- Create: `.claude/agents/appraisal-clinical-relevance.md`

**Content requirements:**
- Frontmatter: `name: appraisal-clinical-relevance`, description (the "so what?" lens), `tools: Read, Grep, Glob, Bash`.
- Shared `## Input` block.
- `## What to judge`: applicability to real-world practice; population & setting representativeness; patient-important outcomes vs. surrogate endpoints; actionability (does it change what a clinician does). Paper-only.
- Explicit rule: does NOT assess novelty-vs-literature (that is `appraisal-novelty`), methods, or statistics.
- Shared return schema (`## Lens: Clinical relevance`).

- [ ] **Step 1: Write the file** per requirements.
- [ ] **Step 2: Validate**

Run:
```bash
python3 scripts/validate_appraisal_agent.py .claude/agents/appraisal-clinical-relevance.md \
  --require "## Lens: Clinical relevance" --require "surrogate" --require "Could not assess"
```
Expected: `OK ...`.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/appraisal-clinical-relevance.md
git commit  # "feat: add appraisal-clinical-relevance agent" + trailer
```

---

### Task 6: `appraisal-integrity`

**Files:**
- Create: `.claude/agents/appraisal-integrity.md`

**Content requirements:**
- Frontmatter: `name: appraisal-integrity`, description (research integrity & ethics), `tools: Read, Grep, Glob, Bash`.
- Shared `## Input` block.
- `## What to check`: funding source & declared conflicts of interest; IRB/ethics approval and informed consent; pre-registration & protocol adherence (compare reported primary outcome to any stated registry/protocol — flag outcome switching); data & code availability statements. Paper-only (reads what the paper declares; does not verify registries online).
- Explicit rule: does NOT judge scientific validity of results.
- Shared return schema (`## Lens: Research integrity`).

- [ ] **Step 1: Write the file** per requirements.
- [ ] **Step 2: Validate**

Run:
```bash
python3 scripts/validate_appraisal_agent.py .claude/agents/appraisal-integrity.md \
  --require "## Lens: Research integrity" --require "conflicts of interest" --require "Could not assess"
```
Expected: `OK ...`.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/appraisal-integrity.md
git commit  # "feat: add appraisal-integrity agent" + trailer
```

---

### Task 7: `appraisal-writing`

**Files:**
- Create: `.claude/agents/appraisal-writing.md`

**Content requirements:**
- Frontmatter: `name: appraisal-writing`, description (clarity-first, typos secondary), `tools: Read, Grep, Glob, Bash`.
- Shared `## Input` block.
- `## What to flag`, in priority order: (1) clarity/coherence — unreadable or ambiguous sentences, contradictions between sections, undefined acronyms/terms, figure/table-vs-text mismatches; (2) typos & grammar — a line-referenced list, explicitly allowed to be "none of note" since papers are usually copyedited.
- Rule: only promote a clarity issue toward a Major comment when it makes a result genuinely uninterpretable; otherwise it stays a writing note.
- Shared return schema (`## Lens: Writing & presentation`) — split findings into a Clarity/coherence group and a Typos & grammar group.

- [ ] **Step 1: Write the file** per requirements.
- [ ] **Step 2: Validate**

Run:
```bash
python3 scripts/validate_appraisal_agent.py .claude/agents/appraisal-writing.md \
  --require "## Lens: Writing & presentation" --require "clarity" --require "Could not assess"
```
Expected: `OK ...`.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/appraisal-writing.md
git commit  # "feat: add appraisal-writing agent" + trailer
```

---

### Task 8: `appraisal-novelty` (web-enabled)

**Files:**
- Create: `.claude/agents/appraisal-novelty.md`

**Content requirements:**
- Frontmatter: `name: appraisal-novelty`, description (contribution vs. literature; web-enabled), `tools: Read, Grep, Glob, Bash, WebSearch, WebFetch`.
- Shared `## Input` block.
- `## Method`: identify the paper's claimed contribution; search the web for prior/similar work, related trials, and existing reviews; judge whether the contribution is novel, incremental, or redundant.
- **Web rules (verbatim intent):** every "X already reported this" claim MUST cite a real URL retrieved via WebFetch — never a citation from memory. If web is unavailable or returns nothing, fall back to a paper-only judgment of the *stated* contribution and explicitly flag that it could not verify against live literature.
- Shared return schema (`## Lens: Novelty`) PLUS a final `### Sources` list of retrieved URLs.

- [ ] **Step 1: Write the file** per requirements.
- [ ] **Step 2: Validate (note `--web`)**

Run:
```bash
python3 scripts/validate_appraisal_agent.py .claude/agents/appraisal-novelty.md --web \
  --require "## Lens: Novelty" --require "### Sources" --require "could not verify"
```
Expected: `OK ...`.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/appraisal-novelty.md
git commit  # "feat: add web-enabled appraisal-novelty agent" + trailer
```

---

### Task 9: `appraisal-references` (web-enabled)

**Files:**
- Create: `.claude/agents/appraisal-references.md`

**Content requirements:**
- Frontmatter: `name: appraisal-references`, description (bibliography factual audit; web-enabled), `tools: Read, Grep, Glob, Bash, WebSearch, WebFetch`.
- Shared `## Input` block, plus: extract the reference list from the PDF.
- `## Method`: for each reference, locate it online (try DOI first, then title + first author). Classify **Verified** (found; metadata matches — cite the retrieved DOI/URL), **Discrepancy** (found but year/authors/journal/pages disagree — show both), **Unverified** (could not locate).
- **Guardrail (verbatim intent):** "Not found" is NOT "fabricated." Search coverage is imperfect, so **Unverified means flag and ask the user to verify online — never assert the citation is fake.** Verdicts rest only on sources actually retrieved. If web is unavailable, report that references could not be checked this run.
- Return: a `## Lens: References` section reporting `Verified <n>/<total>`, then a Discrepancy list and an **Unverified — please verify online** list, then `### Sources`.

- [ ] **Step 1: Write the file** per requirements.
- [ ] **Step 2: Validate (note `--web`)**

Run:
```bash
python3 scripts/validate_appraisal_agent.py .claude/agents/appraisal-references.md --web \
  --require "## Lens: References" --require "please verify online" \
  --require "Not found" --require "### Sources"
```
Expected: `OK ...`.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/appraisal-references.md
git commit  # "feat: add web-enabled appraisal-references agent" + trailer
```

---

### Task 10: `/appraise` command + gitignore + docs

**Files:**
- Create: `.claude/commands/appraise.md`
- Modify: `.gitignore` (add `!.claude/commands/` under the `.claude/*` block)
- Modify: `CLAUDE.md` (add a short "Article-review agents" note; optional but recommended)

**Interfaces:**
- Consumes: all eight agents from Tasks 2–9 (by name).

- [ ] **Step 1: Un-ignore the commands directory**

Edit `.gitignore`: directly beneath the existing `!.claude/agents/` line, add:
```
!.claude/commands/
```
Verify:
```bash
touch .claude/commands/.keep && git check-ignore -v .claude/commands/.keep; echo "exit=$?  (want exit=1)"
rm .claude/commands/.keep
```
Expected: `exit=1` (no longer ignored).

- [ ] **Step 2: Write the command file**

Create `.claude/commands/appraise.md` with this content:

````markdown
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

4. **Synthesize** into exactly this report and print it to the terminal:

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
````

- [ ] **Step 3: Validate the command file's frontmatter**

Run:
```bash
python3 - <<'PY'
import yaml
t = open(".claude/commands/appraise.md").read()
fm = yaml.safe_load(t.split("---",2)[1])
assert fm.get("description"), "missing description"
for a in ["appraisal-methodologist","appraisal-statistician","appraisal-claims-auditor",
          "appraisal-clinical-relevance","appraisal-integrity","appraisal-writing",
          "appraisal-novelty","appraisal-references"]:
    assert a in t, f"command does not reference {a}"
print("command OK")
PY
```
Expected: `command OK`.

- [ ] **Step 4: Full-suite regression**

Run: `python3 -m pytest tests/ -v`
Expected: PASS (validator tests + existing config/router tests unaffected).

- [ ] **Step 5: Commit**

```bash
git add .gitignore .claude/commands/appraise.md CLAUDE.md
git commit  # "feat: add /appraise orchestration command for the review network" + trailer
git push -u origin claude/article-review-agents-86hzih
```

---

## Post-build verification (manual — NOT a plan task)

These prompt artifacts have no behavioral unit tests; quality is judged by a human on known papers. After the build, the user runs:

- **Run #1:** `/appraise <known-paper>.pdf` — judge framework justification, honesty of "Unable to assess", zero confabulation, and that references-Unverified reads as "please verify", not "fake".
- **Run #2:** a paper of a *different design* (observational) — confirm the methodologist switches to STROBE rather than defaulting to CONSORT.

Findings from Run #1/#2 drive prompt tuning and the deferred `appraisal-red-team` decision.
