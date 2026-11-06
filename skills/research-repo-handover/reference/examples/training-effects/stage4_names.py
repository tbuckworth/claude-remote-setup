"""Stage 4: environment variables, Modal names, container mounts, temp prefixes, internal keys.

PP_<NAME>        -> TE_<NAME>           (every environment variable and PP_ constant)
pp-<modal name>  -> te-<...>            (explicit map below; volumes get shorter names)
pp_<store key>   -> te_<...>            (Inspect store/metadata keys, shell helpers)
Kept, because the agent can see them: /tmp/pp-exec, pp_submission, propensity_predictor.
Run from the repository root.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from stage3_vocab import FROZEN_FILES, FROZEN_PREFIXES  # noqa: E402

HYPHEN = {  # whole hyphen-words, longest first
    "pp-e5-logs": "te-logs",
    "pp-data-raw": "te-data",
    "pp-hyp-rescue": "te-rescue",
    "pp-hf-cache": "te-hf-cache",
    "pp-target-adapters": "te-target-adapters",
    "pp-train-data-": "te-train-data-",
    "pp-sandbox-root": "te-sandbox-root",
    "pp-sandbox-": "te-sandbox-",
    "pp-sandbox": "te-sandbox",
    "pp-targets-": "te-targets-",
    "pp-targets": "te-targets",
    "pp-judge-": "te-judge-",
    "pp-judge": "te-judge",
    "pp-modal": "te-modal",
    "pp-check-sandbox": "te-check-sandbox",
    "pp-pinned-tree-": "te-pinned-tree-",
    "pp-e5-": "te-build-",
    "pp-hyp-": "te-measure-",
    "pp-hypotheses-": "te-hypotheses-",
    "pp-oracle-": "te-answer-keys-",
    "pp-grading-inputs-": "te-grading-inputs-",
    "pp-evals-": "te-evals-",
    "pp-page-inputs-": "te-page-inputs-",
    "pp-unattributed": "te-unattributed",
    "pp-test-cluster": "te-test-cluster",
    "pp-hyp-test": "te-measure-test",
    "pp-e5": "te-run",
    "pp-hyp": "te-measure",
    "pp-hf": "te-hf",
    "pp-venv": "te-venv",
    "pp-train-venv": "te-train-venv",
    "pp-src": "te-src",
    "pp-rescue": "te-rescue",
    "pp-data": "te-data",
    "pp-logs": "te-logs",
    "pp-hypotheses": "te-measure",
    "pp-surf-base-refusal-qwen3-8b-002": "te-measure-qwen3-8b-002",
    "pp-surf": "te-measure",
    "pp-data-root": "te-data-root",
    "pp-archive": "te-archive",
}
KEEP_HYPHEN = {"pp-exec"}
UNDERSCORE_KEEP = {"pp_submission", "pp_masked_table", "pp_surf_turf"}  # archives go in stage 5
APP_KINDS = {'owned_app_name("e5"': 'owned_app_name("run"', 'owned_app_name("hyp"': 'owned_app_name("measure"'}

HY_RX = re.compile(r"(?<![\w/.-])(" + "|".join(sorted(map(re.escape, HYPHEN), key=len, reverse=True)) + r")(?![\w])")
HY_PATH_RX = re.compile(r"(?<=/)(" + "|".join(sorted(map(re.escape, HYPHEN), key=len, reverse=True)) + r")(?![\w-])")
ENV_RX = re.compile(r"\bPP_(?=[A-Z0-9])")
US_RX = re.compile(r"\bpp_([a-z0-9][a-z0-9_]*)\b")
OWNER_PREFIX = re.compile(r'f"pp-\{kind\}')


def rewrite(text: str) -> str:
    text = ENV_RX.sub("TE_", text)
    text = HY_RX.sub(lambda m: HYPHEN[m.group(1)], text)
    text = HY_PATH_RX.sub(lambda m: HYPHEN[m.group(1)], text)
    text = OWNER_PREFIX.sub('f"te-{kind}', text)
    text = text.replace("PP_*_CONFIG", "TE_*_CONFIG").replace("`PP_*_CONFIG`", "`TE_*_CONFIG`")
    text = re.sub(r'"pp-(run-e5-|em-organisms-fixed10-005|continue-e5-smoke)', r'"te-\1', text)
    text = text.replace("``pp-<kind>-", "``te-<kind>-").replace("``pp-`` and", "``te-`` and")
    text = text.replace('END_USER_PREFIX: Final[str] = "pp-"', 'END_USER_PREFIX: Final[str] = "te-"')
    for a, b in APP_KINDS.items():
        text = text.replace(a, b)
    text = US_RX.sub(lambda m: m.group(0) if m.group(0) in UNDERSCORE_KEEP else f"te_{m.group(1)}", text)
    return text


def main() -> int:
    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    changed = 0
    for f in files:
        if f in FROZEN_FILES or f.startswith(FROZEN_PREFIXES):
            continue
        p = Path(f)
        try:
            t = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        new = rewrite(t)
        if new != t:
            p.write_text(new, encoding="utf-8")
            changed += 1
    print(changed, "file(s) rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(main())
