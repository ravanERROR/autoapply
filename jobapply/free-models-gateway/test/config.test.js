import assert from "node:assert/strict"
import test from "node:test"
import { createConfig, defaultMemoryFile } from "../src/config.js"

test("uses the outer project memory file for a doubly nested gateway folder", () => {
  const result = defaultMemoryFile(
    "C:\\Users\\Pawan\\.config\\opencode\\free-models-gateway\\free-models-gateway",
  )

  assert.equal(
    result,
    "C:\\Users\\Pawan\\.config\\opencode\\free-models-gateway\\memory.md",
  )
})

test("allows memory on training-eligible models by default", () => {
  const config = createConfig({}, "/project/free-models-gateway")
  assert.equal(config.memoryAllowTraining, true)
})
