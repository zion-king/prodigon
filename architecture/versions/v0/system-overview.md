<!-- Version: v0 | Last updated: 2026-04-16 | Status: current -->

# Prodigon AI Platform -- System Overview

## 1. System Purpose

Prodigon is a multi-service AI assistant platform built as both a **production-grade system** and a **teaching vehicle** for the "Designing Production AI Systems" workshop series.

The platform demonstrates real-world architectural patterns -- service decomposition, config-driven behavior, structured logging, streaming inference, and containerized deployment -- while remaining simple enough to understand in under 30 minutes. Each workshop task evolves the baseline system, introducing new design patterns, scalability techniques, and security hardening.

---

## 2. Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Backend** | Python 3.11+, FastAPI, Pydantic v2, pydantic-settings, httpx, structlog, Groq SDK |
| **Frontend** | React 18.3, Vite 5.4, TypeScript 5.5, Zustand 4.5, Tailwind CSS 3.4, React Router 6, Lucide icons |
| **Infrastructure** | Docker (multi-stage builds), docker-compose, Nginx 1.27, Redis 7 (stubbed for future Task 8) |
| **Tooling** | Ruff (lint), pytest + pytest-asyncio, npm + ESLint |

---

## 3. Architecture Diagram

```mermaid
graph TB
    subgraph Client
        Browser["Browser"]
    end

    subgraph "Production (Docker)""
        Nginx["Nginx :80"]
        FrontendProd["Frontend (prod) :3000"]
    end

    subgraph "Development"
        Vite["Vite Dev Server :5173"]
    end

    subgraph "Backend Services"
        APIGateway["API Gateway :8000"]
        ModelService["Model Service :8001"]
        WorkerService["Worker Service :8002"]
        Shared["shared/ module"]
    end

    subgraph "External"
        Groq["Groq Cloud API"]
        Redis["Redis :6379 (stub)"]
    end

    %% Production flow
    Browser -->|"HTTP"| Nginx
    Nginx -->|"/api/*"| APIGateway
    Nginx -->|"/*"| FrontendProd

    %% Dev flow
    Browser -.->|"HTTP (dev)"| Vite
    Vite -.->|"proxy /api/*"| APIGateway

    %% Backend routing
    APIGateway -->|"HTTP"| ModelService
    APIGateway -->|"HTTP"| WorkerService
    WorkerService -->|"inference calls"| ModelService
    ModelService -->|"LLM requests"| Groq

    %% Shared module
    APIGateway -.-|"imports"| Shared
    ModelService -.-|"imports"| Shared
    WorkerService -.-|"imports"| Shared

    %% Future
    WorkerService -.->|"future: Task 8"| Redis
```

**Legend:** Solid lines = active connections. Dashed lines = dev-mode or future paths.

---

## 4. Service Inventory

| Service | Port | Responsibility | Docker Image |
|---------|------|---------------|--------------|
| **Nginx** (reverse proxy) | 80 | Routes traffic, SSE support, static serving | `nginx:1.27-alpine` |
| **API Gateway** | 8000 | Public API, CORS, request logging, timing middleware | `python:3.11-slim` |
| **Model Service** | 8001 | LLM inference via Groq API, model fallback, streaming | `python:3.11-slim` |
| **Worker Service** | 8002 | Background batch job processing, queue management | `python:3.11-slim` |
| **Frontend** (dev) | 5173 | React SPA with Vite HMR, dev proxy | N/A (Vite dev server) |
| **Frontend** (prod) | 3000 | Static SPA served by nginx | `node:20-alpine` -> `nginx:1.27-alpine` |
| **Redis** | 6379 | Queue backend (stub, used in Task 8) | `redis:7-alpine` |

---

## 5. Repository Structure

```
prod-ai-system-design/
├── architecture/              # This documentation (you are here)
├── baseline/                  # Production services
│   ├── api_gateway/           # Public API entry point (:8000)
│   ├── model_service/         # LLM inference engine (:8001)
│   ├── worker_service/        # Async job processor (:8002)
│   ├── shared/                # Cross-cutting: config, logging, schemas, errors, HTTP client
│   ├── infra/                 # Nginx config, Dockerfile.nginx
│   ├── protos/                # gRPC definitions (Task 1 extension)
│   ├── tests/                 # Integration tests
│   └── docker-compose.yml
├── frontend/                  # React + Vite SPA
│   ├── src/                   # Components, stores, hooks, API client
│   ├── Dockerfile             # Multi-stage build
│   └── nginx.conf             # SPA routing config
├── workshop/                  # Teaching materials
│   ├── part1_design_patterns/ # Tasks 1-4 (complete)
│   ├── part2_scalability/     # Tasks 5-8 (pending)
│   └── part3_security/        # Tasks 9-11 (pending)
├── scripts/                   # setup.sh, run_all.sh, check_health.sh
├── pyproject.toml             # Python project config
├── Makefile                   # Developer commands
├── .env.example               # Configuration template
└── CLAUDE.md                  # System design directives
```

---

## 6. Request Flow

A typical inference request follows this path:

1. **Browser** sends `POST /api/generate` with a prompt.
2. **Nginx** (prod) or **Vite proxy** (dev) forwards the request to the **API Gateway** on port 8000.
3. **API Gateway** logs the request, starts a timing middleware, validates the payload, and forwards it to the **Model Service** on port 8001.
4. **Model Service** calls the **Groq Cloud API** with the configured model (with fallback logic if the primary model is unavailable).
5. The response streams back through the same chain to the browser.

For background jobs, the **API Gateway** dispatches to the **Worker Service** on port 8002, which manages a job queue and calls the **Model Service** for inference when processing each item.

---

## 7. Workshop Context

The baseline codebase evolves across three workshop parts:

### Part I -- Design Patterns (Tasks 1-4) -- Complete

| Task | Topic | What It Adds |
|------|-------|-------------|
| 1 | REST vs gRPC | gRPC service definitions, benchmarking scripts |
| 2 | Microservices vs Monolith | Service decomposition, inter-service communication |
| 3 | Batch vs Real-time vs Streaming | Three inference pipeline modes |
| 4 | FastAPI Dependency Injection | Injected model loader, config manager, auth middleware |

### Part II -- Scalability & Performance (Tasks 5-8) -- Pending

| Task | Topic | What It Adds |
|------|-------|-------------|
| 5 | Code Profiling & Optimization | cProfile integration, bottleneck analysis |
| 6 | Concurrency & Parallelism | Async handling, threading, multiprocessing comparison |
| 7 | Memory Management | Lazy loading, model sharing, memory monitoring |
| 8 | Load Balancing & Caching | Nginx load balancer, Redis caching layer |

### Part III -- Security (Tasks 9-11) -- Pending

| Task | Topic | What It Adds |
|------|-------|-------------|
| 9 | Authentication vs Authorization | JWT auth, role-based access control |
| 10 | Securing API Endpoints | HTTPS, CORS hardening, rate limiting |
| 11 | Secrets Management | Secret manager abstraction, no hardcoded secrets |

---

## 8. Cross-References

- [Backend Architecture](backend-architecture.md) -- Service internals, shared module design, API contracts
- [Frontend Architecture](frontend-architecture.md) -- Component tree, state management, API client
- [Infrastructure](infrastructure.md) -- Docker setup, Nginx config, networking, environment variables
- [Getting Started](getting-started.md) -- Local setup, running the system, health checks
