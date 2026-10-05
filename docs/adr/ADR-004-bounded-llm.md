# ADR-004 — Bounded LLM responsibilities

## Status
ACCEPTED

## Context
Language assistance is useful for ambiguous semantics and communication, while
business computations and authorization require deterministic backend authority.

## Decision
Allow only: genuinely ambiguous Excel semantic mapping suggestions; overall Decision
Summary wording from authorized facts; Decision Copilot/explanation wording over
deterministic results. Known approved mapping profiles map deterministically;
otherwise rules run first. Confident rules return deterministic mappings. Genuine
ambiguity may request LLM suggestion, followed by backend validation and human
approval where required. No new canonical field/schema may be invented.

Natural language → authorized intent/tool selection → deterministic tool computation
→ structured authorized facts → optional wording. Tool selection never replaces
computation or permission checks. LLM cannot own business facts, computation,
strategy/scenario selection or authorization. No provider call occurs at startup.

## Consequences
Provider integration is an optional bounded infrastructure gateway, not a domain
dependency. Outage cannot block core decision computation; ambiguous imports can
remain pending human review and wording can fall back to backend facts.

## Rejected/Deferred alternatives
REJECTED: generic business agents, LLM-selected recommendations, invented schema,
LLM permission bypass or mandatory provider availability.
DEFERRED: OpenRouter/Qwen client, confidence thresholds and approval UX until slices S4/S5.

## Revisit conditions
Explicit approved semantic/language scope change with evidence and a superseding
decision; better model quality alone does not grant business authority.

## Affected areas
Import/Mapping, Decision explanation, application authorization, infrastructure
gateway, FE approval flows, outage tests and demo wording.
