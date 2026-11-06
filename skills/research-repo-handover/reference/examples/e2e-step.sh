#!/usr/bin/env bash
# e2e-step.sh NAME CMD...: run one end-to-end step in the run's environment.
# Writes $E/NAME.start (UTC start), $E/NAME.log (all output), $E/NAME.done ("exit=N <UTC end>").
# A step list sorted by .start with each .done is the run's record (see e2e-checklist.md).
# Long steps (cloud launches) go in the background with `nohup`; a foreground tool call that
# hits its time limit kills the launcher client.
. "$(dirname "$0")/e2e-env.sh"
name=${1:?usage: e2e-step.sh NAME CMD...}; shift
date -u +%FT%TZ > "$E/$name.start"
"$@" > "$E/$name.log" 2>&1
echo "exit=$? $(date -u +%FT%TZ)" > "$E/$name.done"
