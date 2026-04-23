// ---------------------------------------------------------------------------
// Workshop Topics Data — static typed tree of all 11 workshop tasks
// ---------------------------------------------------------------------------

import type { LucideIcon } from 'lucide-react';
import { BookOpen, FlaskConical, Presentation, AlertTriangle } from 'lucide-react';

// ---- Types ----------------------------------------------------------------

export type PartId = '0' | 'I' | 'II' | 'III';
export type Difficulty = 'beginner' | 'intermediate' | 'advanced';

export interface Subtopic {
  id: string;
  label: string;
  /** Relative path within workshop/ — null for unimplemented tasks */
  filePath: string | null;
  icon: LucideIcon;
  description: string;
}

export interface WorkshopTask {
  id: string;
  taskNumber: number;
  title: string;
  description: string;
  duration: string;
  difficulty: Difficulty;
  part: PartId;
  /** true = Part I tasks with real markdown files */
  implemented: boolean;
  subtopics: Subtopic[];
}

// ---- Helpers --------------------------------------------------------------

function makeSubtopics(
  slug: string,
  implemented: boolean,
  partPrefix = 'part1_design_patterns',
): Subtopic[] {
  const base = implemented
    ? `${partPrefix}/${slug}`
    : null;

  return [
    {
      id: 'overview',
      label: 'Overview',
      filePath: base ? `${base}/README.md` : null,
      icon: BookOpen,
      description: 'Concepts, comparisons, and diagrams',
    },
    {
      id: 'lab',
      label: 'Lab',
      filePath: base ? `${base}/lab/README.md` : null,
      icon: FlaskConical,
      description: 'Hands-on exercises with starter and solution code',
    },
    {
      id: 'slides',
      label: 'Slides',
      filePath: base ? `${base}/slides.md` : null,
      icon: Presentation,
      description: 'Slide presentation for this topic',
    },
    {
      id: 'production-reality',
      label: 'Production Reality',
      filePath: base ? `${base}/production_reality.md` : null,
      icon: AlertTriangle,
      description: 'What breaks at scale and what senior engineers do about it',
    },
  ];
}

// ---- Task definitions -----------------------------------------------------

