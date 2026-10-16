# ADR-023 — Approved Import missing-data policy

Status: ACCEPTED by the user's explicit policy update, 2026-10-17.

Classification: ACCEPTED DECISION; limited supersession of ADR-010's blanket
missing-never-zero rule. ADR-010 remains authoritative for all other facts and
unknown/invalid distinctions; ADR-008/013 and retained evidence stay unchanged.

## Decision and reason

Recipe process loss absent in source may use effective0% in computation. This is
an approved system policy, not an assertion that measured loss is zero. Retain raw
absence, SYSTEM_DEFAULT provenance and warning; explicit0 remains SOURCE_EXPLICIT.
Missing recipe end date means no assigned end. Missing Product/Ingredient SKU is
unknown/null, never a generated code. Invalid input is not missing and cannot use
these policies. Other required facts without an approved default block.

No zero defaults for stock, fees, prices, MOQ, units or other business facts. No
default becomes an Owner declaration/PROFILE_CONSTANT. Existing values/conflict,
Store/permission/review and confirmation guards remain. Explicitly selected
IMPORT_VALUE requirements still require the declaration; absence of that command
is not an absent source column and cannot silently discard a reviewed source rule.

## CURRENT FACT — implementation boundary

Import applies the fixed allowlist before typed row validation, records effective
values in preview/canonical data and raw absence/source_missing in retained Import
provenance. Existing canonical Recipe loss remains non-null effective numeric; no
DDL or consumer fallback is necessary. BOM/readiness consume effective0 under this
policy. Current retained JSON tables hold provenance/warnings; no historical
preview/spec/receipt is rewritten. Old provenance reads source_missing=false,
preserving its recorded meaning. Canonical dates/IDs/units/quantities remain strict.
New preview payload/summary pin import_mapping_policy/2; retained /1 reads and
commits its captured operations under current guards, not re-normalization.

[Canonical Import contract](../IMPORT_MAPPING_API_CONTRACT_VI.md#approved-missing-policy)
owns fields, warnings, FE guidance and source-policy examples. Source DTO/OpenAPI
own structure. This ADR records the accepted exception, not a task report.
