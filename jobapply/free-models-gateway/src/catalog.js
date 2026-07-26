export function createCatalog(options = {}) {
  const fetcher = options.fetcher || fetch
  const config = options.config
  let cached
  let expires = 0
  let pending

  async function models(input = {}) {
    if (!input.refresh && cached && Date.now() < expires) return cached
    if (!input.refresh && pending) return pending

    pending = load().finally(() => {
      pending = undefined
    })
    cached = await pending
    expires = Date.now() + config.cacheMs
    return cached
  }

  async function resolve(id) {
    const result = await models()
    const exact = result.data.find((model) => model.id === id)
    if (exact) return exact

    const raw = result.data.filter((model) => model.upstream_model === id)
    if (raw.length === 1) return raw[0]
    return undefined
  }

  async function load() {
    const settled = await Promise.allSettled([
      loadOpenCode(config.backends.opencode, fetcher),
      loadKilo(config.backends.kilo, fetcher),
    ])
    const data = settled.flatMap((result) => (result.status === "fulfilled" ? result.value : []))
    const errors = settled.flatMap((result, index) =>
      result.status === "rejected"
        ? [
            {
              backend: index === 0 ? "opencode" : "kilo",
              message: errorMessage(result.reason),
            },
          ]
        : [],
    )

    if (!data.length && errors.length) {
      throw new Error(errors.map((item) => `${item.backend}: ${item.message}`).join("; "))
    }

    const models = data.sort((a, b) => a.id.localeCompare(b.id))
    return {
      object: "list",
      data: [
        {
          id: "auto-route",
          object: "model",
          created: 0,
          owned_by: "free-models-gateway",
          name: "Auto Route",
          backend: "router",
          upstream_model: "auto-route",
          description: `Round-robin routing with automatic failover across ${models.filter((model) => model.routable).length} eligible free chat models.`,
          routable: false,
        },
        ...models,
      ],
      ...(errors.length ? { warnings: errors } : {}),
    }
  }

  return { models, resolve }
}

export async function loadOpenCode(config, fetcher = fetch) {
  const [catalog, available] = await Promise.all([
    getJson(config.catalogUrl, config.headers, fetcher),
    getJson(config.modelsUrl, config.headers, fetcher),
  ])
  const provider = catalog?.opencode
  const live = new Set(array(available?.data).map((model) => model?.id).filter(Boolean))
  const models = Object.values(provider?.models || {}).filter((model) => {
    if (!live.has(model?.id)) return false
    if (model?.status === "deprecated") return false
    return zero(model?.cost?.input) && zero(model?.cost?.output)
  })

  if (!models.length) {
    return array(available?.data)
      .filter((model) => model?.id === "big-pickle" || model?.id?.endsWith("-free"))
      .map((model) => normalize("opencode", { ...model, mayTrainOnYourPrompts: true }))
  }

  return models.map((model) =>
    normalize("opencode", {
      ...model,
      created: dateToUnix(model.release_date),
      owned_by: "opencode",
      context_length: model.limit?.context,
      mayTrainOnYourPrompts: true,
    }),
  )
}

export async function loadKilo(config, fetcher = fetch) {
  const result = await getJson(config.modelsUrl, config.headers, fetcher)
  return array(result?.data)
    .filter(isKiloFree)
    .map((model) => normalize("kilo", model))
}

function normalize(backend, model) {
  return {
    id: `${backend}/${model.id}`,
    object: "model",
    created: Number(model.created) || 0,
    owned_by: model.owned_by || backend,
    name: model.name || model.id,
    backend,
    upstream_model: model.id,
    ...(model.description ? { description: model.description } : {}),
    ...(Number(model.context_length) > 0 ? { context_window: Number(model.context_length) } : {}),
    ...(typeof model.mayTrainOnYourPrompts === "boolean"
      ? { may_train_on_prompts: model.mayTrainOnYourPrompts }
      : {}),
    routable: routable(model),
  }
}

function routable(model) {
  const output = model.architecture?.output_modalities || model.modalities?.output || []
  if (output.length && !output.includes("text")) return false
  return !/(content[-_ ]?safety|embedding|rerank|image[-_ ]?generation)/i.test(
    `${model.id || ""} ${model.name || ""}`,
  )
}

function isKiloFree(model) {
  if (!model?.id) return false
  if (model.isFree === true) return true
  if (model.id === "kilo-auto/free" || model.id.endsWith(":free")) return freePricing(model.pricing)
  return false
}

function freePricing(pricing) {
  if (!pricing) return true
  return ["prompt", "completion", "request", "image", "web_search", "internal_reasoning"].every(
    (field) => pricing[field] === undefined || zero(pricing[field]),
  )
}

async function getJson(url, headers, fetcher) {
  const response = await fetcher(url, {
    headers: {
      Accept: "application/json",
      ...headers,
    },
    signal: AbortSignal.timeout(15_000),
  })
  if (!response.ok) throw new Error(`${url} returned HTTP ${response.status}`)
  return response.json()
}

function array(value) {
  return Array.isArray(value) ? value : []
}

function zero(value) {
  return value !== undefined && value !== null && Number(value) === 0
}

function dateToUnix(value) {
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? Math.floor(parsed / 1000) : 0
}

function errorMessage(error) {
  return error instanceof Error ? error.message : String(error)
}
