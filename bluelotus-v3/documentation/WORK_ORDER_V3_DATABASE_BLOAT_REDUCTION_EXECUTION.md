# WORK ORDER — BlueLotus V3 Database Bloat Reduction Execution

**Addressed To:** Dr. Codex, Windows Platform Team  
**Date:** 2026-06-20  
**Authority:** CIO request  
**Source Doctrine:** `BLUELOTUS_V3_DATABASE_BLOAT_REDUCTION_THESIS.md`

---

## Objective

Implement the first production-safe version of the BlueLotus V3 database bloat reduction doctrine:

```text
Store once.
Hash always.
Reference often.
Summarize for humans.
Never delete.
Never overwrite truth.
Append corrections with lineage.
```

---

## Required Deliverables

1. Add an institutional object-store utility.
2. Add non-destructive MySQL schema for object-store and cycle-manifest tables.
3. Replace duplicated canonical embedded full payloads with compact references/summaries.
4. Replace duplicated deterministic pipeline full stage outputs with compact summaries.
5. Generate `dataset_public.json` for dashboard-safe compact publishing.
6. Add tests proving:
   - hashes are stable,
   - object references are compact,
   - safety invariants remain intact,
   - public dataset is materially smaller than internal dataset,
   - no destructive database behavior is introduced.
7. Regenerate `dataset_raw.json`, `dataset_public.json`, and reports.
8. Write a technical completion report.

---

## Non-Negotiable Safety Invariants

```text
execution_authority = CIO_ONLY_MANUAL
order_routing_enabled = false
system_orders_generated = 0
broker mutation = prohibited
automatic DCA = prohibited
automatic second tranche = prohibited
```

---

## Execution Doctrine

This work order is not a trading upgrade. It is a memory efficiency and institutional storage upgrade.

The database remains immutable. No old rows are deleted. No old truth is overwritten.

Where duplicate intelligence exists, the system stores compact object references:

```text
object_type
object_hash
payload_size_bytes
summary_status
source_key
```

Full objects remain available at their primary top-level source or in future MySQL object-store rows.

---

## Acceptance Criteria

1. `dataset_raw.json` still contains all required V3.1-V3.4 keys.
2. `canonical.str_state`, `canonical.pei_state`, and `canonical.risk_state` no longer store full duplicate payloads.
3. `deterministic_pipeline_v3_2.stages` and `stage_outputs` no longer duplicate full risk/target payloads.
4. `dataset_public.json` is generated and smaller than `dataset_raw.json`.
5. Reports regenerate successfully.
6. Focused and relevant regression tests pass.
7. GitHub publisher remains operational.

