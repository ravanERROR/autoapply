import assert from "node:assert/strict"
import test from "node:test"
import { loadKilo, loadOpenCode } from "../src/catalog.js"

test("keeps only zero-cost live OpenCode models", async () => {
  const responses = new Map([
    [
      "https://catalog.test",
      {
        opencode: {
          models: {
            free: { id: "free", cost: { input: 0, output: 0 } },
            paid: { id: "paid", cost: { input: 1, output: 1 } },
          },
        },
      },
    ],
    [
      "https://models.test",
      {
        data: [{ id: "free" }, { id: "paid" }],
      },
    ],
  ])
  const fetcher = async (url) => Response.json(responses.get(url))
  const result = await loadOpenCode(
    {
      catalogUrl: "https://catalog.test",
      modelsUrl: "https://models.test",
      headers: {},
    },
    fetcher,
  )
  assert.deepEqual(result.map((model) => model.id), ["opencode/free"])
})

test("keeps only free Kilo models", async () => {
  const fetcher = async () =>
    Response.json({
      data: [
        { id: "vendor/free:free", pricing: { prompt: "0", completion: "0" } },
        { id: "vendor/paid", pricing: { prompt: "1", completion: "1" } },
      ],
    })
  const result = await loadKilo({ modelsUrl: "https://models.test", headers: {} }, fetcher)
  assert.deepEqual(result.map((model) => model.id), ["kilo/vendor/free:free"])
})
