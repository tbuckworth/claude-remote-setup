"""Stage 3: fresh vocabulary (task set, report, hypotheses, open-book, answer-key grading).

Run from the repository root. Python files are rewritten token by token:
  NAME    exact identifier map (NAMES) plus part rules for battery/sidecar/oracle;
          `ceiling` only where it is the task-set config's field (an attribute not called);
  STRING  whole-string literals equal to a key in KEYS or a renamed identifier; path- and
          module-like strings get segment renames (SEGMENTS); prose in strings is NOT touched,
          because some of it is shown to the agent or a judge;
  COMMENT and docstrings: prose rules (PROSE) and identifier renames.
YAML: keys (KEYS), comments (prose), and path-like values (segments). Markdown: prose,
identifiers and segments. Frozen trees are skipped entirely.
"""

from __future__ import annotations

import ast
import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path

ROOT = Path.cwd()
P = "src/training_effects"
FROZEN_PREFIXES = (
    f"{P}/prompts/reports/", f"{P}/prompts/hypotheses/", f"{P}/prompts/shared/",
    f"{P}/prompts/hypothesis_scoring/", f"{P}/prompts/phase1_reports/", f"{P}/prompts/phase2_hypotheses/",
    f"{P}/training/_vendor/",
    "benchmarks/shared/reading/", "benchmarks/shared/checkpoints/",
    "benchmarks/optimisers/ground-truth/", "benchmarks/shared/ground-truth/",
    "tests/support/fixtures/",
)
FROZEN_FILES = {"uv.lock", "LICENSE", "NOTICE"}

