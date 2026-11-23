# Aqarak

A modular Egyptian real-estate assistant for property search, deterministic
installment-plan comparisons, ROI estimates, and operational analytics. The
backend is FastAPI; the multipage dashboard is Streamlit and communicates with
the backend over HTTP.

All listings, area guides, and developer names in `data/raw/` are clearly
marked fictional sample content. They are for local development and retrieval
evaluation, not real offers or verified market information.

## Local setup

Use Python 3.11 or newer. In PowerShell, from the repository root:

```powershell
if (-not (Test-Path .venv)) { python -m venv .venv }
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Generate a private API key locally, then add it to `.env` without removing the
LLM settings:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set `API_KEY` to the generated value. This is the app's local API/UI
authentication key, not your Groq key. Keep `.env` local and never commit it.

To use Groq, configure these separate LLM settings in `.env`:

```env
LLM_PROVIDER=groq
LLM_API_KEY=your_groq_api_key
LLM_MODEL=llama-3.3-70b-versatile
```

Replace the example model with a model ID currently available in your Groq
account. The Groq key is sent to Groq by the OpenAI-compatible client; it is
not the `API_KEY` used by the local app. Gemini and OpenAI can also be selected
with `LLM_PROVIDER=gemini` or `LLM_PROVIDER=openai`. The UI uses
`API_BASE_URL`, which defaults to `http://127.0.0.1:8000`.

The sample inventory and knowledge documents must be ingested before searches:

```powershell
.\.venv\Scripts\python.exe -m rag.ingest
.\.venv\Scripts\python.exe -m rag.evaluate
```

Chroma's local embedding model is downloaded on first use and cached locally.
Exact listing filters run in SQLite before semantic ranking. Missing source
values stay unknown and are never inferred.

## Run the application

Open two PowerShell terminals in the repository root. Start the API in the
first:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --reload
```

Start the Streamlit dashboard in the second:

```powershell
.\.venv\Scripts\python.exe -m streamlit run ui/app.py
```

Open the local Streamlit URL printed in the terminal (normally
`http://localhost:8501`). Use the navigation menu for:

- **Chat**: ask in English or Arabic; results use structured listing cards.
- **Compare Plans**: search, select two to four listings, and compare stored
  installment terms.
- **Analytics**: view request latency, cache hit rate, area counts, listing
  views, and LLM token usage.

All `/v1` endpoints require the `X-API-Key` header. The dashboard reads
`API_KEY` and `API_BASE_URL` from `.env`. `/health` is public. API docs are
available at `http://127.0.0.1:8000/docs`.

## Docker Compose

After creating `.env` and configuring `API_KEY` and the LLM provider, build
and initialize the persistent sample-data volume:

```powershell
docker compose run --rm api python -m rag.ingest
docker compose up --build
```

Open `http://localhost:8501` for the UI and `http://localhost:8000/docs` for
the API documentation. The compose stack stores SQLite and Chroma data in a
named volume.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

The tests use mocked providers and do not require a live LLM API key. Live
Groq/Gemini/OpenAI availability and usage depend on the configured provider
account.

The installment calculator accepts mortgage annual rates as decimal fractions
(for example, `0.08` means 8%). ROI calculations require rent, annual
appreciation, and horizon assumptions as inputs and return those assumptions
with the estimate. See [docs/limitations.md](docs/limitations.md) for known
limits and the required project review template.
