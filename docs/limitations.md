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