MOVES = [
    (f"{P}/benchmark/phase1_reports", f"{P}/benchmark/reports"),
    (f"{P}/benchmark/phase2_hypotheses", f"{P}/benchmark/hypotheses"),
    (f"{P}/reporting/phase1_reports", f"{P}/reporting/reports"),
    (f"{P}/reporting/phase2_hypotheses", f"{P}/reporting/hypotheses"),
    (f"{P}/prompts/phase1_reports", f"{P}/prompts/reports"),
    (f"{P}/prompts/phase2_hypotheses", f"{P}/prompts/hypotheses"),
    (f"{P}/benchmark/ceiling_rounds.py", f"{P}/benchmark/open_book_rounds.py"),
    (f"{P}/benchmark/ceiling_oracle.py", f"{P}/benchmark/answer_key_grading.py"),
    (f"{P}/benchmark/commands/run_e5_battery.py", f"{P}/benchmark/commands/run_task_set.py"),
    (f"{P}/benchmark/commands/launch_e5_battery.py", f"{P}/benchmark/commands/launch_task_set.py"),
    (f"{P}/benchmark/commands/complete_e5_run.py", f"{P}/benchmark/commands/complete_run.py"),
    (f"{P}/benchmark/commands/consolidate_e5_run.py", f"{P}/benchmark/commands/consolidate_run.py"),
    (f"{P}/benchmark/commands/regrade_e5_run.py", f"{P}/benchmark/commands/regrade_run.py"),
    (f"{P}/benchmark/commands/rescore_e5_run.py", f"{P}/benchmark/commands/rescore_run.py"),
    (f"{P}/benchmark/commands/oracle_grade.py", f"{P}/benchmark/commands/grade_answer_keys.py"),
    (f"{P}/reporting/commands/report_e5.py", f"{P}/reporting/commands/reports_markdown.py"),
    (f"{P}/reporting/commands/report_e5_html.py", f"{P}/reporting/commands/results_html.py"),
    (f"{P}/reporting/commands/report_e6.py", f"{P}/reporting/commands/hypotheses_markdown.py"),
    (f"{P}/reporting/commands/export_e6_sidecar.py", f"{P}/reporting/commands/hypotheses_json.py"),
    (f"{P}/reporting/hypotheses/sidecar.py", f"{P}/reporting/hypotheses/json_export.py"),
    ("tests/benchmark/test_e5_runs.py", "tests/benchmark/test_runs.py"),
    ("tests/benchmark/test_run_e5_battery.py", "tests/benchmark/test_run_task_set.py"),
    ("tests/benchmark/test_launch_e5_battery.py", "tests/benchmark/test_launch_task_set.py"),
    ("tests/benchmark/test_complete_e5_run.py", "tests/benchmark/test_complete_run.py"),
    ("tests/benchmark/test_replace_e5_episode_script.py", "tests/benchmark/test_episode_replacement_script.py"),
    ("tests/benchmark/test_ceiling_rounds.py", "tests/benchmark/test_open_book_rounds.py"),
    ("tests/benchmark/test_ceiling_oracle.py", "tests/benchmark/test_answer_key_grading.py"),
    ("tests/benchmark/test_performance_ceiling.py", "tests/benchmark/test_open_book.py"),
    ("tests/benchmark/test_report_battery_research.py", "tests/benchmark/test_report_task_set_research.py"),
    ("tests/benchmark/test_phase1_acceptance.py", "tests/benchmark/test_report_acceptance.py"),
    ("tests/benchmark/test_phase1_contract_drift.py", "tests/benchmark/test_report_contract_drift.py"),
    ("tests/benchmark/test_phase2_grader.py", "tests/benchmark/test_hypotheses_grader.py"),
    ("tests/benchmark/test_phase2_importance.py", "tests/benchmark/test_hypotheses_importance.py"),
    ("tests/benchmark/test_report_task_phase_two_tools.py", "tests/benchmark/test_report_task_hypotheses_tools.py"),
    ("tests/reporting/test_e6_selection.py", "tests/reporting/test_hypotheses_selection.py"),
    ("tests/reporting/test_e6_sidecar.py", "tests/reporting/test_hypotheses_json.py"),
    ("tests/reporting/test_report_e5_html.py", "tests/reporting/test_results_html_command.py"),
    ("tests/reporting/test_analysis_e5.py", "tests/reporting/test_analysis_reports.py"),
    ("tests/reporting/test_analysis_e5_html.py", "tests/reporting/test_results_html.py"),
    ("tests/reporting/test_e5_factory_shape.py", "tests/reporting/test_episode_factory_shape.py"),
    ("tests/reporting/test_phase1_legacy.py", "tests/reporting/test_report_legacy.py"),
    ("tests/reporting/test_phase1_eras.py", "tests/reporting/test_report_eras.py"),
    ("tests/support/e5_factories.py", "tests/support/episode_factories.py"),
    ("tests/support/report_battery_factories.py", "tests/support/report_task_set_factories.py"),
    ("tests/support/phase2_battery_factories.py", "tests/support/hypotheses_task_set_factories.py"),
    ("tests/support/phase2_row_factories.py", "tests/support/hypothesis_row_factories.py"),
    ("tests/support/phase1_acceptance.py", "tests/support/report_acceptance.py"),
    ("tests/support/fixtures/phase1_acceptance", "tests/support/fixtures/report_acceptance"),
    ("tests/support/fixtures/phase1_five_level", "tests/support/fixtures/report_five_level"),
    ("tests/support/fixtures/phase1_legacy", "tests/support/fixtures/report_legacy"),
]

# Path and module segments (inside /- or .-separated strings, and in prose paths).
SEGMENTS = {
    "phase1_reports": "reports", "phase2_hypotheses": "hypotheses",
    "ceiling_rounds": "open_book_rounds", "ceiling_oracle": "answer_key_grading",
    "run_e5_battery": "run_task_set", "launch_e5_battery": "launch_task_set",
    "complete_e5_run": "complete_run", "consolidate_e5_run": "consolidate_run",
    "regrade_e5_run": "regrade_run", "rescore_e5_run": "rescore_run",
    "oracle_grade": "grade_answer_keys",
    "report_e5_html": "results_html", "report_e5": "reports_markdown",
    "report_e6": "hypotheses_markdown", "export_e6_sidecar": "hypotheses_json",
    "sidecar": "json_export",  # the module reporting/hypotheses/sidecar.py
    "e5_factories": "episode_factories", "report_battery_factories": "report_task_set_factories",
    "phase2_battery_factories": "hypotheses_task_set_factories",
    "phase2_row_factories": "hypothesis_row_factories", "phase1_acceptance": "report_acceptance",
    "phase1_five_level": "report_five_level", "phase1_legacy": "report_legacy",
}
for _old, _new in MOVES:
    if _old.startswith("tests/") and _old.endswith(".py"):
        SEGMENTS[Path(_old).stem] = Path(_new).stem

