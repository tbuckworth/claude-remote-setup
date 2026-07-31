#!/bin/bash

# Claude executes the prompt hook above. Codex currently skips prompt hooks, so
# provide the main agent with a lightweight reminder when PLUGIN_ROOT is set.
if [ -z "${PLUGIN_ROOT:-}" ]; then
    exit 0
fi

cat >/dev/null
printf '%s\n' '{"systemMessage":"Before accepting the completed plan, independently check its unstated assumptions, edge cases, and beliefs about system behavior."}'
