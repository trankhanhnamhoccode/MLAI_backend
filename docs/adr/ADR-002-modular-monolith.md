# ADR-002 — Modular Monolith for Competition MVP

## Status
ACCEPTED

## Context
Competition scope requires clear, reproducible delivery without distributed-system overhead.

## Decision
Use one FastAPI modular monolith on Python 3.11+, Pydantic v2 public boundaries,
application use cases and plain Python domains. Use synchronous application code and
SQLAlchemy Session. Route → application → domain/repository contracts → wired
infrastructure. Business rules do not live in routes or ORM models and domains do
not import API, SQLAlchemy models, HTTP clients, providers or filesystem implementations.
Local storage is sufficient. Introduce interfaces only for concrete use cases.

## Consequences
Vertical slices share one deployable backend, with explicit domain boundaries.
Future external HTTP calls may use async internally without converting business
computation to async. Empty packages are appropriate until a slice needs behavior.

## Rejected/Deferred alternatives
REJECTED for current scope: microservices, brokers, Kafka, Celery, Kubernetes,
distributed architecture, event sourcing, CQRS, enterprise IAM, generic agent
frameworks and unused repository/service abstractions.
DEFERRED: separate runtime boundaries without demonstrated need.

## Revisit conditions
Only concrete runtime requirements (measured scaling, isolation or deployment needs)
may justify a proposed distributed boundary.

## Affected areas
BE package layout/dependencies, API transport, infrastructure, ML/Data integration,
tests, local/demo deployment and engineering rules.
