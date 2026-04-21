# Workshop Materials — Designing Production AI Systems

This directory contains all teaching materials, hands-on labs, and reference solutions for the workshop series.

## Prerequisites

Before starting any task:
1. Complete the project setup: `bash scripts/setup.sh`
2. Verify the baseline runs: `make run` (or `make run-docker`)
3. Set `USE_MOCK=true` in `.env` if you don't have a Groq API key

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

### Half-Day (4 hours)
Pick 2-3 tasks. Recommended: Tasks 2, 1, 4

### Full-Day (8 hours)
All 4 Part I tasks in order: 2 → 4 → 1 → 3

### Multi-Session (3 × 2 hours)
- Session 1: Tasks 2 + 4 (architecture foundations)
- Session 2: Tasks 1 + 3 (communication patterns)
- Session 3: Discussion + extension exercises

## Participant Workflow

1. Read `taskNN/README.md` for conceptual understanding
2. Open `taskNN/lab/README.md` for hands-on instructions
3. Work in the `lab/starter/` directory
4. Compare with `lab/solution/` when stuck or after completing
5. Read `production_reality.md` for depth
