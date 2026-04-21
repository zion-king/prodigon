# Slides: Microservices vs Monolith

**Duration:** ~30 minutes
**Audience:** Engineers building or evaluating AI system architectures

---

## Slide 1: Title

**Microservices vs Monolith: When to Split Your AI System**

Key question: Should you start with one app or many services?
(Spoiler: It depends. But you should understand the tradeoffs before deciding.)

---

## Slide 2: What Is a Monolith?

- A single deployable unit containing ALL application logic
- One codebase, one process, one deployment pipeline
- Example: `monolith.py` -- API + inference + jobs in 300 lines

**Diagram:** Single box containing all components

```
+------------------------------------------+
|              Monolith (:8000)             |
|                                          |
|  [Routes] -> [Inference] -> [Groq API]  |
|  [Routes] -> [Job Queue] -> [Worker]    |
|  [Middleware] [Config] [Logging]         |
+------------------------------------------+
```

---

## Slide 3: What Are Microservices?

- Multiple small, independent services, each doing one thing
- Each has its own process, deployment, and (ideally) data store
- Communicate over the network (HTTP, gRPC, message queues)

**Diagram:** Three boxes connected by arrows

```
[Gateway :8000] --HTTP--> [Model Service :8001] --> [Groq API]
[Gateway :8000] --HTTP--> [Worker Service :8002] --HTTP--> [Model Service :8001]
```

---

## Slide 4: The Tradeoff Space

| | Monolith | Microservices |
|---|---|---|
| Simplicity | High | Low |
| Scalability | Limited | High |
| Fault isolation | None | Strong |
| Team independence | Low | High |
| Debugging | Easy | Hard |
| Deployment speed | Fast (one thing) | Fast (per service) |
| Operational cost | Low | High |

**Key insight:** Microservices do not reduce complexity. They move it from code to infrastructure.

---

## Slide 5: Why Monoliths Win Early

- Faster to build (no network, no orchestration, no service discovery)
- Easier to debug (one log stream, one stack trace)
- Cheaper to run (one container vs many)
- Easier to refactor (rename a function, not a service contract)
- Lower cognitive load for small teams

**Martin Fowler's advice:** "Almost all the successful microservice stories have started with a monolith that got too big and was broken up."

---

## Slide 6: When Monoliths Break

- **Deployment coupling:** Changing inference logic requires deploying the whole app
- **Scaling bottleneck:** Cannot scale inference independently from the API
- **Team friction:** 10 developers stepping on each other in one codebase
- **Blast radius:** A bug in the worker crashes the entire API
- **Technology lock-in:** Everything must use the same language/framework

---

## Slide 7: Why Microservices Win Later

- **Independent scaling:** Run 5 inference instances, 1 gateway, 1 worker
- **Fault isolation:** Bad model version crashes Model Service, not the API
- **Team ownership:** Team A owns inference, Team B owns the gateway
- **Technology flexibility:** Inference in Python, gateway in Go
- **Independent deployments:** Ship a fix to inference without touching jobs

---

## Slide 8: When Microservices Hurt

- **Network is not free:** Every service call can fail, time out, or be slow
- **Distributed debugging:** A bug might span 3 services and 3 log streams
- **Data consistency:** No transactions across service boundaries
- **Operational overhead:** Docker, orchestration, service mesh, monitoring
- **Distributed monolith risk:** Services too tightly coupled = worst of both worlds

---

## Slide 9: The Middle Ground -- Modular Monolith

```
Monolith --> Modular Monolith --> Selective Extraction --> Microservices
```

- Enforce module boundaries within one deployable unit
- Clear interfaces between modules (no reaching into internals)
- Can extract modules into services when there is a concrete reason
- Shopify does this at massive scale

---

## Slide 10: Decision Framework

**Choose monolith when:**
- Team < 5 engineers
- MVP / exploration phase
- Domain boundaries unclear
- Need to ship fast

**Choose microservices when:**
- Multiple teams need independent deployments
- Specific components need independent scaling
- Fault isolation is critical
- You have the operational maturity

**Choose modular monolith when:**
- Team 5-15 engineers
- Want clean boundaries without distributed systems overhead
- Preparing for future extraction

---

## Slide 11: Real-World Case Studies

**Amazon:** Monolith -> hundreds of microservices (thousands of deploys/day)
**Netflix:** Monolith -> 700+ microservices (pioneered circuit breakers, service mesh)
**Shopify:** Stayed modular monolith (strict boundaries, single deploy)

All started with monoliths. Decomposition was driven by specific pain points, not trends.

---

## Slide 12: AI System Specific Considerations

AI systems have unique characteristics that affect the decision:

- **GPU resources are expensive** -- you want to scale inference separately from CPU-bound API/worker logic
- **Model loading is slow** -- cold-starting a service with a model takes seconds/minutes
- **Inference latency varies** -- batch vs real-time have different resource profiles
- **Models change frequently** -- decoupling model deployment from API deployment reduces risk

These characteristics often push AI systems toward microservices earlier than typical web apps.

---

## Slide 13: Live Demo

1. Run `monolith.py` -- show all endpoints working from one process
2. Show the baseline microservices -- three services, same API
3. Kill Model Service -- show Gateway still responds (with errors for inference)
4. Restart Model Service -- full recovery

---

## Slide 14: The Refactoring Pattern

How to extract a service from a monolith:

1. Identify the boundary (what data and logic belong together)
2. Create the new service with its own routes
3. Replace direct calls with HTTP/gRPC calls
4. Add service discovery (env vars, DNS, service mesh)
5. Deploy both in parallel, then cut over
6. Remove the old code from the monolith

**Rule:** Extract the most independent piece first (fewest dependencies on other code).

---

## Slide 15: What You Need for Microservices

Before going micro, make sure you have:

- [ ] Containerization (Docker)
- [ ] Orchestration (docker-compose, Kubernetes)
- [ ] Service discovery (env vars, DNS, Consul)
- [ ] Centralized logging (ELK, Datadog)
- [ ] Distributed tracing (Jaeger, X-Ray)
- [ ] Health checks and alerting
- [ ] CI/CD per service
- [ ] Timeout and retry policies

If you do not have most of these, the operational cost will outweigh the benefits.

---

## Slide 16: Summary

1. Start with a monolith unless you have strong reasons not to
2. Enforce clean module boundaries from day one
3. Extract services when you have evidence (scaling needs, team friction, fault isolation)
4. Invest in operational tooling before or alongside decomposition
5. The goal is not microservices -- the goal is a system that ships reliably and scales efficiently

---

## Slide 17: Hands-On Lab

Open `lab/starter/monolith.py` and follow `lab/starter/refactor_guide.md` to break it
into three services.

**Time:** 30-45 minutes

---

## Slide 18: Discussion Questions

1. At what team size would you recommend splitting this system?
2. Which service would you extract first if inference latency became a problem?
3. How would you handle a database shared between the monolith and a new service during migration?
4. What happens to your debugging workflow when requests span three services?
5. How does the "modular monolith" approach change your answer to question 1?
