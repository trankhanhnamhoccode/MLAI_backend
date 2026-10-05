#!/bin/sh
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python="$script_dir/../.venv/bin/python"
if [ ! -x "$python" ]; then
    echo "ERROR: Missing repository virtual environment; create .venv and install -e '.[dev]'." >&2
    exit 1
fi
exec "$python" "$script_dir/dev.py" "$@"
