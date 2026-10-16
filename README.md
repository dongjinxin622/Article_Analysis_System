# SciPDF — AI-Powered Scientific Paper Analysis Platform

> End-to-end pipeline that turns research PDFs into structured knowledge: **PDF Parsing → NER → Relation Extraction → Domain Analysis → Report Generation**, orchestrated by LangGraph multi-agent workflows.

**[中文文档 / Chinese README](README.zh-CN.md)**

## Why This Project

Researchers reading materials-science literature spend most of their time on manual extraction: pulling entities, parameters, and process routes out of dozens of PDFs, then synthesizing them into review reports. SciPDF automates that entire workflow. For a research group using it in daily work, literature-review effort dropped by **~90%**, and the platform has processed 3,500+ papers end-to-end.

## Highlights

- **Full analysis pipeline** — upload a PDF and get entities, relations, domain profiles, and a generated analysis report, with live progress over WebSocket.
- **LangGraph multi-agent workflows** — ReAct-style planning with **human-in-the-loop (HITL) checkpoints**: the workflow pauses for expert review at key decision points instead of trusting the model blindly.
- **Plugin-based domain analyzers** — a `DomainRegistry` + abstract base class design; the REBCO superconductor domain (technical routes, experiment schemes, critical current density Jc metrics) ships as the first implementation.
- **Hybrid semantic retrieval on Milvus** — paper / entity / sentence-level vector search feeding RAG-style grounded analysis.
- **Custom Redis Streams task engine** — replaced Celery in v0.4: async task queues with consumer groups, at-least-once delivery, heartbeat-based **orphan-task recovery** (crashed workers' tasks are reclaimed and re-run instead of hanging), and scheduled cleanup jobs.
- **Production-minded operations** — JWT dual-token auth (access + refresh), per-user prompt-template management, real-time service health checks (PostgreSQL / Redis / Milvus / GROBID), Docker Compose deployment with Nginx HTTP/HTTPS auto-switching.

## Measured Results

| Metric | Result |
|---|---|
| Literature-review workload reduction (user-facing) | ~90% |
| Papers processed end-to-end | 3,500+ |
| NER throughput (single paper, E2E) | 135 entities / 29 groups in ~34 s |
| Deployment verification | 15/15 API functional checks passed |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (Vue 3)                        │
│      Vue 3.4 + Element Plus + Pinia + Vue Router + Vite     │
└───────────────────────────┬─────────────────────────────────┘
                            │  Nginx reverse proxy (HTTP/HTTPS)
┌───────────────────────────┴─────────────────────────────────┐
│                      Backend (FastAPI)                       │
│        FastAPI + SQLAlchemy 2.0 (asyncpg) + Uvicorn         │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ PDF svc │ │ NER svc │ │  RE svc  │ │ Domain analyzers │  │
│  └─────────┘ └─────────┘ └──────────┘ └──────────────────┘  │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ LLM svc │ │Vector svc│ │ Report  │ │  Prompt mgmt     │  │
│  └─────────┘ └─────────┘ └──────────┘ └──────────────────┘  │
│              LangGraph workflows (ReAct + HITL)              │
└──┬──────────┬───────────┬────────────┬──────────────────────┘
   │          │           │            │
┌──┴───┐ ┌───┴────┐ ┌────┴───┐ ┌──────┴──────┐
│Redis │ │Postgres│ │ Milvus │ │   GROBID    │
│ 7.x  │ │  16.x  │ │ (vect.)│ │  (PDF TEI)  │
└──┬───┘ └────────┘ └────────┘ └─────────────┘
   │
┌──┴──────────────────────────────┐
│   Task Worker (Redis Streams)   │
│  consumer groups · heartbeat ·  │
│  orphan-task recovery · cron    │
└─────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vue 3 + TypeScript, Element Plus, Pinia, Vite |
| Backend | Python / FastAPI, SQLAlchemy 2.0 (async), Uvicorn |
| Agent workflows | LangGraph + LangChain (ReAct planning, HITL) |
| Async tasks | Redis Streams (custom engine, replaced Celery in v0.4) |
| Databases | PostgreSQL 16, Milvus (vector), Redis 7 |
| PDF parsing | GROBID + SciPDF-Parser |
| NLP / LLM | Stanza, Transformers, OpenAI-compatible LLM API (Qwen) |
| Auth | JWT dual-token (python-jose) |
| Deployment | Docker Compose, Nginx (HTTP/HTTPS), certbot |

## Quick Start

```bash
# 1. Configure environment
cp .env.example .env        # fill in DB / Redis / Milvus / LLM credentials

# 2. Start all services
docker compose up -d

# 3. Verify
curl http://localhost:8000/health
```

Local development:

```bash
# backend
cd backend && pip install -r requirements.txt
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload

# frontend
cd frontend && npm install && npm run dev

# task worker (Redis Streams)
python -m backend.app.core.tasks.worker
```

## Project Structure

```
backend/
├── app/
│   ├── api/v1/          # REST endpoints (papers, ner, re, domain, tasks, ...)
│   ├── core/            # config, redis client, task engine (stream/engine/worker)
│   ├── domain/          # plugin-style domain analyzers (REBCO implemented)
│   ├── models/          # SQLAlchemy ORM
│   ├── schemas/         # Pydantic schemas
│   ├── services/        # pdf / ner / re / llm / embedding / milvus / report
│   ├── workflows/       # LangGraph multi-agent workflows
│   └── tasks/           # task definitions for the Redis Streams engine
├── tests/
frontend/                # Vue 3 + TypeScript SPA
prompts/                 # LLM prompt templates (NER / RE / domain)
scripts/                 # data migration & ops scripts
docker-compose.yml       # frontend / backend / task-worker / certbot
```

## Evaluation & Reliability

- **HITL review gates** in comprehensive-analysis workflows let domain experts intercept and correct agent decisions before report generation.
- **Task engine robustness**: heartbeat-based orphan-task detection reclaims tasks from crashed workers; scheduled jobs clean expired tasks, failed logs, and temp files.
- **Service health monitoring**: `/config/status` probes PostgreSQL, Redis, Milvus, and GROBID in real time.
- **E2E verification**: 15/15 API functional checks and full NER pipeline tests (upload → parse → extract → persist) pass on a deployed instance.

## License

For academic and portfolio use. See [README.zh-CN.md](README.zh-CN.md) for the original detailed documentation (Chinese).
