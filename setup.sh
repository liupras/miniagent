#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${SCRIPT_DIR}/backend"
MANAGEMENT_DIR="${SCRIPT_DIR}/management"
WORKPLACE_DIR="${SCRIPT_DIR}/workplace"
VENV_DIR="${BACKEND_DIR}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
LOG_DIR="${BACKEND_DIR}/logs"

cd "${SCRIPT_DIR}"

echo "=========================================="
echo "  MiniAgent Linux One-click Launcher"
echo "=========================================="
echo

if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] Python was not found. Install Python 3.12 or later."
    exit 1
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
    echo "[ERROR] MiniAgent requires Python 3.12 or later."
    exit 1
fi
echo "[OK] Python $(python3 -c 'import platform; print(platform.python_version())') is available."

if ! command -v node >/dev/null 2>&1; then
    echo "[ERROR] Node.js was not found. Install Node.js 20.19+ or 22.13+."
    exit 1
fi

if ! node -e "const [a,b]=process.versions.node.split('.').map(Number);process.exit(a===20?b>=19?0:1:a===22?b>=13?0:1:a>22?0:1)"; then
    echo "[ERROR] MiniAgent requires Node.js 20.19+ or 22.13+."
    exit 1
fi
echo "[OK] Node.js $(node --version) is available."

if command -v pnpm >/dev/null 2>&1; then
    PNPM_CMD=(pnpm)
elif command -v corepack >/dev/null 2>&1; then
    PNPM_CMD=(corepack pnpm)
else
    echo "[ERROR] pnpm was not found. Run: npm install -g pnpm"
    exit 1
fi

if ! "${PNPM_CMD[@]}" --version >/dev/null 2>&1; then
    echo "[ERROR] pnpm could not be started. Check your Node.js/Corepack installation."
    exit 1
fi
echo "[OK] pnpm $("${PNPM_CMD[@]}" --version) is available."
echo

if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "[1/5] Creating Python virtual environment..."
    python3 -m venv "${VENV_DIR}"
else
    echo "[1/5] Python virtual environment already exists."
fi

echo "[2/5] Installing backend dependencies..."
"${VENV_PYTHON}" -m pip install -r "${BACKEND_DIR}/requirements.txt"

if [[ ! -f "${BACKEND_DIR}/.env" ]]; then
    echo "[INFO] Creating backend/.env from backend/.env.example..."
    cp "${BACKEND_DIR}/.env.example" "${BACKEND_DIR}/.env"
    echo "[WARN] Review backend/.env and replace JWT_SECRET_KEY before a public deployment."
fi

echo "[3/5] Initializing the database..."
(
    cd "${BACKEND_DIR}"
    "${VENV_PYTHON}" -m app.infra.db.initializer init
)

echo "[4/5] Installing Management dependencies..."
(
    cd "${MANAGEMENT_DIR}"
    "${PNPM_CMD[@]}" install --frozen-lockfile
)

echo "[5/5] Installing Workplace dependencies..."
(
    cd "${WORKPLACE_DIR}"
    "${PNPM_CMD[@]}" install --frozen-lockfile
)

mkdir -p "${LOG_DIR}"
PIDS=()

cleanup() {
    local status=$?
    trap - EXIT INT TERM

    if ((${#PIDS[@]} > 0)); then
        echo
        echo "Stopping MiniAgent services..."
        kill "${PIDS[@]}" 2>/dev/null || true
        wait "${PIDS[@]}" 2>/dev/null || true
    fi

    exit "${status}"
}

trap cleanup EXIT
trap 'exit 130' INT TERM

echo
echo "Starting Backend, Management, and Workplace..."
(
    cd "${BACKEND_DIR}"
    exec "${VENV_PYTHON}" -m uvicorn app.main:app \
        --reload --host 0.0.0.0 --port 10088
) >"${LOG_DIR}/backend-console.log" 2>&1 &
PIDS+=("$!")

(
    cd "${MANAGEMENT_DIR}"
    exec "${PNPM_CMD[@]}" dev --host 0.0.0.0 --port 8848
) >"${LOG_DIR}/management-console.log" 2>&1 &
PIDS+=("$!")

(
    cd "${WORKPLACE_DIR}"
    exec "${PNPM_CMD[@]}" dev --host 0.0.0.0 --port 5173
) >"${LOG_DIR}/workplace-console.log" 2>&1 &
PIDS+=("$!")

sleep 2
for pid in "${PIDS[@]}"; do
    if ! kill -0 "${pid}" 2>/dev/null; then
        echo "[ERROR] A MiniAgent service failed during startup."
        tail -n 50 \
            "${LOG_DIR}/backend-console.log" \
            "${LOG_DIR}/management-console.log" \
            "${LOG_DIR}/workplace-console.log" || true
        exit 1
    fi
done

echo
echo "=========================================="
echo "  MiniAgent has been started"
echo "=========================================="
echo "  Backend API: http://localhost:10088"
echo "  API docs:    http://localhost:10088/docs"
echo "  Management:  http://localhost:8848"
echo "  Workplace:   http://localhost:5173"
echo
echo "Press Ctrl+C to stop all services."
echo "Console logs are stored in: ${LOG_DIR}"
echo

tail -n 0 -F \
    "${LOG_DIR}/backend-console.log" \
    "${LOG_DIR}/management-console.log" \
    "${LOG_DIR}/workplace-console.log" &
PIDS+=("$!")

wait -n "${PIDS[@]}"
