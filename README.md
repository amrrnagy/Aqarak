# Aqarak

AI assistant for Egyptian real estate: search listings, compare installment
plans, and estimate ROI in Arabic and English.

## Data and retrieval

The CSV and Markdown files under `data/raw/` are clearly marked fictional
sample data. They are intended for local development and retrieval evaluation,
not as real estate offers or verified market information.

Install the shared data and retrieval dependencies, then ingest the sample data:

```powershell
python -m pip install -r requirements.txt
python -m rag.ingest
python -m rag.evaluate
```

Chroma's bundled local embedding model is downloaded and cached the first time
the vector collection is initialized. Structured listing filters are applied
in SQLite before semantic ranking in Chroma. Missing listing values remain
unknown and are excluded when a corresponding exact filter is requested.

For the agent, copy `.env.example` to `.env` and set `LLM_API_KEY`. Select
`LLM_PROVIDER=gemini` or `LLM_PROVIDER=openai`, then set the matching model in
`LLM_MODEL`. Keep the key local and never commit `.env`.

The installment calculator accepts mortgage annual rates as decimal fractions
(for example, `0.08` means 8%). ROI calculations require rent, annual
appreciation, and horizon assumptions as inputs and return those assumptions
with the estimate.

Run the Phase 4 tests with:

```powershell
python -m pytest -q
```
