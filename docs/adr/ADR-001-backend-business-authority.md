# ADR-001 — Backend owns business authority

## Status
ACCEPTED

## Context
ShelfCash answers ingredient purchasing decisions, not just forecasts. Business
facts must be reproducible and auditable even when language providers are unavailable.

## Decision
Deterministic backend computation owns forecast results, BOM, ingredient demand,
inventory balances/FEFO, procurement quantities, candidate feasibility, strategy and
scenario selection, risks, business constraints, purchase cost, simulation and
recommendation. LLM is restricted to explicitly approved semantic/language tasks.
Every LEAN/BALANCED/PROTECTED candidate is evaluated by the deterministic simulator;
comparison selects a recommendation. The owner/manager makes the final business decision.

## Consequences
Domain logic is plain Python and independently testable. Core decisions operate with
no LLM provider. Facts supplied for wording are structured and authorized; generated
wording cannot become computation input or business truth.

## Rejected/Deferred alternatives
REJECTED: LLM-owned calculations, recommendation, feasibility or strategy selection.
DEFERRED: exact model, simulator and comparison implementations until their slices.

## Revisit conditions
New business scope requires explicit evidence and a proposed superseding ADR;
provider capability alone does not justify transferring authority.

## Affected areas
BE domain/application, ML/Data outputs, API facts, FE display, demo claims, testing,
future LLM integration and decision audit history.
