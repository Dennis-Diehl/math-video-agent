# Run `just` with no args to list all recipes.
default:
    @just --list

# --- Backend (Python, run from backend/) ---

# Install backend runtime + dev dependencies into backend/.venv
backend-install:
    cd backend && python3 -m venv .venv || true
    cd backend && .venv/bin/pip install -r requirements-dev.txt

# Run the API locally (uvicorn, auto-reload) — needs GEMINI_API_KEY etc. in backend/.env
backend-dev:
    cd backend && .venv/bin/uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Run backend tests
backend-test:
    cd backend && .venv/bin/pytest

# Run one backend test file or node id, e.g. `just backend-test-one tests/test_jobs.py::test_submit_registers_a_queued_job`
backend-test-one TARGET:
    cd backend && .venv/bin/pytest {{TARGET}}

# Lint + format-check + type-check the backend (what CI runs)
backend-check:
    cd backend && .venv/bin/ruff check .
    cd backend && .venv/bin/ruff format --check .
    cd backend && .venv/bin/mypy .

# Auto-fix what ruff can fix, then format
backend-fix:
    cd backend && .venv/bin/ruff check --fix .
    cd backend && .venv/bin/ruff format .

# --- Frontend (Next.js, run from frontend/) ---

# Install frontend dependencies
frontend-install:
    cd frontend && npm install

# Run the frontend dev server (http://localhost:3000)
frontend-dev:
    cd frontend && npm run dev

# Run frontend tests
frontend-test:
    cd frontend && npm test

# Run frontend tests in watch mode
frontend-test-watch:
    cd frontend && npm run test:watch

# Type-check + lint the frontend
frontend-check:
    cd frontend && npx tsc --noEmit
    cd frontend && npx eslint .

# --- Everything ---

# Run backend + frontend test suites
test: backend-test frontend-test

# Run backend + frontend lint/type checks (what CI runs)
check: backend-check frontend-check

# --- Docker (full stack) ---

# Build and start api + frontend via docker compose (foreground, Ctrl-C to stop)
up:
    docker compose up --build

# Start api + frontend in the background
up-d:
    docker compose up --build -d

# Stop and remove the docker compose stack
down:
    docker compose down

# Tail logs from the running docker compose stack
logs:
    docker compose logs -f
