import { createMemoryStore } from "./memory.js"

export function createGateway(options) {
  const catalog = options.catalog
  const config = options.config
  const fetcher = options.fetcher || fetch
  const memoryStore = options.memoryStore || createMemoryStore(config)
  const failures = new Map()
  let cursor = 0

  return async function handle(request) {
    const url = new URL(request.url)

    if (request.method === "OPTIONS") return response(null, { status: 204 })
    if (request.method === "GET" && (url.pathname === "/" || url.pathname === "/health")) {
      const memory = await memoryStore.load()
      return json({
        ok: true,
        service: "free-models-gateway",
        memory: {
          status: memory.status,
          characters: memory.characters,
          transmission_policy: config.memoryAllowTraining
            ? "training-allowed"
            : "only-models-marked-no-training",
        },
      })
    }
    if (request.method === "GET" && ["/models", "/v1/models"].includes(url.pathname)) {
      return json(await catalog.models({ refresh: url.searchParams.get("refresh") === "1" }))
    }
    if (request.method === "POST" && url.pathname === "/v1/chat/completions") {
      return chat(request)
    }

    return error(404, "Not found", "not_found")
  }

  async function chat(request) {
    const body = await request.json().catch(() => undefined)
    if (!body || typeof body !== "object" || Array.isArray(body)) {
      return error(400, "Request body must be valid JSON", "invalid_request_error")
    }
    if (!Array.isArray(body.messages) || !body.messages.length) {
      return error(400, "messages must be a non-empty array", "invalid_request_error")
    }

    const memory = await memoryStore.load()
    const requested = typeof body.model === "string" && body.model ? body.model : config.defaultModel
    const models = await candidates(requested)
    if (!models) {
      return error(
        400,
        `Unknown free model: ${requested}. Use GET /v1/models to list allowed models.`,
        "model_not_found",
      )
    }

    const attempts = []
    const limit = config.maxAttempts > 0 ? Math.min(config.maxAttempts, models.length) : models.length

    for (const model of models.slice(0, limit)) {
      const memoryForAttempt = protectMemory(body, memory, model)
      const result = await attempt(request, memoryForAttempt.body, model)
      if (result.response) {
        failures.delete(model.id)
        return success(result.response, {
          requested,
          model,
          attempts: attempts.length + 1,
          stream: body.stream === true,
          memory: memoryForAttempt,
        })
      }

      failures.set(model.id, Date.now())
      attempts.push({
        model: model.id,
        backend: model.backend,
        ...result.failure,
      })
    }

    return json(
      {
        error: {
          message: `All ${attempts.length} attempted free models failed`,
          type: "server_error",
          code: "all_models_failed",
          attempts,
        },
      },
      {
        status: 502,
        headers: memoryHeaders({
          status: memory.message ? "protected" : memory.status,
          characters: 0,
        }),
      },
    )
  }

  function protectMemory(body, memory, model) {
    if (!memory.message) {
      return { body, status: memory.status, characters: 0 }
    }

    const allowed = config.memoryAllowTraining || model.may_train_on_prompts === false
    if (!allowed) {
      return {
        body,
        status: "withheld-training-risk",
        characters: 0,
      }
    }

    return {
      body: {
        ...body,
        messages: [memory.message, ...body.messages],
      },
      status: "loaded",
      characters: memory.characters,
    }
  }

  async function candidates(requested) {
    const result = await catalog.models()
    const pool = result.data.filter(
      (model) => config.backends[model.backend] && model.routable !== false,
    )
    const healthy = pool.filter(
      (model) => Date.now() - (failures.get(model.id) || 0) >= config.cooldownMs,
    )
    const cooling = pool.filter((model) => !healthy.includes(model))
    const rotated = rotate(healthy).concat(rotate(cooling, false))

    if (["auto", "auto-route"].includes(requested)) return rotated
    const selected = await catalog.resolve(requested)
    if (!selected || !config.backends[selected.backend]) return undefined
    return [selected, ...rotated.filter((model) => model.id !== selected.id)]
  }

  function rotate(models, advance = true) {
    if (!models.length) return []
    const start = cursor % models.length
    if (advance) cursor = (cursor + 1) % Number.MAX_SAFE_INTEGER
    return [...models.slice(start), ...models.slice(0, start)]
  }

  async function attempt(request, body, model) {
    const backend = config.backends[model.backend]
    const controller = new AbortController()
    const abort = () => controller.abort(request.signal.reason)
    request.signal.addEventListener("abort", abort, { once: true })
    const timer = setTimeout(
      () => controller.abort(new Error("Attempt timed out")),
      config.attemptTimeoutMs,
    )
    const upstream = await fetcher(backend.chatUrl, {
      method: "POST",
      headers: {
        Accept: body.stream ? "text/event-stream" : "application/json",
        Authorization: `Bearer ${backend.token}`,
        "Content-Type": "application/json",
        ...backend.headers,
      },
      body: JSON.stringify({
        ...body,
        model: model.upstream_model,
      }),
      signal: controller.signal,
    }).catch((cause) => cause)
    clearTimeout(timer)
    request.signal.removeEventListener("abort", abort)

    if (upstream instanceof Error) {
      return { failure: { error: upstream.message || "Network request failed" } }
    }
    if (!upstream.ok) {
      return {
        failure: {
          status: upstream.status,
          error: await detail(upstream),
        },
      }
    }

    const type = upstream.headers.get("Content-Type") || ""
    if (body.stream === true && type.includes("text/event-stream")) {
      return { response: upstream }
    }

    const text = await upstream.text()
    const data = parse(text)
    if (!data || data.error || !Array.isArray(data.choices) || !data.choices.length) {
      return {
        failure: {
          status: upstream.status,
          error: data?.error?.message || "Upstream returned an invalid OpenAI response",
        },
      }
    }

    return {
      response: new Response(
        JSON.stringify({
          ...data,
          model: model.id,
        }),
        {
          status: upstream.status,
          headers: { "Content-Type": "application/json; charset=utf-8" },
        },
      ),
    }
  }

  function success(upstream, input) {
    return response(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type":
          upstream.headers.get("Content-Type") ||
          (input.stream ? "text/event-stream" : "application/json"),
        "X-Free-Models-Attempts": String(input.attempts),
        "X-Free-Models-Backend": input.model.backend,
        "X-Free-Models-Model": input.model.id,
        "X-Free-Models-Requested-Model": input.requested,
        ...memoryHeaders(input.memory),
        ...(upstream.headers.get("Cache-Control")
          ? { "Cache-Control": upstream.headers.get("Cache-Control") }
          : {}),
      },
    })
  }
}

