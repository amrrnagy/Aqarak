# API Contract

The API uses JSON. Versioned application endpoints are under `/v1`; the health
check is available at `/health`. The payload models below correspond to the
shared Pydantic contracts in `data/schemas.py`.

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

## `GET /v1/listings`

Returns a JSON array of `Listing` objects. Filters may be supplied as query
parameters; supported filters include price range, area, city, bedrooms,
delivery date, and property type.

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

Requests that fail Pydantic validation receive FastAPI's standard HTTP `422`
validation response.