NAMES = {
    **SEGMENTS,
    "e5_runs": "benchmark_runs",
    "phase2_overall": "hypothesis_score", "PHASE2_OVERALL": "HYPOTHESIS_SCORE",
    "Phase2Overall": "HypothesisScore", "PHASE2_OVERALL_KEY": "HYPOTHESIS_SCORE_KEY",
    "phase2_overall_scores": "hypothesis_scores",
    "PHASE2_SCORE_VERSION": "HYPOTHESIS_SCORE_VERSION", "PHASE2_SCORE_DEFINITION": "HYPOTHESIS_SCORE_DEFINITION",
    "E6Row": "HypothesisRow", "E5Record": "EpisodeRecord",
    "e5_sample": "episode_sample", "e5_eval_log": "episode_eval_log", "e5_log": "episode_log",
    "e5_report": "predict_training_effects", "_e5_report": "_predict_training_effects",
    "sidecar": "json_export",
    "load_e5_run_config": "load_benchmark_run_config", "check_e5_run_settings": "check_benchmark_run_settings",
    "phase1_context": "report_context", "phase1_contexts": "report_contexts",
    "hypotheses_phase1_context": "hypotheses_report_context",
    "PHASE1_CONTEXT_SCHEMA": "REPORT_CONTEXT_SCHEMA", "PHASE1_ERA": "REPORT_ERA",
    "phase1_era": "report_era", "_phase1_eras": "_report_eras",
    "phase1_scores_by_judge": "report_scores_by_judge", "phase2_grades_by_judge": "hypothesis_grades_by_judge",
    "Phase1ByJudge": "ReportScoresByJudge", "Phase2ByJudge": "HypothesisGradesByJudge",
    "phase1_by_judge": "report_by_judge", "phase2_by_judge": "hypotheses_by_judge",
    "phase1_roles": "report_roles", "phase2_roles": "hypotheses_roles",
    "phase_two": "hypotheses_phase", "_phase_two": "_hypotheses_phase",
    "_open_phase_two": "_open_hypotheses_phase", "_open_phase_two_and_fill": "_open_hypotheses_phase_and_fill",
    "grade_phase_two": "grade_hypotheses_phase", "_phase_two_target": "_hypotheses_phase_target",
    "_with_phase_two": "_with_hypotheses_phase",
    "PHASE_TWO_NOT_OPEN_RECEIPT": "HYPOTHESES_NOT_OPEN_RECEIPT", "AFTER_SUBMIT_PHASE_TWO": "AFTER_SUBMIT_HYPOTHESES",
    "PHASE_ONE": "REPORT_PHASE", "PHASE_TWO": "HYPOTHESES_PHASE",
    "PHASE_ONE_RULE": "REPORT_PHASE_RULE", "PHASE_TWO_RULE": "HYPOTHESES_PHASE_RULE",
    "PHASE_TWO_VALUE": "HYPOTHESES_PHASE_VALUE", "PHASE_TWO_METADATA": "HYPOTHESES_PHASE_METADATA",
    "PHASE_ONE_TREES": "REPORT_PHASE_TREES",
    "phase_two_opened": "hypotheses_opened",
    "load_phase2_inputs": "load_hypothesis_inputs", "Phase2Inputs": "HypothesisInputs",
    "write_phase2_inputs": "write_hypothesis_inputs", "render_phase2": "render_hypotheses",
    "render_e6_report": "render_hypotheses_report",
    "CeilingRun": "OpenBookConfig", "CEILING_MAX_ROUNDS_KEY": "OPEN_BOOK_MAX_ROUNDS_KEY",
    "CEILING_SOURCE_PAPER_PATTERNS": "OPEN_BOOK_SOURCE_PAPER_PATTERNS", "CEILING_BRIEF_TEMPLATE": "OPEN_BOOK_BRIEF_TEMPLATE",
    "CEILING_RULE": "OPEN_BOOK_RULE", "e6": "hypotheses_sections", "_ceiling_task": "_open_book_task", "raw_ceiling": "raw_open_book",
    "ceiling_source_paper": "open_book_source_paper", "ceiling_max_rounds": "open_book_max_rounds",
    "E5_GROUND_TRUTH_RELPATH": "SHARED_GROUND_TRUTH_RELPATH",

    "SIDECAR_FILENAME": "HYPOTHESES_JSON_FILENAME", "SIDECAR_SCHEMA_VERSION": "HYPOTHESES_JSON_SCHEMA_VERSION",
}
PART = {  # snake/UPPER parts and CamelCase parts of any identifier
    "battery": "task_set", "batteries": "task_sets", "BATTERY": "TASK_SET", "BATTERIES": "TASK_SETS",
    "Battery": "TaskSet", "Batteries": "TaskSets",
    "sidecar": "hypotheses_json", "SIDECAR": "HYPOTHESES_JSON", "Sidecar": "HypothesesJson",
    "oracle": "answer_key", "ORACLE": "ANSWER_KEY", "Oracle": "AnswerKey",
}
NAMES.update({
    "task_e6": "task_with_hypotheses", "task_e5": "task_report_only", "_ceiling": "_open_book",
})
TEST_NAME_SUBS = [  # test function names, applied in order to names starting with test_
    ("_batterys_", "_task_sets_"), ("phase2_overall", "hypothesis_score"),
    ("phase2_grades_by_judge", "hypothesis_grades_by_judge"), ("phase2_", "hypotheses_"),
    ("phase1_scores_by_judge", "report_scores_by_judge"), ("phase1_", "report_"),
    ("phase_two", "hypotheses_phase"), ("phase_one", "report_phase"),
    ("_an_e6_", "_a_hypotheses_"), ("_e6_", "_hypotheses_"), ("the_e5_answer_key", "the_shared_answer_key"),
    ("the_e5_loader", "the_run_loader"), ("an_e5_specific_unknown_key", "an_unknown_key"),
    ("_a_ceiling_task_set", "_an_open_book_task_set"), ("_the_ceiling_task_set", "_the_open_book_task_set"),
    ("_shipped_ceiling_task_set", "_shipped_open_book_task_set"),
    ("_organisms_ceiling_", "_organisms_open_book_"), ("the_ceiling_exemption", "the_open_book_exemption"),
    ("the_ceiling_block", "the_open_book_block"), ("_a_ceiling_episode", "_an_open_book_episode"),
    ("whole_ceiling_episode", "whole_open_book_episode"), ("the_ceiling_brief", "the_open_book_brief"),
    ("on_the_ceiling_terms", "on_the_open_book_terms"), ("_a_ceiling_agent", "_an_open_book_agent"),
    ("_a_ceiling_round", "_an_open_book_round"),
]
KEEP_NAMES = {"base64", "ROUND_WAIT_CEILING_SECONDS", "MODAL_CALL_CEILING_HOURS",
              "CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS", "GIT_CEILING_DIRECTORIES"}

