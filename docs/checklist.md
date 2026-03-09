# Usus Simulation Engine — Build Checklist

## Legend

- [ ] Not started
- [x] Complete
- [~] In progress

---

## Phase A: Minimal CLI Simulation and Persistence Layer (Text-Only)

Core goal: A working text conversation loop between a trainee and an AI customer,
with post-session evaluation and structured debrief.

### A1. Domain Models & Schemas

- [x] `domains/scenarios/` — Scenario, CustomerPersona, DifficultyLevel enums
- [x] `domains/simulations/` — Session, Message, SessionStatus enums
- [x] `domains/evaluations/` — EvaluationResult, DimensionScore, RedFlag
- [x] `Tenant` model with row-level multi-tenancy
- [x] `Scenario` table (with tenant_id FK)
- [x] `Session` table (with tenant_id FK)
- [x] `Message` table (linked to session)
- [x] `EvaluationResult` table (linked to session)

### A2. Infrastructure

- [x] `infrastructure/llm/base.py` — Abstract LLM provider interface
- [x] `infrastructure/llm/anthropic.py` — Claude implementation (model-agnostic ready)
- [x] `infrastructure/storage/memory.py` — In-memory repository (sessions, scenarios)

### A3. Core Services

- [x] `domains/scenarios/service.py` — Load/list scenarios, seed defaults
- [x] `domains/simulations/service.py` — Orchestrate simulation (start, send message, end)
- [x] `domains/evaluations/service.py` — 7-dimension scoring + debrief generation

### A4. Repository Layer

- [ ] Enforce tenant_id filtering on all queries
- [ ] Session transcript storage

### A5. CLI Runner

- [ ] `cli/runner.py` — Interactive CLI: pick scenario → chat → get evaluation
- [ ] `config.py` — Central config (API keys, model selection)
- [ ] `main.py` — Entry point

### A6. Seed Data

- [ ] At least 3 starter scenarios (Beginner / Intermediate / Advanced)
- [ ] Customer personas matching spec (Friendly, Frustrated, Angry)

---

## Phase B: FastAPI HTTP Layer

Core goal: Expose simulation as REST API endpoints.

### B1. API Routes

- [ ] `POST /simulations/start` — Start a new session
- [ ] `POST /simulations/{session_id}/message` — Send trainee message
- [ ] `POST /simulations/{session_id}/end` — End session, trigger eval
- [ ] `GET /simulations/{session_id}/evaluation` — Get debrief
- [ ] `GET /scenarios/` — List available scenarios

### B2. Auth & Tenancy

- [ ] Basic auth middleware (API key or JWT stub)
- [ ] Tenant extraction from auth context
- [ ] RBAC role checks (Platform Admin, Company Admin, Manager, Trainee)

### B3. OpenAPI Docs

- [ ] Auto-generated Swagger via FastAPI
- [ ] Pydantic V2 request/response schemas

---

## Phase C: Evaluation Engine Enhancements

- [ ] Configurable dimension weights per scenario
- [ ] Red flag detection (compliance, misinformation, inappropriate language)
- [ ] Certification gate logic (pass/fail threshold)
- [ ] Remediation module recommendation

---

## Phase D: Background Processing (Celery + Redis)

- [x] Celery worker setup
- [ ] Async evaluation generation task
- [ ] Async document vectorization task

---

## Phase E: Knowledge Base & RAG

- [x] pgvector extension setup
- [ ] Document ingestion pipeline (Layer 3 — company docs)
- [ ] RAG retrieval during simulation (context injection)
- [ ] Layer 1 seeding (universal CS knowledge)

---

## Phase F: Learning Path Engine

- [ ] Progression model (Levels 1–3 for MVP)
- [ ] Unlock criteria enforcement
- [ ] Scenario assignment by manager
- [ ] Progress tracking per trainee

---

## Phase G: Voice Simulation (WebRTC + STT/TTS)

- [ ] WebRTC signaling server
- [ ] STT integration (streaming)
- [ ] TTS integration (streaming)
- [ ] Voice session recording & encrypted storage

---

## Current Status

**Active Phase:** A (Minimal CLI Simulation and Persistence Layer)
**Last Updated:** 2026-03-09
