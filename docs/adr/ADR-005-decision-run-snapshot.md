# ADR-005 — DecisionRun is an auditable versioned snapshot

## Status
ACCEPTED

## Context
Inventory, supplier terms and constraints change. A past recommendation must remain
understandable without silently reinterpreting it through today's mutable state.

## Decision
DecisionRun is the main auditable decision aggregate. Preserve a self-contained,
schema-versioned input/output snapshot sufficient to explain input/model/recipe
versions, demand, candidates, simulation metrics, recommendation, warnings, risks
and business evidence. Decision packages have `package_schema_version`, starting at 1.
Store relevant used values, not only references to mutable current data.
Versioned JSON is acceptable for complex output; important forecast P25/P50/P75
remain explicitly modeled. No full ORM model is needed for scaffold bootstrap.

## Consequences
Completed historical meaning is stable. Package validation/version and provenance
need explicit contracts in S3. Retention must preserve evidence needed to understand
the decision; this does not promise replay with any future algorithm implementation.

## Rejected/Deferred alternatives
REJECTED: live joins that change historical meaning, unversioned arbitrary JSON,
or normalizing every nested package object without a real requirement.
DEFERRED: exact package schema and business migrations until the Decision MVP slice.

## Revisit conditions
Documented audit/query/storage requirements require a proposed schema/retention
evolution while preserving existing historical meaning.

## Affected areas
Decision domain, persistence, ML/Data provenance, API schemas, historical FE display,
golden tests, explanations and demo evidence.