# Whole-string literals and YAML keys: config keys, metadata keys and file names.
KEYS = {
    "battery": "task_set", "batteries": "task_sets", "battery_id": "task_set_id",
    "battery_config": "task_set_config", "battery_config_sha256": "task_set_config_sha256",
    "battery.yaml": "task-set.yaml", "e5-report.html": "results.html",
    "phase2_overall": "hypothesis_score", "phase2_overall_by_judge": "hypothesis_score_by_judge",
    "phase2_overall_contribution": "hypothesis_score_contribution",
    "phase_two_opened": "hypotheses_opened", "e5_report": "predict_training_effects",
    "ceiling": "open_book", "ceiling_run": "open_book_run", "ceiling_source_paper": "open_book_source_paper",
    "ceiling_max_rounds": "open_book_max_rounds", "ceiling_rounds_config": "open_book_rounds_config",
    "ceiling_rounds_config_sha256": "open_book_rounds_config_sha256",
    "pp_ceiling_report_gradings": "pp_open_book_report_gradings",
    "sidecar": "hypotheses_json",
    "phase1_context": "report_context", "hypotheses_phase1_context": "hypotheses_report_context",
    "phase1_era": "report_era", "phase1_eras": "report_eras", "phase1_scores_by_judge": "report_scores_by_judge",
    "phase2_grades_by_judge": "hypothesis_grades_by_judge",
    "phase2-report.md": "hypotheses.md",
}

