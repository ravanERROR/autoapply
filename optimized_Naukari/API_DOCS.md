# 🛸 Antigravity AI — API Documentation

> **Base URL (Render):** `https://ai-v008.onrender.com`  
> **UI:** Visit `/` in your browser to open the full chat workspace.

---

## 📋 Table of Contents

| # | Endpoint | Method | Purpose |
|---|---|---|---|
| 1 | [`/`](#1--get--serve-ui) | GET | Serve the chat UI |
| 2 | [`/health`](#2-get-health--health-check) | GET | Health check |
| 3 | [`/metrics`](#3-get-metrics--server-metrics) | GET | Server request metrics |
| 4 | [`/v1/providers`](#4-get-v1providers--provider-stats) | GET | AI provider statistics |
| 5 | [`/v1/sessions`](#5-post-v1sessions--create-session) | POST | Create a new chat session |
| 6 | [`/v1/sessions/{id}`](#6-delete-v1sessionssession_id--delete-session) | DELETE | Delete / clear a session |
| 7 | [`/v1/sessions/{id}/history`](#7-get-v1sessionssession_idhistory--get-history) | GET | Get conversation history |
| 8 | [`/v1/queries`](#8-post-v1queries--send-a-query-main-endpoint) | POST | Send a query (main AI endpoint) |

---

## 1. `GET /` — Serve UI

Serves the `index.html` chat workspace directly from the Flask server.  
This avoids all CORS issues — the UI and API run on the same origin.

**URL:** `https://ai-v008.onrender.com/`

**Response:** `text/html` — The full chat workspace page.

---

## 2. `GET /health` — Health Check

Quick ping to verify the server is alive.

**URL:** `https://ai-v008.onrender.com/health`

### Response
```json
{
  "status": "ok",
  "timestamp": "2026-06-17T07:19:36.617736+00:00"
}
```

### Example — curl
```bash
curl https://ai-v008.onrender.com/health
```

### Example — Python
```python
import requests
res = requests.get("https://ai-v008.onrender.com/health")
print(res.json())
```

---

## 3. `GET /metrics` — Server Metrics

Returns internal request counters and average latency statistics.

**URL:** `https://ai-v008.onrender.com/metrics`

### Response
```json
{
  "requests_total": 42,
  "requests_ok": 40,
  "requests_failed": 2,
  "cache_hits": 5,
  "provider_wins": {
    "OperaAria": 15,
    "Felo": 12,
    "WeWordle": 8
  },
  "avg_latency_ms": 3245.7,
  "_latency_sum": 136319.0
}
```

| Field | Type | Description |
|---|---|---|
| `requests_total` | int | Total requests handled since startup |
| `requests_ok` | int | Successful responses |
| `requests_failed` | int | Failed responses |
| `cache_hits` | int | Requests served from LRU cache |
| `provider_wins` | object | How many times each provider won the race |
| `avg_latency_ms` | float | Average response latency in milliseconds |

### Example — curl
```bash
curl https://ai-v008.onrender.com/metrics
```

---

## 4. `GET /v1/providers` — Provider Stats

Returns all registered AI providers sorted by their dynamic performance score (latency + success rate).

**URL:** `https://ai-v008.onrender.com/v1/providers`

### Response
```json
[
  {
    "name": "OperaAria",
    "avg_latency_ms": 1200.0,
    "success_rate": 100.0,
    "consecutive_failures": 0,
    "score": 0.813
  },
  {
    "name": "WeWordle",
    "avg_latency_ms": 1080.0,
    "success_rate": 95.0,
    "consecutive_failures": 0,
    "score": 0.775
  }
]
```

| Field | Type | Description |
|---|---|---|
| `name` | string | Provider name |
| `avg_latency_ms` | float | Rolling average latency (last 5 wins) |
| `success_rate` | float | % of successful calls (0–100) |
| `consecutive_failures` | int | Consecutive failures (penalizes score) |
| `score` | float | Composite routing score (higher = better) |

### Available Providers
| Provider | Notes |
|---|---|
| `OperaAria` | Fast, high reliability |
| `Felo` | Good quality |
| `Yqcloud` | Stable |
| `WeWordle` | Ultra-fast |
| `Groq` | High quality, fast |
| `OpenRouterFree` | Free tier routing |
| `Perplexity` | Search-enhanced |
| `DeepInfra` | Large model support |
| `PollinationsAI` | Vision + multimodal (non-streaming) |
| `BlackboxPro` | Best for vision/images |

### Example — curl
```bash
curl https://ai-v008.onrender.com/v1/providers
```

---

## 5. `POST /v1/sessions` — Create Session

Creates a new persistent conversation session and returns its UUID.  
Pass the `session_id` in subsequent `/v1/queries` calls to maintain context.

**URL:** `https://ai-v008.onrender.com/v1/sessions`

### Request
```
Content-Type: application/json
Body: {} (empty body is fine)
```

### Response
```json
{
  "session_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "message": "Session created."
}
```

### Example — curl
```bash
curl -X POST https://ai-v008.onrender.com/v1/sessions \
  -H "Content-Type: application/json"
```

### Example — Python
```python
import requests
res = requests.post("https://ai-v008.onrender.com/v1/sessions")
session_id = res.json()["session_id"]
print("Session ID:", session_id)
```

---

## 6. `DELETE /v1/sessions/{session_id}` — Delete Session

Clears all conversation history for a session (both in-memory and persisted file).

**URL:** `https://ai-v008.onrender.com/v1/sessions/{session_id}`

### Response
```json
{
  "session_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "message": "Session history cleared."
}
```

### Example — curl
```bash
curl -X DELETE https://ai-v008.onrender.com/v1/sessions/f47ac10b-58cc-4372-a567-0e02b2c3d479
```

### Example — Python
```python
import requests
requests.delete(f"https://ai-v008.onrender.com/v1/sessions/{session_id}")
```

---

## 7. `GET /v1/sessions/{session_id}/history` — Get History

Returns the full conversation history for a session.

**URL:** `https://ai-v008.onrender.com/v1/sessions/{session_id}/history`

### Response
```json
{
  "session_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "count": 4,
  "history": [
    { "role": "user", "content": "Hello!" },
    { "role": "assistant", "content": "Hi there! How can I help?" },
    { "role": "user", "content": "Write a poem." },
    { "role": "assistant", "content": "Roses are red..." }
  ]
}
```

### Example — curl
```bash
curl https://ai-v008.onrender.com/v1/sessions/f47ac10b-58cc-4372-a567-0e02b2c3d479/history
```

---

## 8. `POST /v1/queries` — Send a Query *(Main Endpoint)*

The core endpoint. Sends a prompt to the AI, races multiple providers in parallel, and returns the fastest valid response.

**URL:** `https://ai-v008.onrender.com/v1/queries`

### Request Headers
```
Content-Type: application/json
Authorization: Basic <base64(USERNAME:PASSWORD)>   ← optional
```

### Request Body (JSON)

| Field | Type | Default | Required | Description |
|---|---|---|---|---|
| `prompt` | string | — | ✅ Yes | The user's message / question. If `image_urls` is provided but no prompt, defaults to `"Describe these images"` |
| `system_prompt` | string | `""` | No | System-level instruction prepended to every request |
| `llm_model` | string | `"gpt-4o"` | No | Model to use (see models table below) |
| `provider` | string | `"auto"` | No | Provider or routing profile (see below) |
| `stream` | boolean | `false` | No | Enable Server-Sent Events streaming |
| `session_id` | string | `null` | No | Session UUID for multi-turn conversation. When set, full history is prepended; response is also stored |
| `use_cache` | boolean | `true` | No | Return cached response for identical prompts. Cache is disabled when `session_id` is set |
| `use_proxy` | boolean | `false` | No | Route through proxy (configured via `PROXY` env variable) |
| `image_url` | string | `null` | No | Single base64 image URL for vision queries. Merged into `image_urls` list |
| `image_urls` | array | `[]` | No | List of base64 image URLs (supports multiple images) |
| `search` | boolean | `true` | No | Enable internet search (provider-dependent) |
| `geo_location` | string | `"United States"` | No | Geo hint for search providers |
| `source` | string | `"chatgpt"` | No | Source tag (metadata only, echoed in response) |
| `parse` | boolean | `true` | No | Parse response markdown to AST (`markdown_json`). Echoed in the response `job` object |
| `callback_url` | string | `null` | No | Callback URL (echoed in the response `job` object, not actively called) |

### Supported Models (`llm_model`)
| Value | Model |
|---|---|
| `"default"` / `"auto"` / `""` | Fastest available (g4f default, recommended) |
| `"gpt-4o"` | OpenAI GPT-4o |
| `"gpt-4o-mini"` | OpenAI GPT-4o Mini |
| `"gpt-4"` | OpenAI GPT-4 |
| `"gemini-2.0-flash"` | Google Gemini 2.0 Flash |
| `"gemini-2.5-flash"` | Google Gemini 2.5 Flash |
| `"llama-3.3-70b"` | Meta LLaMA 3.3 70B |
| `"qwen-2.5-72b"` | Alibaba Qwen 2.5 72B |
| `"deepseek-v3"` | DeepSeek V3 |
| `"deepseek-r1"` | DeepSeek R1 (Reasoning) |

> **Note:** If the requested model is rejected by a provider (e.g. invalid/unsupported), the server automatically retries with `g4f.models.default` before falling back to the provider race.

### Routing Profiles (`provider`)
| Value | Behavior |
|---|---|
| `"auto"` / `"default"` | Dynamic race — top 5 providers compete, fastest wins |
| `"ultra-fast"` | Only providers with avg latency < 1500ms enter the race |
| `"max-quality"` | Prioritizes BlackboxPro, Groq, OpenRouterFree, Perplexity |
| `"OperaAria"` | Force specific provider |
| `"Groq"` | Force Groq |
| *(any provider name)* | Force that provider; falls back to race on failure |

> **Vision requests** (`image_urls` non-empty): Forces `BlackboxPro` → falls back to `Blackbox` → `PollinationsAI` → auto-routing.  
> **Streaming blacklist**: `PollinationsAI` is excluded from streaming (known compatibility issue).

---

### 8a. Standard (Non-Streaming) Response

```json
{
  "results": [
    {
      "content": {
        "prompt": "Write a short poem about coding.",
        "response_text": "Code flows like a silent stream...",
        "markdown_text": "Code flows like a silent stream...",
        "markdown_json": [ { "type": "paragraph", "children": [...] } ],
        "provider_used": "OperaAria",
        "latency_ms": 8592.53,
        "llm_model": "gpt-4o",
        "session_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        "parse_status_code": 12000
      },
      "created_at": "2026-06-17 07:19:36",
      "updated_at": "2026-06-17 07:19:36",
      "page": 1,
      "url": "https://chatgpt.com/?hints=search",
      "job_id": "8392847561029384756",
      "status_code": 200,
      "parser_type": "chatgpt"
    }
  ],
  "job": {
    "parse": true,
    "prompt": "Write a short poem about coding.",
    "search": true,
    "source": "chatgpt",
    "callback_url": null,
    "geo_location": "United States",
    "id": "8392847561029384756",
    "status": "done",
    "created_at": "2026-06-17 07:19:36",
    "updated_at": "2026-06-17 07:19:36"
  }
}
```

| `results[0].content` Field | Type | Description |
|---|---|---|
| `prompt` | string | The original prompt sent |
| `response_text` | string | The full AI response text |
| `markdown_text` | string | Same as `response_text` |
| `markdown_json` | array | Parsed markdown AST (paragraph, heading, code, etc.) |
| `provider_used` | string | Which provider generated the response |
| `latency_ms` | float | End-to-end latency in milliseconds |
| `llm_model` | string | Model used in the request |
| `session_id` | string \| null | Session ID (if provided) |
| `parse_status_code` | int | Always `12000` (success indicator) |

### 8b. Streaming Response (SSE)

When `"stream": true`, the response is a stream of Server-Sent Events:

```
data: {"delta": "Code "}
data: {"delta": "flows "}
data: {"delta": "like a "}
data: {"delta": "silent stream..."}
data: {"done": true, "full_text": "Code flows like a silent stream...", "provider_used": "Felo"}
```

| SSE Event Field | Description |
|---|---|
| `delta` | Incremental text chunk |
| `done: true` | Stream complete; includes full assembled text and provider metadata |
| `full_text` | The complete assembled response (only in `done` event) |
| `provider_used` | Which provider won (only in `done` event) |
| `error` | Present only on failure |

> **Note:** The streaming `done` event does **not** include `latency_ms` (unlike the non-streaming response).

---

### Example — Standard Request (Python)
```python
import requests

res = requests.post(
    "https://ai-v008.onrender.com/v1/queries",
    json={
        "prompt": "Explain async programming in 3 sentences.",
        "system_prompt": "You are a concise technical teacher.",
        "llm_model": "gemini-2.0-flash",
        "provider": "auto",
        "stream": False,
        "use_cache": True
    }
)
data = res.json()
content = data["results"][0]["content"]
print("Provider:", content["provider_used"])
print("Latency:", content["latency_ms"], "ms")
print("Answer:", content["response_text"])
```

### Example — Streaming Request (Python)
```python
import requests, json

res = requests.post(
    "https://ai-v008.onrender.com/v1/queries",
    json={
        "prompt": "Write a haiku about the ocean.",
        "llm_model": "auto",
        "stream": True,
        "use_proxy": False
    },
    stream=True
)

for line in res.iter_lines():
    if line:
        decoded = line.decode("utf-8")
        if decoded.startswith("data: "):
            chunk = json.loads(decoded[6:])
            if "delta" in chunk:
                print(chunk["delta"], end="", flush=True)
            elif chunk.get("done"):
                print(f"\n[Done — Provider: {chunk.get('provider_used')}]")
                print(f"[Full text length: {len(chunk.get('full_text', ''))} chars]")
```

### Example — With Session (Multi-turn Conversation)
```python
import requests

BASE = "https://ai-v008.onrender.com"

# 1. Create session
session_id = requests.post(f"{BASE}/v1/sessions").json()["session_id"]

# 2. First turn
res = requests.post(f"{BASE}/v1/queries", json={
    "prompt": "My name is Pavan. Remember that.",
    "session_id": session_id,
    "llm_model": "auto"
})
print(res.json()["results"][0]["content"]["response_text"])

# 3. Second turn — AI remembers context
res = requests.post(f"{BASE}/v1/queries", json={
    "prompt": "What is my name?",
    "session_id": session_id,
    "llm_model": "auto"
})
print(res.json()["results"][0]["content"]["response_text"])
# → "Your name is Pavan."

# 4. View history
history = requests.get(f"{BASE}/v1/sessions/{session_id}/history").json()
print(f"Total messages: {history['count']}")

# 5. Clear session
requests.delete(f"{BASE}/v1/sessions/{session_id}")
```

### Example — Vision / Image Query
```python
import requests, base64

with open("screenshot.png", "rb") as f:
    b64 = "data:image/png;base64," + base64.b64encode(f.read()).decode()

res = requests.post(
    "https://ai-v008.onrender.com/v1/queries",
    json={
        "prompt": "What is shown in this image?",
        "image_url": b64,
        "llm_model": "gpt-4o",
        "provider": "BlackboxPro"
    }
)
print(res.json()["results"][0]["content"]["response_text"])
```

### Example — Multiple Images
```python
import requests, base64

def encode_image(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()

res = requests.post(
    "https://ai-v008.onrender.com/v1/queries",
    json={
        "prompt": "Compare these two screenshots.",
        "image_urls": [encode_image("before.png"), encode_image("after.png")],
        "llm_model": "gpt-4o"
    }
)
print(res.json()["results"][0]["content"]["response_text"])
```

### Example — curl (Quick Test)
```bash
curl -X POST https://ai-v008.onrender.com/v1/queries \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is 2+2?",
    "llm_model": "auto",
    "provider": "auto"
  }'
```

---

## ⚙️ Environment Variables (`.env`)

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `MAX_HISTORY` | `40` | Max messages stored per session (older messages are trimmed) |
| `HISTORY_DIR` | `./chat_history` | Directory for persisted session JSON files. Set to `""` to disable file persistence |
| `PROVIDER_TIMEOUT` | `20` | Seconds to wait before the provider race times out |
| `PARALLEL_WORKERS` | `4` | Max concurrent provider race threads |
| `REQUEST_CACHE_SIZE` | `128` | LRU cache size for identical prompts (disabled when `session_id` is present) |
| `PROXY` | `""` | Comma-separated proxy list (e.g. `http://p1,http://p2`). Activated per-request via `use_proxy: true` |

---

## 🏗️ Architecture Overview

```
POST /v1/queries
       │
       ├─ system_prompt injected into messages[]
       ├─ session history loaded (if session_id provided)
       ├─ large input? → chunked pass (split + summarize per chunk)
       │
       ├─ [Vision? image_urls set]
       │     → BlackboxPro → Blackbox → PollinationsAI → auto-routing
       │
       └─ [Text] Staggered Parallel Race (top 5 providers)
              │
              ├── Thread 1: Provider A ──→ wins? → return response
              ├── Thread 2: Provider B (start +400ms)
              ├── Thread 3: Provider C (start +800ms)
              ├── Thread 4: Provider D (start +1200ms)
              └── Thread 5: Provider E (start +1600ms)
                    │
                    ├── All fail? → auto-routing fallback (g4f Client)
                    └── Still fail? → Failsafe stable providers (OperaAria, Felo, Yqcloud, WeWordle)
```

**Self-Optimizing Routing:** After every request, the winning provider's latency is recorded in a rolling window (last 5 results). Providers are sorted by a composite score `success_rate / (avg_latency + 0.1)`, penalized exponentially for consecutive failures. This means the system automatically prefers the fastest and most reliable providers over time.

**Large Input Handling:** If the estimated token count of the prompt exceeds the provider's context limit, the input is automatically split into chunks. Each chunk is summarized independently, and all partial results are combined before the final answer is generated.

**Continuation Logic:** If the response looks truncated (e.g. ends mid-sentence or has an unclosed code block), the server automatically sends a `"Continue exactly where you left off"` follow-up to the same provider (up to 4 continuations).

---

## 🧩 Session Persistence

Session histories are stored as JSON files in `HISTORY_DIR` (default: `./chat_history/`).

- File format: `./chat_history/<session_id>.json`
- Content: Array of `{"role": "user"|"assistant", "content": "..."}` objects
- Size limit: `MAX_HISTORY` messages per session (oldest trimmed automatically)
- Disable: Set `HISTORY_DIR=""` in `.env` (in-memory only, lost on restart)

---

*Generated for `app.py` — Antigravity AI Flask Server*
