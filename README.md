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

uv run seed-admin

uv run seed-scenarios

# Create an organization (tenant) + a user inside it + its default scenarios.
# Users created this way sign in without needing a tenant ID.
uv run seed-demo

```

### 6. Run the Application

**Start the FastAPI Server:**

```bash
# We use `uv run` to ensure it executes strictly within the uv environment
uv run fastapi dev src/main.py

# or directly via uvicorn
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

```

- API Documentation: `http://localhost:8000/docs`
- Admin Dashboard: `http://localhost:8000/admin`

**Start the Celery Worker (in a separate terminal):**

```bash
uv run celery -A src.celery_app worker --loglevel=info

```

## Key Development Guidelines

1. **Multi-Tenancy is Mandatory:** Every database model that belongs to a specific company must include a `tenant_id` foreign key. Always filter queries by `tenant_id` at the CRUD layer to prevent cross-tenant data leaks.
2. **Async Database Queries:** We use SQLAlchemy 2.0's asynchronous engine. Always use `await session.execute(...)` instead of synchronous calls. Avoid lazy-loading relationships; use `selectinload` for eager loading.
3. **Heavy AI Tasks go to Celery:** Never block a FastAPI endpoint waiting for an LLM to generate a complex evaluation report. Return a `task_id` immediately and let the Celery worker handle the LLM call in the background.

## Testing

```bash
uv run pytest tests/

```

---

## Idea Dumps

```plaintext
usus_backend/
├── alembic.ini
├── pyproject.toml
├── alembic/
└── app/
    ├── __init__.py
    ├── main.py             # FastAPI application entry point
    ├── celery_app.py       # Celery application instance & routing
    │
    ├── core/               # App-wide foundational settings
    │   ├── config.py       # Pydantic BaseSettings (DB URLs, LLM API keys)
    │   ├── database.py     # SQLAlchemy async engine & Postgres session
    │   ├── vector_db.py    # Pinecone/pgvector connection
    │   └── security.py     # Multi-tenant RBAC logic (Admin, Manager, Trainee) [cite: 171]
    │
    ├── utils/              # ⬅️ Shared utilities (Agnostic to business logic)
    │   ├── llm_client.py   # Model-agnostic LLM wrappers (Claude, OpenAI)
    │   ├── audio.py        # STT/TTS API wrappers and audio file converters [cite: 37, 80]
    │   ├── storage.py      # AWS S3 wrappers for storing voice recordings [cite: 216, 277]
    │   └── text_parsing.py # Helpers for cleaning LLM JSON outputs
    │
    ├── admin/              # Starlette-Admin dashboards
    │   ├── setup.py
    │   └── views.py        # Admin views for Tenants, Users, and System Health
    │
    └── domains/            # ⬅️ Your Core Usus Modules
        ├── tenants/        # Multi-tenancy & Company management [cite: 207]
        │   ├── router.py, models.py, schemas.py, crud.py
        │
        ├── simulations/    # The Simulation Engine [cite: 42]
        │   ├── router.py   # WebSocket/WebRTC endpoints for real-time chat/voice
        │   ├── models.py   # Simulation sessions, chat history
        │   ├── schemas.py
        │   ├── crud.py
        │   └── engine.py   # Hybrid generation logic (Scripts + AI Improv) [cite: 53]
        │
        ├── evaluations/    # The Evaluation Engine [cite: 84]
        │   ├── router.py
        │   ├── models.py   # Scores, Red Flags, Dimensions [cite: 89, 114]
        │   ├── schemas.py
        │   ├── crud.py
        │   └── tasks.py    # ⬅️ Celery tasks: Async scoring & report generation
        │
        ├── knowledge_base/ # Training Knowledge Base (RAG) [cite: 121]
        │   ├── router.py
        │   ├── models.py   # Document metadata
        │   ├── schemas.py
        │   ├── crud.py
        │   ├── rag.py      # Retrieval logic across the 3 knowledge layers [cite: 283]
        │   └── tasks.py    # ⬅️ Celery tasks: Vectorizing company docs/reviews in background
        │
        └── learning/       # Learning Path Engine [cite: 147]
            ├── router.py
            ├── models.py   # Scenarios, Categories, Paths, Remediation Modules [cite: 151, 281, 282]
            ├── schemas.py
            └── crud.py
```

---

## Potential Dependencies Dump

```plaintext
# Core Web Framework
"fastapi>=0.110.0",
"uvicorn[standard]>=0.29.0",
"pydantic>=2.6.0",
"pydantic-settings>=2.2.0",
"python-multipart>=0.0.9",  # Required for file/audio uploads

# Database & ORM (Async)
"sqlalchemy>=2.0.29",
"asyncpg>=0.29.0",
"alembic>=1.13.1",
"pgvector>=0.2.5",          # For RAG embeddings in PostgreSQL

# Admin Dashboard
"starlette-admin>=0.13.1",
"itsdangerous>=2.1.2",      # Required by starlette-admin for session security

# Background Tasks & Caching
"celery>=5.3.6",
"redis>=5.0.3",

# AI & LLM Integration
"openai>=1.14.0",           # Primary LLM client
"anthropic>=0.21.0",        # For Claude fallback/options
"tiktoken>=0.6.0",          # Token counting for RAG chunking

# Real-time Streaming (Voice/Chat)
"websockets>=12.0",         # For real-time WebRTC signaling & Sockets

# Cloud Storage (Async AWS S3)
"aioboto3>=12.3.0",         # For asynchronously saving voice recordings to S3

###### DEV DEPENDENCIES #########
# Testing
"pytest>=8.1.1",
"pytest-asyncio>=0.23.5",
"httpx>=0.27.0",            # Async test client for FastAPI

# Linting & Formatting
"ruff>=0.3.3",              # Blazing fast linter/formatter (Replaces flake8/black)
"mypy>=1.9.0",              # Static type checking
```
