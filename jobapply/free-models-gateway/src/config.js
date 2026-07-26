import { existsSync } from "node:fs"
import path from "node:path"

const trim = (value) => value.replace(/\/+$/, "")

export function createConfig(env = process.env, cwd = process.cwd()) {
  const opencode = trim(env.FREE_MODELS_OPENCODE_URL || "https://opencode.ai/zen/v1")
  const kilo = trim(env.FREE_MODELS_KILO_URL || "https://api.kilo.ai/api/openrouter")

  return {
    attemptTimeoutMs: positive(env.FREE_MODELS_ATTEMPT_TIMEOUT_MS, 60_000),
    cacheMs: positive(env.FREE_MODELS_CACHE_MS, 5 * 60 * 1000),
    cooldownMs: positive(env.FREE_MODELS_COOLDOWN_MS, 60_000),
    defaultModel: env.FREE_MODELS_DEFAULT_MODEL || "auto-route",
    host: env.FREE_MODELS_HOST || "127.0.0.1",
    maxAttempts: nonnegative(env.FREE_MODELS_MAX_ATTEMPTS, 0),
    memoryAllowTraining: boolean(env.FREE_MODELS_MEMORY_ALLOW_TRAINING, true),
    memoryFile: env.FREE_MODELS_MEMORY_FILE || defaultMemoryFile(cwd),
    memoryMaxChars: positive(env.FREE_MODELS_MEMORY_MAX_CHARS, 100_000),
    port: positive(env.FREE_MODELS_PORT, 8787),
    backends: {
      opencode: {
        id: "opencode",
        modelsUrl: `${opencode}/models`,
        catalogUrl: env.FREE_MODELS_CATALOG_URL || "https://models.dev/api.json",
        chatUrl: `${opencode}/chat/completions`,
        token: "public",
        headers: {
          "User-Agent": "free-models-gateway/0.3",
        },
      },
      kilo: {
        id: "kilo",
        modelsUrl: `${kilo}/models`,
        chatUrl: `${kilo}/chat/completions`,
        token: "anonymous",
        headers: {
          "User-Agent": "free-models-gateway/0.3",
          "X-KiloCode-EditorName": "Free Models Gateway",
        },
      },
    },
  }
}

export function defaultMemoryFile(cwd = process.cwd()) {
  const paths = cwd.includes("\\") ? path.win32 : path
  const parent = paths.dirname(cwd)
  const insideGateway = paths.basename(cwd).toLowerCase() === "free-models-gateway"
  const nestedGateway = paths.basename(parent).toLowerCase() === "free-models-gateway"
  const chatbotSibling = existsSync(paths.join(parent, "free-models-chatbot"))

  return insideGateway && (nestedGateway || chatbotSibling)
    ? paths.join(parent, "memory.md")
    : paths.join(cwd, "memory.md")
}

function positive(value, fallback) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

function nonnegative(value, fallback) {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : fallback
}

function boolean(value, fallback) {
  if (value === undefined) return fallback
  return ["1", "true", "yes", "on"].includes(String(value).toLowerCase())
}
