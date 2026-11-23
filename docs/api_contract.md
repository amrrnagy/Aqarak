# API Contract

The API uses JSON. Versioned application endpoints are under `/v1`; the health
check is available at `/health`. The payload models below correspond to the
shared Pydantic contracts in `data/schemas.py`.

## Authentication and rate limiting

All `/v1` endpoints require the `X-API-Key` header. The expected key is read
from `API_KEY`; health checks do not require authentication. Requests are
limited per key using `RATE_LIMIT_MAX_REQUESTS` within
`RATE_LIMIT_WINDOW_SECONDS`. A `429` response includes a `Retry-After` header.

## `POST /v1/chat`

### Request

`ChatRequest`:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `session_id` | string | Yes | Conversation session identifier |
| `message` | string | Yes | User message in Arabic or English |
| `language` | `"ar"` \| `"en"` | Yes | Language for the assistant response |

Example:

```json
{
  "session_id": "session-123",
  "message": "Find apartments in New Cairo under 5000000 EGP",
  "language": "en"
}
```

### Response

`ChatResponse`:

| Field | Type | Description |
| --- | --- | --- |
| `reply` | string | Assistant response |
| `tool_calls_used` | string[] | Names of tools used to produce the response |
| `sources` | string[] | Sources supporting the response |
| `listings` | `Listing[]` | Matching properties |
| `plans` | `PlanResult[]` | Calculated installment plans |
| `cached` | boolean | Whether the response was served from cache |
| `latency_ms` | number | Request latency in milliseconds |

Chat requests are not cached because they contain session-specific context.

## `GET /v1/listings`

Returns a JSON array of `Listing` objects. `query` is required. Optional query
parameters are `areas` (repeat once per area), `city`, `developer`, `price_min`,
`price_max`, `bedrooms`, `delivery_by` (ISO date), `property_type`, and `limit`
(1-10). Structured filters are applied before semantic ranking. Results are
cached for `CACHE_TTL_SECONDS`; this endpoint has no session context.

Example:

```text
GET /v1/listings?query=apartments&areas=New%20Cairo&price_max=5000000
```

## `POST /v1/compare-plans`

Calculates a deterministic installment plan for each selected listing and
returns a `PlanComparison`. The endpoint accepts 2-4 unique listing IDs and
returns an error when a listing is missing required price or installment data.
The current listing schema has no developer rate field, so this endpoint uses
the deterministic calculator's documented 0% default.

### Request

```json
{
  "listing_ids": ["NC-001", "NC-002"]
}
```

### Response

`PlanComparison` contains `side_by_side` options, each with an `option_id`,
label, source listing, and `PlanResult`. `lowest_total_cost` and
`lowest_monthly_payment` identify the winning option IDs.

## `GET /v1/metrics`

Returns aggregate request count and average latency, cache hits/misses and hit
rate, request counts by area, the ten most-viewed listings, recent latency and
cache series, and aggregate LLM prompt/completion token counts.

## Error responses

Errors use a stable JSON shape. Validation details are included when applicable:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request contains invalid or missing fields.",
    "details": [
      {
        "location": ["body", "language"],
        "message": "Input should be 'ar' or 'en'",
        "type": "literal_error"
      }
    ]
  }
}
```

### `Listing`

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Listing identifier |
| `title` | string | Listing title |
| `area` | string \| null | Neighborhood or development area |
| `city` | string \| null | City |
| `developer` | string \| null | Developer name |
| `price` | number \| null | Price in EGP |
| `area_sqm` | number \| null | Property area in square meters |
| `bedrooms` | integer \| null | Bedroom count |
| `bathrooms` | integer \| null | Bathroom count |
| `delivery_date` | date \| null | Delivery date in ISO 8601 format |
| `down_payment_pct` | number \| null | Down payment percentage |
| `installment_years` | number \| null | Installment duration in years |
| `description` | string \| null | Listing description |
| `property_type` | string \| null | Property type |

Unavailable listing data is represented as `null`; it is not inferred.

## `PlanResult`

| Field | Type | Description |
| --- | --- | --- |
| `price` | number | Property price in EGP |
| `down_payment` | number | Down payment in EGP |
| `financed_amount` | number | Amount financed in EGP |
| `monthly_payment` | number | Monthly payment in EGP |
| `total_paid` | number | Total amount paid in EGP |
| `total_interest` | number | Total interest in EGP |
| `annual_rate` | number | Annual rate as a percentage |
| `years` | number | Plan duration in years |
| `schedule_summary` | string | Human-readable schedule summary |

## `GET /health`

Returns HTTP `200` with a JSON object indicating service status, for example:

```json
{
  "status": "ok"
}
```

## Validation

Requests that fail Pydantic validation receive HTTP `422` with the shared
structured error shape. Authentication failures use HTTP `401`; missing API
configuration uses `503`.
