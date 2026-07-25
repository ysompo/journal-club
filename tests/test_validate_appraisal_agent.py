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
