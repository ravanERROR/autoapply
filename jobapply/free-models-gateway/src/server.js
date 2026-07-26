import { createServer } from "node:http"
import { Readable } from "node:stream"
import { createCatalog } from "./catalog.js"
import { createConfig } from "./config.js"
import { createGateway } from "./gateway.js"
import { createMemoryStore } from "./memory.js"

const config = createConfig()
const catalog = createCatalog({ config })
const memoryStore = createMemoryStore(config)
const gateway = createGateway({ catalog, config, memoryStore })

const server = createServer(async (incoming, outgoing) => {
  try {
    const request = toRequest(incoming, config)
    const result = await gateway(request)
    outgoing.writeHead(result.status, Object.fromEntries(result.headers))

    if (!result.body) {
      outgoing.end()
      return
    }
    Readable.fromWeb(result.body).pipe(outgoing)
  } catch (cause) {
    outgoing.writeHead(500, {
      "Access-Control-Allow-Origin": "*",
      "Content-Type": "application/json; charset=utf-8",
    })
    outgoing.end(
      JSON.stringify({
        error: {
          message: cause instanceof Error ? cause.message : String(cause),
          type: "server_error",
          code: "gateway_error",
        },
      }),
    )
  }
})

server.listen(config.port, config.host, () => {
  console.log(`Free Models Gateway: http://${config.host}:${config.port}/v1`)
  console.log(`Default model: ${config.defaultModel}`)
  console.log(`Permanent memory: ${memoryStore.file}`)
  console.log(
    `Memory policy: ${
      config.memoryAllowTraining ? "training-eligible models allowed" : "no-training models only"
    }`,
  )
})

function toRequest(incoming, config) {
  const headers = new Headers()
  for (const [name, value] of Object.entries(incoming.headers)) {
    if (Array.isArray(value)) {
      for (const item of value) headers.append(name, item)
    } else if (value !== undefined) {
      headers.set(name, value)
    }
  }

  const method = incoming.method || "GET"
  const init = { method, headers }
  if (!["GET", "HEAD"].includes(method)) {
    init.body = Readable.toWeb(incoming)
    init.duplex = "half"
  }

  return new Request(
    `http://${incoming.headers.host || `${config.host}:${config.port}`}${incoming.url || "/"}`,
    init,
  )
}
