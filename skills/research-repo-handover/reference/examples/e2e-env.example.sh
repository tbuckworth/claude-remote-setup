# Sourced by e2e-step.sh. The end-to-end run's environment: values are read from files or a
# dotenv in a subshell, never typed here and never echoed. Copy beside your e2e logs and edit.
# (Pattern of the Training Effects e2e-v11 env.sh, 6 Nov 2026.)
E="${E:?set E to the directory holding this run's logs}"
CLONE="${CLONE:?set CLONE to the fresh clone of the commit under test}"

# load NAME FILE: export NAME from the first line of FILE (a token a deploy step wrote there).
load() { printf -v "$1" '%s' "$(head -1 "$2")"; export "$1"; }
# from_env NAME DOTENV: export NAME from a dotenv file, read in a subshell, never printed.
from_env() { printf -v "$1" '%s' "$(set -a; . "$2" >/dev/null 2>&1; set +a; printenv "$1")"; export "$1"; }

# Examples (edit): a server's token and URL written by its deploy step; a read credential.
# load EXAMPLE_SCREEN_API_KEY "$E/screen-token"
# [ -s "$E/screen-url" ] && load EXAMPLE_SCREEN_BASE_URL "$E/screen-url"
# from_env HF_ADAPTERS_TOKEN "/path/to/the/.env/that/holds/it"

# Keys a local judge would prefer over the provider's: clear them.
# unset EXAMPLE_JUDGE_API_KEY
export EXAMPLE_OWNER_LABEL=handover   # owner label for shared cloud resource names
cd "$CLONE" || exit 9