export const WORKSHOP_TASKS: WorkshopTask[] = [
  // Part 0 — Baseline Introduction
  // Preparatory material that tours the existing baseline system before
  // attendees touch Part I refactors. Task numbers are 0.1–0.6 so they sort
  // cleanly ahead of Part I's integer task numbers while remaining globally
  // unique in display ("Task 0.1: Getting Started ...").
  {
    id: 'task0_1',
    taskNumber: 0.1,
    title: 'Getting Started — Dev Environment Walkthrough',
    description:
      'Clone, install, and run the 3-service baseline + Postgres locally. Learn what every make target does and verify health end-to-end.',
    duration: '45 min',
    difficulty: 'beginner',
    part: '0',
    implemented: true,
    subtopics: makeSubtopics('task01_getting_started', true, 'part0_introduction'),
  },
  {
    id: 'task0_2',
    taskNumber: 0.2,
    title: 'System Architecture Tour',
    description:
      'The 3-service split (gateway / model / worker), what lives in shared/, and how the request pipeline is wired. Mental model before the refactors.',
    duration: '30 min',
    difficulty: 'beginner',
    part: '0',
    implemented: true,
    subtopics: makeSubtopics('task02_system_architecture', true, 'part0_introduction'),
  },
  {
    id: 'task0_3',
    taskNumber: 0.3,
    title: 'Service Lifecycle & Dependency Injection',
    description:
      'FastAPI lifespan context managers, module-global dependency init, and the Depends() pattern that recurs in every service. Foundations for Part I Task 4.',
    duration: '45 min',
    difficulty: 'intermediate',
    part: '0',
    implemented: true,
    subtopics: makeSubtopics('task03_lifecycle_and_di', true, 'part0_introduction'),
  },
  {
    id: 'task0_4',
    taskNumber: 0.4,
    title: 'Request Flows — Sync, Streaming, Jobs',
    description:
      'Trace a request end-to-end through sync /generate, SSE /generate/stream, and the Postgres-backed job queue. Watch request IDs propagate across services.',
    duration: '45 min',
    difficulty: 'intermediate',
    part: '0',
    implemented: true,
    subtopics: makeSubtopics('task04_request_flows', true, 'part0_introduction'),
  },
  {
    id: 'task0_5',
    taskNumber: 0.5,
    title: 'Persistence, Config, and Observability',
    description:
      'ORM models, Alembic migrations, Pydantic Settings, structlog, and the AppError hierarchy — the state + telemetry layer Parts II & III will extend.',
    duration: '45 min',
    difficulty: 'intermediate',
    part: '0',
    implemented: true,
    subtopics: makeSubtopics('task05_persistence_observability', true, 'part0_introduction'),
  },
  {
    id: 'task0_6',
    taskNumber: 0.6,
    title: 'Frontend Primer — Layout, Stores, Streaming',
    description:
      'Three-panel layout, Zustand stores, server-backed chat cache, and SSE token reconciliation on the client.',
    duration: '45 min',
    difficulty: 'beginner',
    part: '0',
    implemented: true,
    subtopics: makeSubtopics('task06_frontend_primer', true, 'part0_introduction'),
  },
  // Part I — Design Patterns
  {
    id: 'task01',
    taskNumber: 1,
    title: 'REST vs gRPC',
    description:
      'Implement both REST and gRPC interfaces for the model inference service. Benchmark latency and understand when each protocol excels.',
    duration: '45 min',
    difficulty: 'intermediate',
    part: 'I',
    implemented: true,
    subtopics: makeSubtopics('task01_rest_vs_grpc', true),
  },
  {
    id: 'task02',
    taskNumber: 2,
    title: 'Microservices vs Monolith',
    description:
      'Refactor a monolithic AI app into microservices. Understand deployment complexity, failure isolation, and service boundaries.',
    duration: '60 min',
    difficulty: 'intermediate',
    part: 'I',
    implemented: true,
    subtopics: makeSubtopics('task02_microservices_vs_monolith', true),
  },
  {
    id: 'task03',
    taskNumber: 3,
    title: 'Batch vs Real-time vs Streaming',
    description:
      'Implement three inference pipelines and understand the tradeoffs: throughput vs latency vs resource usage.',
    duration: '60 min',
    difficulty: 'intermediate',
    part: 'I',
    implemented: true,
    subtopics: makeSubtopics('task03_batch_realtime_streaming', true),
  },
  {
    id: 'task04',
    taskNumber: 4,
    title: 'FastAPI Dependency Injection',
    description:
      'Master DI patterns in FastAPI for AI systems — injected model loaders, config managers, and testability improvements.',
    duration: '45 min',
    difficulty: 'intermediate',
    part: 'I',
    implemented: true,
    subtopics: makeSubtopics('task04_dependency_injection', true),
  },
  // Part II — Scalability & Performance
  {
    id: 'task05',
    taskNumber: 5,
    title: 'Code Profiling & Optimization',
    description:
      'Profile model inference code with cProfile and line_profiler. Identify CPU vs I/O bottlenecks and learn when optimization matters.',
    duration: '45 min',
    difficulty: 'advanced',
    part: 'II',
    implemented: false,
    subtopics: makeSubtopics('task05_profiling', false),
  },
  {
    id: 'task06',
    taskNumber: 6,
    title: 'Concurrency & Parallelism',
    description:
      'Compare async, multi-threading, and multi-processing under load. Understand the GIL and when to use each approach.',
    duration: '60 min',
    difficulty: 'advanced',
    part: 'II',
    implemented: false,
    subtopics: makeSubtopics('task06_concurrency', false),
  },
  {
    id: 'task07',
    taskNumber: 7,
    title: 'Memory Management',
    description:
      'Simulate memory issues in AI systems. Learn lazy loading, model sharing strategies, and memory monitoring tools.',
    duration: '45 min',
    difficulty: 'advanced',
    part: 'II',
    implemented: false,
    subtopics: makeSubtopics('task07_memory', false),
  },
  {
    id: 'task08',
    taskNumber: 8,
    title: 'Load Balancing & Caching',
    description:
      'Add Nginx load balancer and Redis caching layer. Demonstrate cache hits vs misses and horizontal scaling.',
    duration: '60 min',
    difficulty: 'advanced',
    part: 'II',
    implemented: false,
    subtopics: makeSubtopics('task08_load_balancing', false),
  },
  // Part III — Security
  {
    id: 'task09',
    taskNumber: 9,
    title: 'Authentication vs Authorization',
    description:
      'Implement JWT authentication and role-based access control. Clearly understand Auth vs AuthZ.',
    duration: '60 min',
    difficulty: 'advanced',
    part: 'III',
    implemented: false,
    subtopics: makeSubtopics('task09_auth', false),
  },
  {
    id: 'task10',
    taskNumber: 10,
    title: 'Securing API Endpoints',
    description:
      'Secure the system with HTTPS, CORS configuration, and rate limiting. Simulate common attacks.',
    duration: '60 min',
    difficulty: 'advanced',
    part: 'III',
    implemented: false,
    subtopics: makeSubtopics('task10_securing_endpoints', false),
  },
  {
    id: 'task11',
    taskNumber: 11,
    title: 'Secrets Management',
    description:
      'Implement proper secrets handling — env vars, .env files, secret manager abstraction. No hardcoded secrets.',
    duration: '45 min',
    difficulty: 'advanced',
    part: 'III',
    implemented: false,
    subtopics: makeSubtopics('task11_secrets', false),
  },
];

// ---- Derived helpers ------------------------------------------------------

export const PART_LABELS: Record<PartId, string> = {
  '0': 'Part 0 — Baseline Introduction',
  I: 'Part I — Design Patterns',
  II: 'Part II — Scalability & Performance',
  III: 'Part III — Security',
};

export const TASKS_BY_PART: Record<PartId, WorkshopTask[]> = {
  '0': WORKSHOP_TASKS.filter((t) => t.part === '0'),
  I: WORKSHOP_TASKS.filter((t) => t.part === 'I'),
  II: WORKSHOP_TASKS.filter((t) => t.part === 'II'),
  III: WORKSHOP_TASKS.filter((t) => t.part === 'III'),
};

export function getTask(id: string): WorkshopTask | undefined {
  return WORKSHOP_TASKS.find((t) => t.id === id);
}

export function getSubtopic(taskId: string, subtopicId: string): Subtopic | undefined {
  return getTask(taskId)?.subtopics.find((s) => s.id === subtopicId);
}
