<!-- Version: v0 | Last updated: 2026-04-16 | Status: current -->

# Prodigon Architecture Documentation

Comprehensive architecture documentation for the Prodigon AI platform — a multi-service AI assistant built with FastAPI, React, and Groq.

## Document Index

| Document | Purpose | Version |
|----------|---------|---------|
| [System Overview](system-overview.md) | High-level architecture, tech stack, service inventory, repo structure | v0 |
| [Backend Architecture](backend-architecture.md) | Services deep dive: Gateway, Model, Worker, Shared module, DI pattern | v0 |
| [Frontend Architecture](frontend-architecture.md) | React SPA: components, stores, hooks, streaming, build pipeline | v0 |
| [API Reference](api-reference.md) | Complete endpoint reference with schemas, examples, and error codes | v0 |
| [Data Flow](data-flow.md) | User flows with sequence diagrams: streaming, jobs, health monitoring | v0 |
| [Infrastructure](infrastructure.md) | Docker, Nginx, networking, deployment modes, environment config | v0 |
| [Getting Started](getting-started.md) | Step-by-step setup guide with troubleshooting for all known issues | v0 |
| [Design Decisions](design-decisions.md) | 8 Architecture Decision Records (ADRs) with rationale | v0 |

## Reading Order

**New to the project?** Start here:
1. [Getting Started](getting-started.md) — set up and run the system
2. [System Overview](system-overview.md) — understand the big picture
3. [Data Flow](data-flow.md) — see how requests flow through the system

**Backend developer?**
1. [Backend Architecture](backend-architecture.md) — services, DI, config, shared module
2. [API Reference](api-reference.md) — endpoint contracts

**Frontend developer?**
1. [Frontend Architecture](frontend-architecture.md) — components, stores, streaming
2. [API Reference](api-reference.md) — what the backend provides

**Understanding design choices?**
1. [Design Decisions](design-decisions.md) — why things are built this way

**Deploying or configuring?**
1. [Infrastructure](infrastructure.md) — Docker, Nginx, ports, env vars

## Versioning Policy

These documents are **Version 0 (v0)** — the initial architecture as of 2026-04-16.

### When to version

Create a new version when:
- Service boundaries change (new service added, service merged/split)
- New infrastructure components added (e.g., Redis queue in Task 8, JWT auth in Task 9)
- Breaking API changes (endpoint paths, request/response schemas)
- Major frontend restructuring

Do **not** version for:
- Typo fixes or clarification improvements
- Adding detail to existing sections
- Minor bug fixes that don't change architecture

### How to version

1. Copy all current files to `architecture/versions/v0/`
2. Update the version header in each main file: `<!-- Version: v1 | Last updated: YYYY-MM-DD | Status: current -->`
3. Update the version column in the Document Index table above
4. Add a changelog entry below

### Changelog

| Version | Date | Summary |
|---------|------|---------|
| v0 | 2026-04-16 | Initial architecture documentation. Covers baseline services, React frontend, Docker infrastructure, and 8 ADRs. |

## Diagrams

Architecture diagrams use [Mermaid](https://mermaid.js.org/) syntax. They render natively on GitHub. For local viewing, use:
- VS Code: [Markdown Preview Mermaid Support](https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid) extension
- JetBrains: Built-in Mermaid support in markdown preview
- CLI: `npx @mermaid-js/mermaid-cli` for PNG/SVG export
