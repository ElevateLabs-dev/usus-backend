# Architecture Decision Record: Usus Backend Core Stack

**Date:** February 26, 2026

**Status:** Accepted

**Project:** Usus AI Simulation Environment

## 1. Context & Goals

Usus is an enterprise-grade AI simulation platform designed for human-staff training. It requires high concurrency for real-time WebRTC audio streaming, complex AI workflows (Evaluations, LLM text generation), secure multi-tenancy, and Retrieval-Augmented Generation (RAG) capabilities. The backend needs to be performant, highly scalable, and developer-friendly while avoiding synchronous bottlenecks.

## 2. Architectural Decisions

### 2.1 Web Framework: FastAPI (Async)

- **Decision:** Use **FastAPI** over Django.
- **Rationale:** FastAPI provides native asynchronous support (essential for WebRTC and long-running AI API calls), blazing-fast performance, and out-of-the-box OpenAPI documentation. It enforces strict type-checking via Pydantic V2.

### 2.2 Database ORM: SQLAlchemy 2.0 (Async) + Alembic

- **Decision:** Use **SQLAlchemy 2.0** with `asyncpg` over Tortoise ORM or Pony ORM.
- **Rationale:** As an enterprise app, Usus requires complex database interactions (multi-tenant filtering, vector lookups). SQLAlchemy is the industry standard Data Mapper ORM that handles high complexity and edge cases flawlessly without bottlenecking the async event loop. Alembic will handle database migrations natively.

### 2.3 Vector Database & Storage: PostgreSQL + pgvector

- **Decision:** Use **PostgreSQL** extended with **pgvector**.
- **Rationale:** Instead of adding an external vector database (like Pinecone) right away, using `pgvector` allows us to store RAG embeddings (for the 3-layer training knowledge base) directly alongside our relational data. This simplifies local development and data integrity.

### 2.4 Admin Dashboard: Starlette-Admin

- **Decision:** Use **Starlette-Admin**.
- **Rationale:** It integrates seamlessly with FastAPI (which is built on Starlette) and SQLAlchemy. It provides a highly customizable, Django-like admin panel interface while supporting complex data types and potential future integrations with NoSQL databases if required.

### 2.5 Background Processing: Celery + Redis

> **Superseded (Oct 2026):** for the MVP, evaluations run as FastAPI background tasks inside the API process; Celery and Redis were removed to keep deployment to a single service. Revisit if background workload grows.

- **Decision:** Use **Celery** as the task queue and **Redis** as the message broker.
- **Rationale:** AI evaluation generation and document vectorization are computationally expensive. Moving these to asynchronous Celery workers ensures the main FastAPI server is never blocked, maintaining a responsive UI and fast WebRTC signaling.

### 2.6 Package & Environment Management: `uv`

- **Decision:** Enforce **`uv`** and use a modern `pyproject.toml`.
- **Rationale:** `uv` is incredibly fast and enforces deterministic builds via a `uv.lock` file. This guarantees parity between local development environments and production, eliminating standard `pip` inconsistencies.

### 2.7 Application Structure: Domain-Driven Design (DDD)

- **Decision:** Organize code by feature domains (e.g., `domains/simulations/`, `domains/evaluations/`) rather than file types.
- **Rationale:** Mimics the maintainability of Django "apps". It ensures that as Usus grows, feature logic remains encapsulated and developers can easily locate related routes, models, and schemas.

### 2.8 Multi-Tenancy Strategy

- **Decision:** Row-level multi-tenancy enforced at the CRUD layer.
- **Rationale:** To fulfill the strict "No cross-tenant data access" requirement, every tenant-owned SQLAlchemy model will feature a `tenant_id` foreign key. All CRUD operations will strictly require this ID to prevent data leakage.

## 3. Consequences

- **Positive:** The system is heavily optimized for async operations, AI processing, and real-time streaming without blocking. The developer tooling (`uv`, `ruff`) is exceptionally fast.
- **Negative/Trade-offs:** The team will need to adapt to the "Data Mapper" pattern of SQLAlchemy and explicit session management, which has a steeper learning curve than Django's "Active Record" pattern.
