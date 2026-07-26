# Free Models Gateway

A standalone, dependency-free Node.js gateway for free, no-user-key models
exposed by OpenCode Zen and the Kilo AI Gateway.

It does not require the OpenCode CLI or Kilo CLI. It exposes an
OpenAI-compatible API, discovers currently free models, rotates across them,
and automatically switches to another model when an attempt fails.

## Requirements

- Node.js 20 or newer
- An internet connection

## Start

```cmd
npm start
```

The default API base URL is:

```text
http://127.0.0.1:8787/v1
```

## Permanent Markdown memory

Edit `memory.md` in the project directory and add the information you want every
model to remember. The file is read again for every request, so saved changes
take effect on the next message without restarting the gateway.

For this Windows layout:

```text
C:\Users\Pawan\.config\opencode\free-models-gateway\
├── memory.md
├── free-models-gateway\
└── free-models-chatbot\
```

the gateway automatically uses:

```text
C:\Users\Pawan\.config\opencode\free-models-gateway\memory.md
```

If an existing `memory.md` is found inside the nested gateway folder and the
outer project file does not exist yet, it is copied to the project directory
automatically.

By default, the gateway sends this memory to every selected free model so it can
use the stored facts and instructions. A successful response will contain:

```text
X-Free-Models-Memory: loaded
```

The anonymous free OpenCode and Kilo models may retain prompts or use them for
model improvement or training. Do not place secrets or sensitive personal data
in `memory.md`.

Example:

```md
# About me

- My name is Pavan.
- I prefer short answers.
- I use Windows and PowerShell.

# Current project

- I am building an OpenAI-compatible free-model gateway.
```

The gateway inserts this content as a system message before the messages sent
by the client. The original `messages` array remains unchanged in the client.

Do not store passwords, private keys, payment details, or other secrets in this
file. Its contents are sent to whichever OpenCode or Kilo model handles the
request.

Check whether memory loaded:

```cmd
curl http://127.0.0.1:8787/health
```

The response reports the file status and the active transmission policy.

To use another Markdown file in PowerShell:

```powershell
$env:FREE_MODELS_MEMORY_FILE = "C:\path\to\my-memory.md"
npm start
```

## OpenAI-compatible API

List free models:

```cmd
curl http://127.0.0.1:8787/v1/models
```

Chat:

```cmd
curl http://127.0.0.1:8787/v1/chat/completions -H "Content-Type: application/json" -d "{\"model\":\"auto-route\",\"messages\":[{\"role\":\"user\",\"content\":\"What is my name?\"}]}"
```

For apps that require an API key field, enter any non-empty value such as
`free`. The gateway ignores the client key.

## Routing

`auto-route` is the default model. It round-robins across eligible free text
models. When a model fails, times out, is rate-limited, rejects anonymous
access, or returns an invalid OpenAI response, the gateway tries the next model.

You can also request a particular model. It is attempted first and the
remaining free models become its fallback pool.

## Configuration

| Variable | Default |
| --- | --- |
| `FREE_MODELS_HOST` | `127.0.0.1` |
| `FREE_MODELS_PORT` | `8787` |
| `FREE_MODELS_DEFAULT_MODEL` | `auto-route` |
| `FREE_MODELS_ATTEMPT_TIMEOUT_MS` | `60000` |
| `FREE_MODELS_MAX_ATTEMPTS` | `0` (try all) |
| `FREE_MODELS_COOLDOWN_MS` | `60000` |
| `FREE_MODELS_CACHE_MS` | `300000` |
| `FREE_MODELS_MEMORY_FILE` | `memory.md` |
| `FREE_MODELS_MEMORY_MAX_CHARS` | `100000` |
| `FREE_MODELS_MEMORY_ALLOW_TRAINING` | `true` |

## Routing response headers

| Header | Meaning |
| --- | --- |
| `X-Free-Models-Requested-Model` | Model requested by the client |
| `X-Free-Models-Model` | Model that answered |
| `X-Free-Models-Backend` | `opencode` or `kilo` |
| `X-Free-Models-Attempts` | Number of models attempted |
| `X-Free-Models-Memory` | Memory loading status |
| `X-Free-Models-Memory-Characters` | Number of memory characters actually sent |
