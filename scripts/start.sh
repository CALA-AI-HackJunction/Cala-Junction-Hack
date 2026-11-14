#!/usr/bin/env bash
# ==============================================================================
# Unicorn Radar — One-Command Launcher (Linux / macOS / WSL / Git Bash)
# Usage: ./scripts/start.sh [PORT] [HOST]
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Load .env if present without overriding existing environment variables
if [[ -f "${REPO_ROOT}/.env" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    trimmed="${line#"${line%%[![:space:]]*}"}"
    [[ -z "$trimmed" || "$trimmed" == \#* || "$trimmed" != *=* ]] && continue
    key="${trimmed%%=*}"
    val="${trimmed#*=}"
    key="${key//[[:space:]]/}"
    val="${val%\"}"
    val="${val#\"}"
    val="${val%\'}"
    val="${val#\'}"
    if [[ -z "${!key:-}" ]]; then
      export "${key}=${val}"
    fi
  done < "${REPO_ROOT}/.env"
fi

export PORT="${1:-${PORT:-8080}}"
export HOST="${2:-${HOST:-127.0.0.1}}"

read -r -d '' BOOT_CODE << 'PYEOF' || true
import importlib, os, sys
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "backend"))
host = os.environ.get("HOST", "127.0.0.1")
port = int(os.environ.get("PORT", "8080"))

app = None
target = None
for mod_name in ("backend.main", "backend.app", "backend.server"):
    try:
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "app"):
            app = getattr(mod, "app")
            target = f"{mod_name}:app"
            break
        if hasattr(mod, "create_app"):
            app = mod.create_app()
            target = mod_name
            break
    except ImportError:
        continue

if app is not None:
    import uvicorn
    print(f"[Unicorn Radar] Starting server ({target}) at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
else:
    for mod_name in ("backend.server", "server"):
        try:
            mod = importlib.import_module(mod_name)
            if hasattr(mod, "run_server"):
                mod.run_server(host=host, port=port)
                sys.exit(0)
        except ImportError:
            continue
    raise SystemExit("Backend entrypoint not found. Expected backend.main:app, backend.app:app, or backend.server:app.")
PYEOF

echo "================================================================"
echo "  Unicorn Radar — Cala x Slush Connection Intelligence (2026)"
echo "  URL: http://${HOST}:${PORT}"
echo "================================================================"

if command -v uv >/dev/null 2>&1; then
  exec uv run --python 3.12 python -c "${BOOT_CODE}"
elif command -v python3 >/dev/null 2>&1; then
  exec python3 -c "${BOOT_CODE}"
elif command -v python >/dev/null 2>&1; then
  exec python -c "${BOOT_CODE}"
else
  echo "Error: Neither 'uv', 'python3', nor 'python' found in PATH." >&2
  exit 1
fi
