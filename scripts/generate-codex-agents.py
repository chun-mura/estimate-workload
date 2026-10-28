#!/usr/bin/env python3
"""Generate Codex custom-agent TOML from agents/*.md.

    python3 scripts/generate-codex-agents.py
    python3 scripts/generate-codex-agents.py --check

Emits only the three keys Codex requires: name, description, developer_instructions.
The spawn name is <prefix>-<frontmatter name> so it does not collide with Codex's
example reviewer or other plugins. Claude-only frontmatter (model, tools) is dropped.
"""
import os
import sys

PREFIX = "estimate"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_DIR = os.path.join(ROOT, "agents")
OUT_DIR = os.path.join(ROOT, ".codex", "agents")


def parse_agent_md(path):
    text = open(path, encoding="utf-8").read()
    if not text.startswith("---\n"):
        raise SystemExit("%s: missing frontmatter" % path)
    rest = text[4:]
    end = rest.find("\n---\n")
    if end < 0:
        raise SystemExit("%s: unterminated frontmatter" % path)
    fm_text, body = rest[:end], rest[end + 5 :]
    data = {}
    for line in fm_text.splitlines():
        if not line or line.startswith("#"):
            continue
        key, sep, val = line.partition(":")
        if not sep:
            raise SystemExit("%s: bad frontmatter line: %s" % (path, line))
        data[key.strip()] = val.strip()
    name = data.get("name")
    description = data.get("description")
    if not name or not description:
        raise SystemExit("%s: frontmatter needs name and description" % path)
    return name, description, body.strip() + "\n"


def toml_multiline(value):
    body = value.replace("\\", "\\\\").replace('"""', '\\"""')
    if not body.endswith("\n"):
        body += "\n"
    return '"""\n%s"""' % body


def render(name, description, body):
    spawn = "%s-%s" % (PREFIX, name)
    return (
        "name = %s\n" % toml_quote(spawn)
        + "description = %s\n" % toml_multiline(description)
        + "developer_instructions = %s\n" % toml_multiline(body)
    )


def toml_quote(value):
    return '"%s"' % (
        value.replace("\\", "\\\\").replace('"', '\\"')
    )


def expected_outputs():
    outputs = {}
    for filename in sorted(os.listdir(AGENTS_DIR)):
        if not filename.endswith(".md"):
            continue
        path = os.path.join(AGENTS_DIR, filename)
        name, description, body = parse_agent_md(path)
        dest_name = "%s-%s.toml" % (PREFIX, name)
        outputs[dest_name] = render(name, description, body)
    if not outputs:
        raise SystemExit("no agents/*.md found")
    return outputs


def write_outputs(outputs):
    os.makedirs(OUT_DIR, exist_ok=True)
    for filename, text in outputs.items():
        path = os.path.join(OUT_DIR, filename)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)


def check_outputs(outputs):
    stale = []
    for filename, text in outputs.items():
        path = os.path.join(OUT_DIR, filename)
        if not os.path.isfile(path):
            stale.append("missing %s" % path)
            continue
        current = open(path, encoding="utf-8").read()
        if current != text:
            stale.append("stale %s" % path)
    extra = []
    if os.path.isdir(OUT_DIR):
        for filename in sorted(os.listdir(OUT_DIR)):
            if filename.endswith(".toml") and filename not in outputs:
                extra.append("unexpected %s" % os.path.join(OUT_DIR, filename))
    problems = stale + extra
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print("codex-agents generate: OK (%d files)" % len(outputs))
    return 0


def main(argv):
    check = False
    for arg in argv[1:]:
        if arg == "--check":
            check = True
        else:
            raise SystemExit("usage: generate-codex-agents.py [--check]")
    outputs = expected_outputs()
    if check:
        return check_outputs(outputs)
    write_outputs(outputs)
    print("wrote %d files to %s" % (len(outputs), OUT_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
