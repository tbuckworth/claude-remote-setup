#!/usr/bin/env bash
# Replay the v1.1 upstream PRs onto bb02d00 (the fork in upstream layout) as branch up-v11, one commit each.
set -uo pipefail
cd "$(dirname "$0")/../work/v11"
EXCL='tree|docs/(decisions|log|index)\.md|docs/plans/|docs/workflows/|archive/|configs/benchmark/|calibration/|rejudge\.py|recovered_reports\.py|lit-|em-optimisers\.yaml|benchmarks/README\.md|test_hypotheses_calibration|test_hypothesis_hub_targets|test_report_battery|grade_hypothesis_importance'
ADD='pause_round_(ended|failed|results)\.md|phase2_hypotheses/caps\.py|judge_reply_(answer|both|reasoning)\.md|judge_test_cap\.md|test_phase2_test_(caps|schema)\.py|test_hypothesis_test_options\.py'
pick() {  # $1 merge commit, [$2 regex restricting files]
  local m=$1 only=${2:-.}
  git diff --name-status "$m^1" "$m" | while read -r st f _; do
    [[ $f =~ $only ]] || continue
    [[ $f =~ $EXCL ]] && continue
    if git cat-file -e "HEAD:$f" 2>/dev/null || [[ $st == A && $f =~ $ADD ]]; then echo "$f"; fi
  done
}
git switch -q -C up-v11 bb02d00
for spec in "7f905fdd 816 item1 sandbox/scaffold\.py|test_sandbox_network_isolation" "e8ec7737 820 item4 ." "d040ddfc 821 items5-7 ." "e9e30bba 822 items8-10 ." "0fae458c 823 item11 ." "9ed46842 825 item12 ." "fd6f77be 828 item13 ."; do
  set -- $spec; m=$1; pr=$2; what=$3; only=$4
  mapfile -t files < <(pick "$m" "$only")
  echo "== #$pr ($what): ${#files[@]} files"
  git diff --binary "$m^1" "$m" -- "${files[@]}" > "/tmp/../$PWD/../../v11port/pr$pr.patch" 2>/dev/null || git diff --binary "$m^1" "$m" -- "${files[@]}" > "../../v11port/pr$pr.patch"
  git apply -3 --index "../../v11port/pr$pr.patch" 2>&1 | grep -v -E "^Applied patch|cleanly\.$|^Falling back|^Applying patch|^Checking patch|with conflicts\.$" | sed 's/^/   /'
  conflicted=$(git diff --name-only --diff-filter=U)
  if [ -n "$conflicted" ]; then echo "   CONFLICTS:"; echo "$conflicted" | sed 's/^/     /'; echo "STOP at #$pr"; exit 3; fi
  git commit -q -m "upstream #$pr ($what), files the fork keeps" && echo "   committed $(git rev-parse --short HEAD)"
done