function memoryHeaders(memory) {
  return {
    "X-Free-Models-Memory": memory.status,
    "X-Free-Models-Memory-Characters": String(memory.characters),
  }
}

async function detail(response) {
  const text = await response.text().catch(() => "")
  const data = parse(text)
  return data?.error?.message || data?.message || text.slice(0, 500) || `HTTP ${response.status}`
}

function parse(text) {
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

function error(status, message, code) {
  return json(
    {
      error: {
        message,
        type: status >= 500 ? "server_error" : "invalid_request_error",
        code,
      },
    },
    { status },
  )
}

function json(value, init = {}) {
  return response(JSON.stringify(value), {
    ...init,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...init.headers,
    },
  })
}

function response(body, init = {}) {
  const headers = new Headers(init.headers)
  headers.set("Access-Control-Allow-Origin", "*")
  headers.set("Access-Control-Allow-Headers", "Authorization, Content-Type")
  headers.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
  headers.set(
    "Access-Control-Expose-Headers",
    [
      "X-Free-Models-Attempts",
      "X-Free-Models-Backend",
      "X-Free-Models-Model",
      "X-Free-Models-Requested-Model",
      "X-Free-Models-Memory",
      "X-Free-Models-Memory-Characters",
    ].join(", "),
  )
  return new Response(body, { ...init, headers })
}
