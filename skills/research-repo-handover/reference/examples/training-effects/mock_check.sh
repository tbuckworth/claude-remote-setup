#!/usr/bin/env bash
# Run the three scripted (mock) episodes in a checkout and compare each with the source repo's run.
#
# Usage: mock_equivalence.sh <clean checkout with .venv>
# Needs Docker and the corpora. Free: every model is a scripted mockllm. Exits 1 on any difference.
set -uo pipefail
H=/media/titus/big/tmp/claude-1000/-media-titus-py-PycharmProjects-propensity-prediction-todo-2415-create-training-effects-pred/2fc8ee02-1a2f-472f-826b-f8b3c21ff70b/scratchpad/harness
SRC=$H/../work/src-c9881f02
REPO="$(cd "${1:?usage: mock_equivalence.sh <checkout>}" && pwd)"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMBA_NUM_THREADS=1
export TE_DATA_ROOT=/media/titus/py/PycharmProjects/propensity-prediction-build-E5/data/raw
export PP_DATA_ROOT=$TE_DATA_ROOT TE_JUDGE_API_KEY= TE_MONITOR_API_KEY= PP_JUDGE_API_KEY= PP_MONITOR_API_KEY=
test -z "$(git -C "$REPO" status --porcelain)" || { echo "checkout is dirty: commit first" >&2; exit 2; }
fail=0
while IFS=$'\t' read -r cfg old; do
  [ -z "$cfg" ] && continue
  rm -rf "$REPO/logs/$cfg"; mkdir -p "$REPO/logs"
  echo "== $cfg"
  (cd "$REPO" && .venv/bin/training-effects benchmark run --config "${RUNS_DIR:-configs/runs}/$cfg.yaml") > "$REPO/logs/mock-$cfg.log" 2>&1 ||
    { echo "  run failed: see $REPO/logs/mock-$cfg.log"; fail=1; continue; }
  new=$(ls -t "$REPO/logs/$cfg"/*.eval 2>/dev/null | head -1)
  oldlog=$(ls -t "$SRC/logs/$old"/*.eval | head -1)
  [ -n "$new" ] || { echo "  no .eval written"; fail=1; continue; }
  "$SRC/.venv/bin/python" "$H/compare_mock.py" "$oldlog" "$new" --key-map "${KEY_MAP:-$H/key-map.tsv}" || fail=1
done <<EOF
optimisers-mock	equivalence-run-optimisers-hypotheses-fixed10-smoke-20261103-154558
organisms-mock	equivalence-run-organisms-hypotheses-fixed10-smoke-20261103-154558
optimisers-open-book-mock	equivalence-run-optimisers-ceiling-smoke-20261103-154558
EOF
exit $fail
