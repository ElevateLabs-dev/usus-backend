### 1. Environment & Dependency Management

- Initialize your project environment using **`uv`** to ensure fast, deterministic builds.
- Define your dependencies (FastAPI, SQLAlchemy, Celery, etc.) in a modern **`pyproject.toml`** file.
- Generate your **`uv.lock`** file to lock down dependency versions for production parity.

### 2. Project Structure (Domain-Driven Design)

- Scaffold your root application directory using a **Domain-Driven Design (DDD)** approach.
- Create distinct domain folders to encapsulate feature logic, such as `domains/simulations/` and `domains/evaluations/`.
- Inside each domain, set up the structure for your routes, models, schemas (Pydantic V2), and CRUD operations.

### 3. Core Framework Setup

- Initialize the **FastAPI** application instance.
- Configure the main entry point (e.g., `main.py`) to serve as the ASGI application.

### 4. Database & ORM Configuration

- Stand up a **PostgreSQL** database instance and enable the **`pgvector`** extension for RAG embeddings.
- Install and configure **SQLAlchemy 2.0** with the **`asyncpg`** driver for asynchronous database access.
- Set up explicit session management, adapting to SQLAlchemy's Data Mapper pattern.
- Initialize **Alembic** to handle native database migrations.

### 5. Multi-Tenancy Implementation

- Create a base SQLAlchemy model class that includes a **`tenant_id` foreign key**.
- Implement base CRUD utility classes/functions that strictly require `tenant_id` for all operations to enforce row-level multi-tenancy and prevent data leakage.

### 6. Background Processing

- Spin up a **Redis** instance to act as your message broker.
- Configure **Celery** to connect to Redis for routing background tasks.
- Create test Celery workers to handle computationally expensive tasks like AI evaluations and document vectorization without blocking the FastAPI event loop.

### 7. Admin Dashboard

- Install and configure **Starlette-Admin**.
- Integrate the admin dashboard with your FastAPI application and connect it to your SQLAlchemy models for easy data management.
