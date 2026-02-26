# Usus Backend

Usus is an AI-powered simulation environment designed to help human staff practice real-world job scenarios and receive structured, objective feedback on their performance.

This repository houses the core API, WebSocket/WebRTC streaming engine, RAG pipelines, and asynchronous evaluation workers that power the Usus platform.

## Tech Stack

- **Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Async)
- **Data Validation:** Pydantic V2
- **ORM:** SQLAlchemy 2.0 (via `asyncpg`)
- **Database Migrations:** Alembic
- **Background Tasks:** Celery + Redis
- **Admin Dashboard:** Starlette-Admin
- **Vector Store (RAG):** pgvector / Pinecone (Configurable)
- **AI Integration:** Model-agnostic wrappers (Claude, OpenAI)

## Project Structure

We follow a **Domain-Driven Design (DDD)** approach. Instead of grouping files by type (e.g., all models together), we group them by business feature (e.g., all simulation logic together).

```text
usus_backend/
├── alembic/                # Database migration scripts
├── app/
│   ├── admin/              # Starlette-Admin dashboards and views
│   ├── core/               # App-wide settings (DB connections, security, config)
│   ├── domains/            # Core business modules (Tenants, Simulations, Evaluations, etc.)
│   ├── utils/              # Domain-agnostic helpers (LLM clients, S3 storage, Audio)
│   ├── celery_app.py       # Celery worker initialization
│   └── main.py             # FastAPI application entry point
└── pyproject.toml          # Python dependencies

```

## Local Development Setup

We strictly use **[uv](https://github.com/astral-sh/uv)** for virtual environment creation and dependency management. It is fast and ensures deterministic builds across all developer machines. **Do not use standard `pip` or `poetry`.**

### 1. Prerequisites

- Python 3.11+
- Docker & Docker Compose (for PostgreSQL and Redis)
- **uv** installed on your system.

**To install `uv`:**

- **macOS/Linux:** `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **macOS (Homebrew):** `brew install uv`
- **Windows:** `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

### 2. Clone and Setup the Environment

Navigate to the project directory.

```bash
git clone https://github.com/your-org/usus-backend.git
cd usus-backend

# 1. Create a virtual environment using the specified Python version
uv venv --python 3.11

# 2. Activate the virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate

# 3. Install all dependencies (including dev dependencies) from pyproject.toml
uv sync

```

### 3. Managing Dependencies (For Developers)

When adding new packages to the project, do not use `pip install`. Use `uv add` so it automatically updates the `pyproject.toml` and lockfile.

- **Add a production dependency:**

```bash
uv add fastapi sqlalchemy

```

- **Add a development dependency (e.g., testing tools):**

```bash
uv add --dev pytest ruff

```

### 4. Environment Variables

Copy the example environment file and fill in your local credentials and API keys.

```bash
cp .env.example .env

```

### 5. Start Infrastructure & Run Migrations

Spin up your local PostgreSQL (pgvector) database and Redis broker, then run the Alembic migrations.

```bash
docker-compose up -d

# We use `uv run` to ensure it executes strictly within the uv environment
uv run alembic upgrade head

```

### 6. Run the Application

**Start the FastAPI Server:**

```bash
# We use `uv run` to ensure it executes strictly within the uv environment
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

```

- API Documentation: `http://localhost:8000/docs`
- Admin Dashboard: `http://localhost:8000/admin`

**Start the Celery Worker (in a separate terminal):**

```bash
uv run celery -A app.celery_app worker --loglevel=info

```

## Key Development Guidelines

1. **Multi-Tenancy is Mandatory:** Every database model that belongs to a specific company must include a `tenant_id` foreign key. Always filter queries by `tenant_id` at the CRUD layer to prevent cross-tenant data leaks.
2. **Async Database Queries:** We use SQLAlchemy 2.0's asynchronous engine. Always use `await session.execute(...)` instead of synchronous calls. Avoid lazy-loading relationships; use `selectinload` for eager loading.
3. **Heavy AI Tasks go to Celery:** Never block a FastAPI endpoint waiting for an LLM to generate a complex evaluation report. Return a `task_id` immediately and let the Celery worker handle the LLM call in the background.

## Testing

_(Add testing instructions here once pytest is configured)_

```bash
pytest app/tests/

```
