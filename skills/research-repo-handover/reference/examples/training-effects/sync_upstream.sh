#!/usr/bin/env bash
# Bring upstream propensity-prediction changes into this repository, for the files it keeps.
#
# Usage (from a clean tree):  tools/audit/sync_upstream.sh <propensity-prediction clone> <new commit>
#
# 1. Shows what changed upstream between the pin (tools/audit/PIN) and <new commit>.
# 2. Applies the upstream diff of every file tracked here (modifications, renames, deletions) with
#    `git apply --reject`: a byte-identical file takes the change cleanly; a file this repo edited
#    (tools/audit/changes.tsv; docs/audit/files.tsv lists each file's status) may leave a `.rej` hunk to resolve by hand.
# 3. Lists files upstream ADDED under directories this repo keeps, for you to judge: a new prompt or
#    module a kept file now imports must be copied over; a new historical config must not. Then
#    recomputes the keep set at <new commit> and lists what it needs that this tree lacks.
# 4. If uv.lock changed, regenerates benchmarks/shared/training-environment.yaml (its lock pin).
# 5. Runs ruff, the tree audit and the tests. Review, commit, then write <new commit> to the PIN.
set -euo pipefail

UP="${1:?usage: tools/audit/sync_upstream.sh <propensity-prediction clone> <new commit>}"
NEW="${2:?give the upstream commit to sync to}"
cd "$(dirname "$0")/../.."
PIN=$(awk '{print $1; exit}' tools/audit/PIN)
test -z "$(git status --porcelain)" || { echo "commit or stash your changes first" >&2; exit 2; }
git -C "${UP}" cat-file -e "${NEW}^{commit}" || { echo "${NEW} is not in ${UP}" >&2; exit 2; }

echo "== upstream ${PIN:0:12}..${NEW:0:12}, files this repo keeps"
mapfile -t KEPT < <(git ls-files)
git -C "${UP}" diff --stat "${PIN}" "${NEW}" -- "${KEPT[@]}" | tail -n 40

PATCH="$(mktemp -t upstream-XXXXXX.patch)"
git -C "${UP}" diff --binary -M "${PIN}" "${NEW}" -- "${KEPT[@]}" > "${PATCH}"
if [ -s "${PATCH}" ]; then
  git apply --reject --whitespace=nowarn "${PATCH}" || true
  echo "== rejected hunks (resolve by hand):"
  find . -name '*.rej' -not -path './.git/*' -print
fi

echo "== files upstream added under kept directories (judge each; copy only what kept code needs):"
mapfile -t DIRS < <(printf '%s\n' "${KEPT[@]}" | xargs -n1 dirname | sort -u)
git -C "${UP}" diff --name-only --diff-filter=A "${PIN}" "${NEW}" -- "${DIRS[@]}" | sed 's/^/   /'

echo "== the keep set recomputed at ${NEW:0:12} (closure.py, make_keep_set.py), against this tree:"
# Catches what the two lists above cannot: kept code that now imports or opens a file that
# existed at the pin but was cut here, and a kept file that upstream renamed out of a kept path.
K="$(mktemp -d -t keep-XXXXXX)"
git clone -q --shared --no-checkout "${UP}" "${K}/src" && git -C "${K}/src" checkout -q "${NEW}"
python3 tools/audit/closure.py --repo "${K}/src" --out "${K}/closure.json" > "${K}/closure.log" 2>&1
python3 tools/audit/make_keep_set.py "${K}/src" "${K}/closure.json" tools/audit/traced-reads.txt \
  "${K}/keep.tsv" > "${K}/keep.log" 2>&1
echo "   needed at ${NEW:0:12}, absent here (copy each from upstream, or record why not):"
# Paths changes.tsv records as removed (the test triage's) are not news.
comm -23 <(cut -f1 "${K}/keep.tsv" | sort) \
  <(sort -u <(git ls-files) <(grep -v '^#' tools/audit/changes.tsv | cut -f1)) | sed 's/^/     /'
echo "   kept here, no longer in the keep set (judge each):"
comm -13 <(cut -f1 "${K}/keep.tsv" | sort) <(cut -f1 tools/audit/keep.tsv | sort) | sed 's/^/     /'
echo "   (the new keep set: ${K}/keep.tsv; copy it over tools/audit/keep.tsv once the tree matches)"

if git -C "${UP}" diff --quiet "${PIN}" "${NEW}" -- uv.lock; then :; else
  echo "== uv.lock changed upstream: regenerating the training-environment manifest"
  uv sync --extra providers --extra scaffolds --extra launch --extra dev --locked
  uv run python scripts/benchmark/generate_training_environment.py
fi

echo "== checks"
uv run ruff check . && uv run ruff format --check .
uv run python tools/audit/check_tree.py --source "${UP}" || true
OMP_NUM_THREADS=1 uv run pytest -n 0 -q -m "" || true
echo "Review the diff (git diff), rerun the equivalence checks (tools/audit/README.md), commit,"
echo "then: echo ${NEW} > tools/audit/PIN, and record the sync in docs/AUDIT.md."
