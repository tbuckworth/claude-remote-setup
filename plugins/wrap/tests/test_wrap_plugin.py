#!/usr/bin/env python3
"""Static validation for the wrap plugin.

Checks the things that break silently: manifests that drift from the marketplaces,
frontmatter that stops parsing, relative paths that stop resolving after a rename,
and Codex manifest fields the plugin validator rejects.

Run after touching anything in this plugin:

    python3 plugins/wrap/tests/test_wrap_plugin.py

Stdlib only, so it runs anywhere the repo is checked out.
"""

import json
import re
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PLUGIN_DIR.parent.parent
PLUGIN_NAME = "wrap"

# Fields Codex's plugin validator accepts; anything else is a hard error there.
CODEX_ALLOWED_FIELDS = {
    "id", "name", "version", "description", "skills", "apps",
    "mcpServers", "interface", "author", "homepage", "repository",
    "license", "keywords",
}
CODEX_INTERFACE_REQUIRED = {
    "displayName", "shortDescription", "longDescription",
    "developerName", "category", "capabilities", "defaultPrompt",
}
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)*$")

failures = []


def check(condition, message):
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  FAIL {message}")
        failures.append(message)


def frontmatter(path):
    """Return top-level `key: value` pairs from a markdown file's YAML frontmatter.

    Deliberately minimal -- we only need to know which keys are present and that the
    delimiters are well formed, not to parse arbitrary YAML.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 3)
    if end == -1:
        return None
    keys = {}
    for line in text[4:end].split("\n"):
        if line[:1] in (" ", "\t", "-", "#", ""):
            continue  # nested value, list item, comment, or blank
        if ":" in line:
            key, _, value = line.partition(":")
            keys[key.strip()] = value.strip()
    return keys


def test_claude_manifest():
    print("\nClaude manifest")
    path = PLUGIN_DIR / ".claude-plugin" / "plugin.json"
    check(path.exists(), f"{path.name} exists")
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    check(data.get("name") == PLUGIN_NAME, f"name is '{PLUGIN_NAME}'")
    check(bool(data.get("description")), "description present")
    check(bool(SEMVER.match(data.get("version", ""))), f"version is semver ({data.get('version')})")
    check(isinstance(data.get("author"), dict) and bool(data["author"].get("name")),
          "author.name present")
    return data


def test_codex_manifest(claude_version):
    print("\nCodex manifest")
    path = PLUGIN_DIR / ".codex-plugin" / "plugin.json"
    check(path.exists(), f"{path.name} exists")
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    check(data.get("name") == PLUGIN_NAME, f"name is '{PLUGIN_NAME}'")
    check(bool(SEMVER.match(data.get("version", ""))), f"version is semver ({data.get('version')})")
    check(data.get("version", "").split("+")[0] == claude_version,
          "version base matches the Claude manifest")

    extra = set(data) - CODEX_ALLOWED_FIELDS
    check(not extra, f"no fields rejected by the Codex validator (found: {sorted(extra) or 'none'})")

    check(data.get("skills") == "./skills/", "skills points at ./skills/")
    check(isinstance(data.get("author"), dict) and bool(data["author"].get("name")),
          "author.name present")

    interface = data.get("interface")
    check(isinstance(interface, dict), "interface block present")
    if not isinstance(interface, dict):
        return
    missing = CODEX_INTERFACE_REQUIRED - set(interface)
    check(not missing, f"interface complete (missing: {sorted(missing) or 'none'})")

    prompts = interface.get("defaultPrompt", [])
    check(isinstance(prompts, list) and 1 <= len(prompts) <= 3,
          f"defaultPrompt has 1-3 entries (has {len(prompts)})")
    over = [p for p in prompts if len(p) > 128]
    check(not over, "every defaultPrompt entry is <= 128 chars")
    check(isinstance(interface.get("capabilities"), list) and bool(interface["capabilities"]),
          "capabilities is a non-empty list")


def test_marketplaces(claude_version):
    print("\nMarketplace registration")

    claude_mp = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    entry = next((p for p in claude_mp["plugins"] if p.get("name") == PLUGIN_NAME), None)
    check(entry is not None, "registered in .claude-plugin/marketplace.json")
    if entry:
        check(entry.get("version") == claude_version,
              f"marketplace version matches plugin.json ({entry.get('version')} == {claude_version})")
        check(entry.get("source") == f"./plugins/{PLUGIN_NAME}", "source path correct")
        check(bool(entry.get("description")), "description present")
        check(bool(entry.get("category")), "category present")

    codex_mp = json.loads((REPO_ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
    centry = next((p for p in codex_mp["plugins"] if p.get("name") == PLUGIN_NAME), None)
    check(centry is not None, "registered in .agents/plugins/marketplace.json")
    if centry:
        check(centry.get("source", {}).get("path") == f"./plugins/{PLUGIN_NAME}",
              "Codex source path correct")
        check(bool(centry.get("policy")), "Codex policy present")

    setup_codex = (REPO_ROOT / "setup-codex.sh").read_text(encoding="utf-8")
    check(re.search(rf"MAIN_PLUGINS=\([^)]*\b{PLUGIN_NAME}\b", setup_codex) is not None,
          "listed in setup-codex.sh MAIN_PLUGINS")

    setup_claude = (REPO_ROOT / "setup-plugins.sh").read_text(encoding="utf-8")
    check(re.search(rf'CUSTOM_PLUGINS=\((?:[^)]*\n)*?[^)]*"{PLUGIN_NAME}"', setup_claude) is not None,
          "listed in setup-plugins.sh CUSTOM_PLUGINS")


def test_frontmatter():
    print("\nFrontmatter")
    for path in sorted(PLUGIN_DIR.rglob("*.md")):
        rel = path.relative_to(PLUGIN_DIR)
        # README and references are prose, not loadable components.
        if rel.parts[0] in ("references",) or rel.name == "README.md":
            continue
        keys = frontmatter(path)
        check(keys is not None, f"{rel}: frontmatter delimiters well formed")
        if keys is None:
            continue
        if rel.parts[0] in ("skills", "agents"):
            check("name" in keys, f"{rel}: has name")
            check("description" in keys, f"{rel}: has description")
        if rel.parts[0] == "commands":
            check("description" in keys, f"{rel}: has description")


def test_paths_resolve():
    print("\nInternal path references")
    rel_ref = re.compile(r"\.\./\.\./[A-Za-z0-9._/-]+")
    root_ref = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([A-Za-z0-9._/-]+)")
    seen = 0
    for path in sorted(PLUGIN_DIR.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for ref in set(rel_ref.findall(text)):
            target = (path.parent / ref).resolve()
            seen += 1
            check(target.exists(), f"{path.relative_to(PLUGIN_DIR)} -> {ref}")
        for ref in set(root_ref.findall(text)):
            target = (PLUGIN_DIR / ref).resolve()
            seen += 1
            check(target.exists(), f"{path.relative_to(PLUGIN_DIR)} -> $CLAUDE_PLUGIN_ROOT/{ref}")
    check(seen > 0, "found path references to validate")


def test_agents_referenced_exist():
    print("\nAgents referenced by the workflow")
    text = (PLUGIN_DIR / "commands" / "wrap.md").read_text(encoding="utf-8")
    for name in sorted(set(re.findall(r"`(wrap-[a-z]+)`", text))):
        agent = PLUGIN_DIR / "agents" / f"{name}.md"
        check(agent.exists(), f"{name} referenced in commands/wrap.md has agents/{name}.md")
        if agent.exists():
            keys = frontmatter(agent) or {}
            check(keys.get("name") == name, f"agents/{name}.md frontmatter name matches filename")


def main():
    print(f"Validating {PLUGIN_DIR}")
    claude = test_claude_manifest()
    version = (claude or {}).get("version", "")
    test_codex_manifest(version)
    test_marketplaces(version)
    test_frontmatter()
    test_paths_resolve()
    test_agents_referenced_exist()

    print()
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