_L, _R = r"(?<![\w./`-])", r"(?![\w`/-]|\.\w)"  # a prose word, not part of a path or identifier
PROSE = [  # comments, docstrings, markdown, YAML comments
    (_L + "batteries" + _R, "task sets"), (_L + "Batteries" + _R, "Task sets"),
    (_L + "battery's" + _R, "task set's"), (_L + "battery" + _R, "task set"),
    (_L + "Battery" + _R, "Task set"),
    (_L + "sidecars" + _R, "hypotheses JSON files"), (_L + "sidecar" + _R, "hypotheses JSON"),
    (_L + "Sidecar" + _R, "Hypotheses JSON"),
]

FILES_SEGMENT_RX = None


def rename_identifier(name: str) -> str:
    if name in KEEP_NAMES:
        return name
    if name in NAMES:
        return NAMES[name]
    if "_" in name or name.isupper() or name.islower():
        name = "_".join(PART.get(p, p) for p in name.split("_"))
        if name.startswith("test_"):
            for old, new in TEST_NAME_SUBS:
                name = name.replace(old, new)
        return name
    # CamelCase
    pieces = re.findall(r"[A-Z][a-z0-9]*|[a-z0-9]+|[A-Z]+(?![a-z])", name)
    if "".join(pieces) == name:
        return "".join(PART.get(p, p) for p in pieces)
    return name


IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def segments(text: str) -> str:
    """Rename path/module segments: a segment bounded by / . or string edges."""
    def fix(m: re.Match[str]) -> str:
        return SEGMENTS.get(m.group(0), m.group(0))
    return re.sub(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_]+(?![A-Za-z0-9_-])", lambda m: fix(m) if _is_segment(text, m) else m.group(0), text)


def _is_segment(text: str, m: re.Match[str]) -> bool:
    if m.group(0) not in SEGMENTS:
        return False
    before = text[m.start() - 1] if m.start() > 0 else ""
    after = text[m.end()] if m.end() < len(text) else ""
    return before in "/." or after in "/." or (before in "`'\" (" and after in "`'\" )")


def prose(text: str) -> str:
    for rx, rep in PROSE:
        text = re.sub(rx, rep, text)
    # identifiers named in prose (backticked or bare) follow the code
    def ident(m: re.Match[str]) -> str:
        w = m.group(0)
        return rename_identifier(w) if w not in ("e6", "sidecar") and (w in NAMES or any(p in PART for p in re.split(r"_", w))) and w not in KEEP_NAMES and ("_" in w or w in NAMES) else w
    text = IDENT.sub(ident, text)
    return segments(text)


