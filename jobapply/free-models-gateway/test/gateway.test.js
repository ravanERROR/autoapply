import assert from "node:assert/strict"
import test from "node:test"
import { createGateway } from "../src/gateway.js"

const models = [
  {
    id: "kilo/first:free",
    backend: "kilo",
    upstream_model: "first:free",
    routable: true,
    may_train_on_prompts: false,
  },
  {
    id: "opencode/second-free",
    backend: "opencode",
    upstream_model: "second-free",
    routable: true,
    may_train_on_prompts: false,
  },
]

const config = {
  attemptTimeoutMs: 1000,
  cooldownMs: 60_000,
  defaultModel: "auto-route",
  maxAttempts: 0,
  memoryFile: "memory.md",
  memoryMaxChars: 100_000,
  memoryAllowTraining: false,
  backends: {
    kilo: { chatUrl: "https://kilo.test/chat", token: "anonymous", headers: {} },
    opencode: { chatUrl: "https://opencode.test/chat", token: "public", headers: {} },
  },
}

const catalog = {
  async models() {
    return { object: "list", data: [{ id: "auto-route", routable: false }, ...models] }
  },
  async resolve(id) {
    return models.find((model) => model.id === id || model.upstream_model === id)
  },
}

function request(body = {}) {
  return new Request("http://localhost/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "auto-route",
      messages: [{ role: "user", content: "Hello" }],
      ...body,
    }),
  })
}

test("injects Markdown memory before client messages", async () => {
  let received
  const gateway = createGateway({
    catalog,
    config,
    memoryStore: {
      async load() {
        return {
          status: "loaded",
          characters: 18,
          message: { role: "system", content: "Remember: name Pavan" },
        }
      },
    },
    async fetcher(_url, init) {
      received = JSON.parse(init.body)
      return Response.json({
        choices: [{ index: 0, message: { role: "assistant", content: "Hi" } }],
      })
    },
  })

  const response = await gateway(request())
  assert.equal(response.status, 200)
  assert.deepEqual(received.messages, [
    { role: "system", content: "Remember: name Pavan" },
    { role: "user", content: "Hello" },
  ])
  assert.equal(response.headers.get("X-Free-Models-Memory"), "loaded")
})

test("withholds memory from a model marked as training on prompts", async () => {
  let received
  const unsafeCatalog = {
    async models() {
      return {
        object: "list",
        data: [
          { id: "auto-route", routable: false },
          {
            id: "kilo/unsafe:free",
            backend: "kilo",
            upstream_model: "unsafe:free",
            routable: true,
            may_train_on_prompts: true,
          },
        ],
      }
    },
    async resolve() {
      return undefined
    },
  }
  const gateway = createGateway({
    catalog: unsafeCatalog,
    config,
    memoryStore: {
      async load() {
        return {
          status: "loaded",
          characters: 18,
          message: { role: "system", content: "Private memory text" },
        }
      },
    },
    async fetcher(_url, init) {
      received = JSON.parse(init.body)
      return Response.json({
        choices: [{ index: 0, message: { role: "assistant", content: "Hi" } }],
      })
    },
  })

  const response = await gateway(request())
  assert.deepEqual(received.messages, [{ role: "user", content: "Hello" }])
  assert.equal(response.headers.get("X-Free-Models-Memory"), "withheld-training-risk")
  assert.equal(response.headers.get("X-Free-Models-Memory-Characters"), "0")
})

test("sends memory to a training-eligible model when explicitly allowed", async () => {
  let received
  const unsafeCatalog = {
    async models() {
      return {
        object: "list",
        data: [
          { id: "auto-route", routable: false },
          {
            id: "kilo/unsafe:free",
            backend: "kilo",
            upstream_model: "unsafe:free",
            routable: true,
            may_train_on_prompts: true,
          },
        ],
      }
    },
    async resolve() {
      return undefined
    },
  }
  const gateway = createGateway({
    catalog: unsafeCatalog,
    config: { ...config, memoryAllowTraining: true },
    memoryStore: {
      async load() {
        return {
          status: "loaded",
          characters: 18,
          message: { role: "system", content: "Private memory text" },
        }
      },
    },
    async fetcher(_url, init) {
      received = JSON.parse(init.body)
      return Response.json({
        choices: [{ index: 0, message: { role: "assistant", content: "Hi" } }],
      })
    },
  })

  const response = await gateway(request())
  assert.deepEqual(received.messages, [
    { role: "system", content: "Private memory text" },
    { role: "user", content: "Hello" },
  ])
  assert.equal(response.headers.get("X-Free-Models-Memory"), "loaded")
  assert.equal(response.headers.get("X-Free-Models-Memory-Characters"), "18")
})

test("fails over to the next model after an upstream error", async () => {
  const attempted = []
  const gateway = createGateway({
    catalog,
    config,
    memoryStore: {
      async load() {
        return { status: "empty", characters: 0 }
      },
    },
    async fetcher(url) {
      attempted.push(url)
      if (attempted.length === 1) {
        return Response.json({ error: { message: "busy" } }, { status: 429 })
      }
      return Response.json({
        choices: [{ index: 0, message: { role: "assistant", content: "OK" } }],
      })
    },
  })

  const response = await gateway(request())
  assert.equal(response.status, 200)
  assert.equal(response.headers.get("X-Free-Models-Attempts"), "2")
  assert.equal(attempted.length, 2)
})

test("round-robins consecutive auto-route requests", async () => {
  const selected = []
  const gateway = createGateway({
    catalog,
    config,
    memoryStore: {
      async load() {
        return { status: "empty", characters: 0 }
      },
    },
    async fetcher(_url, init) {
      selected.push(JSON.parse(init.body).model)
      return Response.json({
        choices: [{ index: 0, message: { role: "assistant", content: "OK" } }],
      })
    },
  })

  await gateway(request())
  await gateway(request())
  assert.deepEqual(selected, ["first:free", "second-free"])
})
