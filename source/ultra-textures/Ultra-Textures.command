#!/bin/bash
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
for PY in /opt/homebrew/bin/python3 /usr/local/bin/python3 "$(command -v python3 || true)" /usr/bin/python3; do
  if [ -x "$PY" ] && "$PY" -c 'import sys; raise SystemExit(sys.version_info < (3,10))' 2>/dev/null; then
    export PYTHONDONTWRITEBYTECODE=1
    exec "$PY" "$HERE/addon.py" open
  fi
done
printf '%s\n' 'Python 3.10 or newer is required. Install Python from python.org, then open this command again.'
exit 1
