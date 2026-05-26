# Antigravity Trace: Lightweight LLM Inference Telemetry & Ingestion System

**Antigravity Trace** is a high-fidelity, real-time observability and telemetry system for Large Language Model (LLM) applications. Built as a microservices architecture, it instruments LLM calls, absorbs logs in an event-driven ingestion pipeline, applies PII redaction, saves telemetry in PostgreSQL, and delivers a stunning, reactive analytics dashboard with multi-turn chatbot controls.

---

## 🚀 Refactored Front-End Tech Stack
We have refactored our front-end client using an extremely modern, clean, and highly type-safe stack:
*   **Bun**: Fast JS package manager and tool builder.
*   **Tailwind CSS**: Core utility-first CSS styling.
*   **Ant Design (antd) & ConfigProvider**: Official enterprise UI components styled under custom Dark Algorithms and brand neon colors.
*   **Axios & TanStack React Query**: Strongly typed client API and caching queries with WebSocket auto-invalidations.
*   **openapi-typescript**: End-to-end type safety mapping our API endpoints directly from the FastAPI OpenAPI spec contract.

---

## 🚀 Quick Start Guide (Local Mode)

Ensure you have **Bun** (v1.x) installed on your system.

### 1. Install & Build Frontend
Navigate to `/frontend` and run:
```bash
# 1. Install dependencies via Bun
bun install

# 2. Compile type safety from the OpenAPI schema
bun run gen:types

# 3. Start the local dev server
bun run dev
```

### 2. Launch the Microservices Pipeline
You can still boot the entire microservice ecosystem with a single command:
```bash
docker-compose up --build
```
This single command spins up PostgreSQL, Redis, RabbitMQ, Adminer, the Ingestion API, the Worker, the Chatbot API, and the React Frontend under Bun Alpine containers.

Open your browser and navigate to:
👉 **[http://localhost:8080](http://localhost:8080)**

---

## 🔑 Type-Safe OpenAPI Schema Pipeline

Our backend APIs define precise Pydantic schemas representing request and response payloads. We capture these in a static schema at the root folder `openapi.json`.

We use `openapi-typescript` to compile this schema into TypeScript types.

```bash
# Compile types using the generated OpenAPI specification
bun run gen:types
```

This writes strict, runtime-free TypeScript interfaces directly to `/frontend/src/schema.d.ts`!

### Type-Safe Integration Example:
```typescript
import { apiService, type TelemetryLogResponse } from "./api";
import { useQuery } from "@tanstack/react-query";

// 1. Fetching logs securely with React Query
const logsQuery = useQuery<TelemetryLogResponse[]>({
  queryKey: ["logs"],
  queryFn: apiService.getRecentLogs,
});

// 2. Logging and rendering properties safely
console.log(logsQuery.data?.[0]?.tokens_total); // Safe compiled check!
```

---

## 🏛️ Microservice Topology & Port Mappings

```
┌────────────────────────────────────────────────────────────────────────┐
│                        ANTIGRAVITY TRACE NETWORK                       │
├───────────────────┬──────────────┬───────────────────┬─────────────────┤
│ Service Name      │ Host Port    │ Internal Port     │ Tech Stack      │
├───────────────────┼──────────────┼───────────────────┼─────────────────┤
│ telemetry_frontend│ 8080         │ 80                │ React, TS, Nginx│
│ telemetry_chatbot │ 8005         │ 8000              │ FastAPI, Python │
│ telemetry_ingest  │ 8001         │ 8001              │ FastAPI, Python │
│ telemetry_worker  │ [internal]   │ [worker loop]     │ Python, SQLAL   │
│ telemetry_redis   │ 6385         │ 6379              │ Redis Server    │
│ telemetry_postgres│ 5435         │ 5432              │ PostgreSQL 15   │
│ telemetry_rabbitmq│ 5672, 15672  │ 5672, 15672       │ RabbitMQ Broker │
│ telemetry_adminer │ 8085         │ 8080              │ Adminer DB Tool │
└───────────────────┴──────────────┴───────────────────┴─────────────────┘
```

---

## 📦 Telemetry SDK & DB Schema

The SDK wraps standard unary and streaming LLM calls on secondary daemon threads, adding **0ms** of user-perceived delay. It redacts phone numbers, emails, credit cards, SSNs, and API keys automatically.

The PostgreSQL schema decouples conversational data (`conversations`, `messages` cascade on delete) from observability metrics (`inference_logs` set null on delete). **Deleting a conversation purges chat transcripts for user privacy, but maintains the telemetry statistics for long-term analytics logs!**

---

## ⚖️ Engineering Compromises & Tradeoffs

1.  **React Query Cache Invalidations vs. Live Array Pushing**:
    *   *Compromise*: WebSocket log messages invalidate React Query query caches rather than executing direct state slicing and mutations.
    *   *Rationale*: Appending new items to an active timeseries array manually breaks sorting and state synchronization. Invalidating React Query queries triggers standard cache updates, ensuring that latency averages, counts, and line charts remain 100% correct, synchronized, and unified across multiple browser tabs!
2.  **Clean Ant Design Dark Algos vs. Vanilla Tailwind**:
    *   *Compromise*: Wrapped our layout in Ant Design `ConfigProvider` dark algorithms, styled alongside custom Tailwind boxes.
    *   *Rationale*: Building complex accessible tables, text areas, and sliding code drawer components in pure Tailwind takes significant code lines. Utilizing Ant Design provides enterprise-grade, accessibility-compliant components, and customizing their base tokens inside `ConfigProvider` aligns their aesthetic perfectly with our slate dark carbon radial glow.
3.  **Local Static `openapi.json` vs. Active Swagger Pulling**:
    *   *Compromise*: Dumped a local `openapi.json` at the root folder to generate types rather than fetching it from a running dev server.
    *   *Rationale*: Fetching from a running server requires starting the Python stack, PostgreSQL, and Redis locally in the terminal during build. Keeping a static OpenAPI spec allows you to run `bun install && bun run gen:types && bun run build` at any time without booting any services.
