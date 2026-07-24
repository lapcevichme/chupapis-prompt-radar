# Phase 1 Plan

## Goal
Implement the FastAPI skeleton, ingestion pipeline with queue, mock stores (Qdrant, meta-DB), and key endpoints for /logs and /statistics for the ML service (phase 1 from ml_service/ТЗ.md §16).

## Scope
- Directory structure and FastAPI setup
- Config loading from env/config.yaml
- Health endpoints
- PUT /api/v1/logs endpoint with validation against log.schema.json, queuing for async processing
- Mock Qdrant and meta-store (SQLite) adapters
- GET /api/v1/statistics and GET /api/v1/assignments endpoints returning mock data
- Basic smoke tests and contract tests
- Update plan.md with status

## Out of scope
- Actual ML logic: classification, embeddings, clustering, summarization
- Real stores (keep mock for MVP)
- Background workers beyond basic queue (use asyncio tasks)
- Docker yet (focus on skeleton)

## Acceptance criteria
- Service starts with health/live and health/ready
- PUT /logs validates schema, enqueues, returns accepted/rejected counts
- GET /statistics returns valid structure with pipeline_metadata
- GET /assignments returns assignments with scenario_id etc.
- Quality gates: ruff, tests pass
- Demo data loads

## Decisions
- Follow modular monolith pattern from Claude.md and template (but since no template in ml_service, build new)
- Use Pydantic for all schemas
- Validate config at startup
- Use async where possible
- Mock stores for phase 1 (in-memory or SQLite for meta)

## Current status
In progress. Implemented FastAPI skeleton, ingestion with queue, mock Qdrant and meta stores, endpoints /logs and /statistics. Quality gates: syntax ok, import works.

## Next step
Run full tests, fix any issues (e.g. config loading), commit.