def docstring_spans(source: str) -> set[tuple[int, int]]:
    spans = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return spans
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                spans.add((body[0].value.lineno, body[0].value.col_offset))
        # attribute docstrings: a bare string right after an assignment
        body_list = getattr(node, "body", None)
        for i, stmt in enumerate(body_list if isinstance(body_list, list) else []):
            if i and isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                spans.add((stmt.value.lineno, stmt.value.col_offset))
    return spans


def rewrite_python(path: str, source: str) -> str:
    lines = list(iter(io.StringIO(source).readline, ""))  # the lines tokenize sees
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    docs = docstring_spans(source)
    edits: list[tuple[int, int, str]] = []
    toks = list(tokenize.generate_tokens(io.StringIO(source).readline))
    in_config = path.endswith("benchmark/config.py")
    for i, tok in enumerate(toks):
        start = offsets[tok.start[0] - 1] + tok.start[1]
        end = offsets[tok.end[0] - 1] + tok.end[1]
        if tok.type == tokenize.NAME:
            new = tok.string
            if tok.string == "ceiling":
                prev = toks[i - 1].string if i else ""
                nxt = toks[i + 1].string if i + 1 < len(toks) else ""
                if (prev == "." and nxt != "(") or in_config or (nxt == "=" and "launch.py" not in path and prev in ("(", ",")):
                    new = "open_book"
            else:
                new = rename_identifier(tok.string)
            if new != tok.string:
                edits.append((start, end, new))
        elif tok.type == tokenize.COMMENT:
            new = prose(tok.string)
            if new != tok.string:
                edits.append((start, end, new))
        elif tok.type == tokenize.STRING:
            s = tok.string
            m = re.match(r"(?i)([rbuf]*)('''|\"\"\"|'|\")", s)
            prefix, quote = m.group(1), m.group(2)
            body = s[len(prefix) + len(quote): len(s) - len(quote)]
            if (tok.start[0], tok.start[1]) in docs:
                newbody = prose(body)
            elif body in KEYS and "f" not in prefix.lower():
                newbody = KEYS[body]
            elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", body) and rename_identifier(body) != body and body in NAMES:
                newbody = rename_identifier(body)  # __all__ entries and getattr names
            elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", body) and any(p in PART for p in body.split("_")) and "_" in body:
                newbody = rename_identifier(body)
            elif ("/" in body or "." in body) and " " not in body.strip():
                newbody = segments(body)
            else:
                newbody = body
            if newbody != body:
                edits.append((start, end, f"{prefix}{quote}{newbody}{quote}"))
    out = source
    for start, end, new in sorted(edits, reverse=True):
        out = out[:start] + new + out[end:]
    return out


def rewrite_yaml(text: str) -> str:
    out = []
    for line in text.splitlines(keepends=True):
        m = re.match(r"^(\s*(?:- )?)([A-Za-z_][A-Za-z0-9_]*)(\s*:)(.*)$", line, re.S)
        if m and m.group(2) in KEYS:
            line = f"{m.group(1)}{KEYS[m.group(2)]}{m.group(3)}{m.group(4)}"
        if "#" in line:
            code, _, comment = line.partition("#")
            if '"' not in code and "'" not in code:
                line = code + "#" + prose(comment)
        out.append(line)
    return "".join(out)


def main() -> int:
    for old, new in MOVES:
        if not (ROOT / old).exists():
            print(f"skip move (absent): {old}")
            continue
        (ROOT / new).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "mv", old, new], cwd=ROOT, check=True)
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.splitlines()
    changed = 0
    for f in files:
        if f in FROZEN_FILES or f.startswith(FROZEN_PREFIXES):
            continue
        p = ROOT / f
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        if f.endswith(".py"):
            new = rewrite_python(f, text)
        elif f.endswith((".yaml", ".yml")):
            new = rewrite_yaml(text)
        elif f.endswith((".md", ".sh", ".toml", ".txt")) or f in (".env.example",):
            new = prose(text) if f.endswith(".md") else segments(text)
        else:
            continue
        if new != text:
            p.write_text(new, encoding="utf-8")
            changed += 1
    print(f"{changed} file(s) rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(main())
