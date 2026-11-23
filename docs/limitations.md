# Limitations

- All listings, area guides, and developer names in `data/raw/` are fictional
  sample content, not offers, verified market facts, or investment advice.
- Missing listing price and delivery date values remain `null`. SQL filters
  that require those values do not match those records.
- Installment calculations model monthly payments only. They do not model
  developer-specific fees, payment milestones, insurance, or changing rates.
  Mortgage rates are decimal fractions (for example, `0.08` means 8%).
- ROI is a gross estimate: it annualizes caller-supplied current monthly rent
  and compounds caller-supplied appreciation annually. It excludes vacancy,
  operating costs, taxes, financing, and transaction fees.
- Saved searches are held in process memory and are lost when the process
  restarts.
- Chroma's local embedding model must be downloaded on first use. Retrieval
  quality has not been calibrated against real listings or human relevance
  judgments; the included ten-query evaluation is a sample-data smoke measure.
- API-key authentication and rate limits are intended for a local capstone
  deployment. Rate-limit state is process-local, and API keys are not
  per-user identities.
- Session memory and metrics are local-process/local-disk stores. They are not
  shared across multiple replicas and do not include an automated retention
  policy.
- LLM availability, model access, latency, and token usage depend on the
  configured provider and account. Temporary provider outages can fail a chat
  request; deterministic listing and calculation endpoints remain separate.

## Required limitations write-up template

Complete this section with evidence from the final deployment and review it
before presenting the project.

| Topic | What to document |
| --- | --- |
| Scope | Features, user groups, markets, and workflows not covered |
| Data quality | Data sources, sample-data status, missing fields, and update cadence |
| Retrieval | Evaluation dataset, measured results, and known relevance failures |
| Calculations | Assumptions, exclusions, rounding, and validation evidence |
| LLM behavior | Provider/model tested, language coverage, guardrails, and failure modes |
| Security and privacy | Authentication boundary, secrets handling, stored data, and retention |
| Operations | Deployment environment, availability, backup, monitoring, and recovery |
| Open risks | Known issues, owner, mitigation, and target date |

### Review record

- Reviewed by:
- Review date:
- Deployment/version:
- Evidence links:
