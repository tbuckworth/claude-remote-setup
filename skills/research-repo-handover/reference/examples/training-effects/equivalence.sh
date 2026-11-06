#!/usr/bin/env bash
# Old-vs-new equivalence checks (docs/AUDIT.md, E4 and E5), from a clean checkout of each repo.
#
# Usage:  tools/audit/equivalence.sh <source clone at the PIN, with its own .venv> [<work dir>]
#
#   E4  preflight both blog batteries (and the open-book ones) in both checkouts, then compare
#       the staged sandboxes byte for byte (every file the agent receives), and the host-side
#       records after replacing only the two checkouts' paths and harness SHAs;
#   E5  run the scripted (mock) episodes end to end under Docker in both checkouts, then compare
#       the run directories with compare_runs.py.
#
# Needs Docker and the two corpora (PP_DATA_ROOT, or data/raw). Free: no API call is made
# (the open-book preflights build their judge client, so a dummy ANTHROPIC_API_KEY is set).
set -euo pipefail

SRC="$(cd "${1:?usage: equivalence.sh <source clone> [work dir]}" && pwd)"
NEW="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="${2:-$(mktemp -d -t tep-equivalence-XXXXXX)}"
STAMP="$(date +%Y%m%d-%H%M%S)"
SHA_SRC=$(git -C "${SRC}" rev-parse HEAD)
SHA_NEW=$(git -C "${NEW}" rev-parse HEAD)
test -z "$(git -C "${SRC}" status --porcelain)" || { echo "source checkout is dirty" >&2; exit 2; }
test -z "$(git -C "${NEW}" status --porcelain)" || { echo "this checkout is dirty" >&2; exit 2; }
[ "${SHA_SRC}" = "$(awk '{print $1; exit}' "${NEW}/tools/audit/PIN")" ] ||
  echo "WARNING: the source checkout is not at tools/audit/PIN"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMBA_NUM_THREADS=1
export PP_DATA_ROOT="${PP_DATA_ROOT:-${NEW}/data/raw}" PP_JUDGE_API_KEY= PP_MONITOR_API_KEY=
mkdir -p "${WORK}/cfg"
fail=0

# Config copies with a fresh log_dir, so neither checkout appends to an earlier run.
fresh() {  # fresh <config> <tag>
  local out="${WORK}/cfg/$2.yaml"
  sed -E "s#^log_dir: .*#log_dir: logs/equivalence-$2-${STAMP}#" "$1" > "${out}"
  echo "${out}"
}

echo "== E4: staged sandboxes (preflight, adapters not checked, screen endpoint never contacted)"
for cfg in run-optimisers-fixed10-opus-5.5 run-organisms-fixed10-opus-5.5 run-optimisers-ceiling-opus-5.5 run-organisms-ceiling-opus-5.5; do
  overlay="${WORK}/cfg/${cfg}-preflight.yaml"
  # Overlays do not chain and these configs name a base, so write one standalone file: the
  # config merged over its base, with the adapter check off and the sandbox local.
  "${SRC}/.venv/bin/python" - "${NEW}/configs/benchmark/${cfg}.yaml" "${overlay}" <<'PY'
import sys
from pathlib import Path

import yaml

path, out = Path(sys.argv[1]), Path(sys.argv[2])
settings = yaml.safe_load(path.read_text())
if "base" in settings:
    merged = yaml.safe_load((path.parent / settings.pop("base")).read_text())
    merged.update(settings)
    settings = merged
settings.update(allow_untested_hypotheses=True, sandbox="docker")
out.write_text(yaml.safe_dump(settings, sort_keys=False))
PY
  for side in src new; do
    repo=$([ "${side}" = src ] && echo "${SRC}" || echo "${NEW}")
    tmp="${WORK}/e4/${side}/${cfg}"; mkdir -p "${tmp}"
    # A dummy ANTHROPIC_API_KEY: the open-book task builds its round judge (no call is made).
    (cd "${repo}" && TMPDIR="${tmp}" PP_SCREEN_BASE_URL=http://screen.invalid/v1 PP_SCREEN_API_KEY=x \
      ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-dummy}" \
      PP_TARGET_API_KEY=x PP_TARGET_BASE_URL=http://t.invalid/v1 \
      PP_TARGET_BASE_URL_QWEN3_1_7B=http://t.invalid/v1 PP_TARGET_BASE_URL_QWEN3_4B=http://t.invalid/v1 \
      uv run --frozen pp benchmark run --config "${overlay}" --preflight > "${tmp}.log" 2>&1) ||
      { echo "preflight failed (${side} ${cfg}); see ${tmp}.log"; fail=1; }
  done
  a=$(ls -d "${WORK}/e4/src/${cfg}"/pp-e5-* 2>/dev/null | head -1)
  b=$(ls -d "${WORK}/e4/new/${cfg}"/pp-e5-* 2>/dev/null | head -1)
  [ -n "${a}" ] && [ -n "${b}" ] || { echo "no staged tree for ${cfg}"; fail=1; continue; }
  same=0; host=0; real=0
  while IFS= read -r f; do
    if cmp -s "${a}/${f}" "${b}/${f}"; then same=$((same + 1)); continue; fi
    if cmp -s <(sed -e "s#${a}#<B>#g" -e "s#${SHA_SRC}#<SHA>#g" -e "s#${SRC}#<R>#g" "${a}/${f}") \
              <(sed -e "s#${b}#<B>#g" -e "s#${SHA_NEW}#<SHA>#g" -e "s#${NEW}#<R>#g" "${b}/${f}"); then
      host=$((host + 1))
    else
      echo "  REAL DIFFERENCE: ${f}"; real=$((real + 1)); fail=1
    fi
  done < <(cd "${a}" && find . -type f | sort)
  extra=$(comm -3 <(cd "${a}" && find . -type f | sort) <(cd "${b}" && find . -type f | sort) | wc -l)
  [ "${extra}" -eq 0 ] || { echo "  ${extra} file(s) in only one tree"; fail=1; }
  echo "  ${cfg}: ${same} byte-identical, ${host} identical up to paths and SHA, ${real} different"
done

echo "== E5: scripted episodes end to end (Docker)"
for cfg in run-optimisers-hypotheses-fixed10-smoke run-organisms-hypotheses-fixed10-smoke run-optimisers-ceiling-smoke; do
  c=$(fresh "${NEW}/configs/benchmark/${cfg}.yaml" "${cfg}")
  log_dir=$(awk '/^log_dir:/ {print $2}' "${c}")
  for repo in "${SRC}" "${NEW}"; do
    (cd "${repo}" && uv run --frozen pp benchmark run --config "${c}" > "${WORK}/$(basename "${repo}")-${cfg}.log" 2>&1) ||
      { echo "run failed in ${repo}"; fail=1; }
  done
  "${SRC}/.venv/bin/python" "${NEW}/tools/audit/compare_runs.py" "${SRC}/${log_dir}" "${NEW}/${log_dir}" \
    --root-a "${SRC}" --root-b "${NEW}" --root-b "$(realpath "${NEW}")" \
    --sha "${SHA_SRC}" --sha "${SHA_NEW}" > "${WORK}/compare-${cfg}.txt" 2>&1 || fail=1
  echo "  ${cfg}: $(tail -1 "${WORK}/compare-${cfg}.txt")  (details: ${WORK}/compare-${cfg}.txt)"
done
echo "work dir: ${WORK}"
exit "${fail}"
