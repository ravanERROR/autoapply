#!/usr/bin/env node

import { createCatalog } from "../src/catalog.js"
import { createConfig } from "../src/config.js"
import { createGateway } from "../src/gateway.js"

const [command = "help", ...args] = process.argv.slice(2)

if (command === "serve" || command === "start") {
  await import("../src/server.js")
} else if (command === "models") {
  await models()
} else if (command === "chat") {
  await chat(args)
} else {
  help()
}

async function models() {
  const config = createConfig()
  const catalog = createCatalog({ config })
  const result = await catalog.models({ refresh: true })
  for (const model of result.data) {
    const note =
      model.id === "auto-route" ? "default" : model.routable === false ? "manual only" : ""
    console.log([model.id, model.name, note].filter(Boolean).join("\t"))
  }
}

async function chat(args) {
  const options = parseArgs(args)
  if (!options.prompt) {
    console.error("A prompt is required.")
    process.exitCode = 1
    return
  }

  const config = createConfig()
  const catalog = createCatalog({ config })
  const gateway = createGateway({ catalog, config })
  const messages = []
  if (options.system) messages.push({ role: "system", content: options.system })
  messages.push({ role: "user", content: options.prompt })

  const result = await gateway(
    new Request("http://localhost/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: options.model || config.defaultModel,
        messages,
        ...(options.maxTokens ? { max_tokens: options.maxTokens } : {}),
      }),
    }),
  )
  const data = await result.json()
  if (!result.ok) {
    console.error(JSON.stringify(data, null, 2))
    process.exitCode = 1
    return
  }

  if (options.json) {
    console.log(JSON.stringify(data, null, 2))
  } else {
    console.log(data.choices?.[0]?.message?.content || "")
  }
}

function parseArgs(args) {
  const result = { prompt: "" }
  const prompt = []
  for (let index = 0; index < args.length; index += 1) {
    const value = args[index]
    if (value === "--model") result.model = args[++index]
    else if (value === "--system") result.system = args[++index]
    else if (value === "--max-tokens") result.maxTokens = Number(args[++index])
    else if (value === "--json") result.json = true
    else prompt.push(value)
  }
  result.prompt = prompt.join(" ")
  return result
}

function help() {
  console.log(`free-models - keyless access to free OpenCode and Kilo models

Commands:
  free-models serve
  free-models models
  free-models chat [--model auto-route|ID] [--system TEXT] [--max-tokens N] [--json] PROMPT

API:
  GET  /health
  GET  /v1/models
  POST /v1/chat/completions

Edit memory.md to add permanent context used by every chat request.`)
}
