# Workshop Materials — Designing Production AI Systems

This directory contains all teaching materials, hands-on labs, and reference solutions for the workshop series.

## Prerequisites

Before starting any task:
1. Complete the project setup: `bash scripts/setup.sh`
2. Verify the baseline runs: `make run` (or `make run-docker`)
3. Set `USE_MOCK=true` in `.env` if you don't have a Groq API key

> **New to the baseline?** Work through **[Part 0](#part-0-baseline-introduction)** first. It tours the existing system (architecture, lifecycle, request flows, persistence, frontend) so Part I's refactors make sense.

## Part 0: Baseline Introduction

Orientation module. Tours the current production-AI baseline so newcomers have a mental model before Part I starts refactoring it. Finish Part 0 and you'll know *what* you're changing and *why* — instead of guessing.

| Lesson | Topic | Time | Difficulty | Lab |
|--------|-------|------|------------|-----|
| [0.1](part0_introduction/task01_getting_started/) | Getting Started — Dev Environment Walkthrough | 45 min | Beginner | Full (starter + solution) |
| [0.2](part0_introduction/task02_system_architecture/) | System Architecture Tour | 30 min | Beginner | Lightweight |
| [0.3](part0_introduction/task03_lifecycle_and_di/) | Service Lifecycle & Dependency Injection | 45 min | Intermediate | Full (starter + solution) |
| [0.4](part0_introduction/task04_request_flows/) | Request Flows — Sync, Streaming, Jobs | 45 min | Intermediate | Lightweight |
| [0.5](part0_introduction/task05_persistence_observability/) | Persistence, Config, and Observability | 45 min | Intermediate | Lightweight |
| [0.6](part0_introduction/task06_frontend_primer/) | Frontend Primer — Layout, Stores, Streaming | 45 min | Beginner | Lightweight |

## Part I: Design Patterns for GenAI Systems

| Task | Topic | Time | Difficulty | Prerequisites |
|------|-------|------|------------|---------------|
| [Task 1](part1_design_patterns/task01_rest_vs_grpc/) | REST APIs vs gRPC | 45 min | Intermediate | Baseline running |
| [Task 2](part1_design_patterns/task02_microservices_vs_monolith/) | Microservices vs Monolith | 60 min | Beginner-Intermediate | None |
| [Task 3](part1_design_patterns/task03_batch_realtime_streaming/) | Batch vs Real-time vs Streaming | 45 min | Intermediate | Model Service running |
| [Task 4](part1_design_patterns/task04_dependency_injection/) | FastAPI Dependency Injection | 30 min | Beginner-Intermediate | None |

## Part II: Scalability & Performance (Coming Soon)

| Task | Topic |
|------|-------|
| Task 5 | Code Profiling & Optimization |
| Task 6 | Concurrency & Parallelism |
| Task 7 | Memory Management |
| Task 8 | Load Balancing & Caching |

## Part III: Security (Coming Soon)

| Task | Topic |
|------|-------|
| Task 9 | Authentication vs Authorization |
| Task 10 | Securing API Endpoints |
| Task 11 | Secrets Management |

## How Each Task Is Structured

```
taskNN_topic/
├── README.md              # Concept explanation (beginner → advanced)
├── lab/
│   ├── README.md          # Hands-on instructions
│   ├── starter/           # Your starting point
│   └── solution/          # Complete reference solution
├── slides.md              # Presentation outline
└── production_reality.md  # What breaks in real systems
```

## Suggested Workshop Formats

### Half-Day (4 hours) — Part 0 only
All 6 Part 0 lessons in order. Attendees leave with a full mental model of the baseline and can independently extend it afterwards.

### Half-Day (4 hours) — Part I only
Pick 2-3 tasks. Recommended: Tasks 2, 1, 4 (assumes attendees already know the baseline).

### Full-Day (8 hours) — Part 0 + Part I
Morning: Lessons 0.1 → 0.3 (setup + architecture + lifecycle). Afternoon: Tasks 2 → 4 → 1.

### Multi-Session (3 × 2 hours)
- Session 1: Part 0 (baseline orientation)
- Session 2: Tasks 2 + 4 (architecture foundations)
- Session 3: Tasks 1 + 3 (communication patterns) + discussion

## Participant Workflow

1. Read `taskNN/README.md` for conceptual understanding
2. Open `taskNN/lab/README.md` for hands-on instructions
3. Work in the `lab/starter/` directory
4. Compare with `lab/solution/` when stuck or after completing
5. Read `production_reality.md` for depth
