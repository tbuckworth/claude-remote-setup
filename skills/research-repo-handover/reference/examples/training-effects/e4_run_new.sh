#!/usr/bin/env bash
# Stage the new side for every task set (three passes, as for the source) and compare.
H=/media/titus/big/tmp/claude-1000/-media-titus-py-PycharmProjects-propensity-prediction-todo-2415-create-training-effects-pred/2fc8ee02-1a2f-472f-826b-f8b3c21ff70b/scratchpad/harness; F=$1; KEY=$2; CLI="$3"; OUT=$4
export PP_DATA_ROOT=/media/titus/py/PycharmProjects/propensity-prediction-build-E5/data/raw TE_DATA_ROOT=/media/titus/py/PycharmProjects/propensity-prediction-build-E5/data/raw OMP_NUM_THREADS=1
mkdir -p $OUT
grep -vE "^(em-optimisers-hypotheses|em-organisms-hypotheses-instruct-lit-none|em-organisms-hypotheses-instruct|em-organisms-hypotheses|em-organisms)	" ${PAIRS:-$H/pairs-new.tsv} > $OUT/pairs-a.tsv
grep -E "^(em-optimisers-hypotheses|em-organisms-hypotheses-instruct-lit-none|em-organisms-hypotheses-instruct|em-organisms-hypotheses)	" ${PAIRS:-$H/pairs-new.tsv} > $OUT/pairs-b.tsv
grep -E "^em-organisms	" ${PAIRS:-$H/pairs-new.tsv} > $OUT/pairs-c.tsv
cd $H
python3 e4_capture.py --repo $F --cli "$CLI" --key $KEY --template ${TEMPLATE:-$H/template-new.yaml} --pairs $OUT/pairs-a.tsv --out $OUT
python3 e4_capture.py --repo $F --cli "$CLI" --key $KEY --template ${TEMPLATE:-$H/template-new.yaml} --pairs $OUT/pairs-b.tsv --out $OUT --drop continuation_nudges
python3 e4_capture.py --repo $F --cli "$CLI" --key $KEY --template ${TEMPLATE:-$H/template-new.yaml} --pairs $OUT/pairs-c.tsv --out $OUT --drop continuation_nudges --drop allow_untested_hypotheses
for f in $H/e4-src/*.files.tsv; do l=$(basename $f .files.tsv); if cmp -s $f $OUT/$l.files.tsv; then echo "SAME  $l ($(wc -l < $f) files)"; else echo "DIFF  $l"; diff $f $OUT/$l.files.tsv | head -5; fi; done
