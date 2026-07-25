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
