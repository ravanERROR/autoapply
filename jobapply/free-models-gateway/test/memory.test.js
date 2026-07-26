import assert from "node:assert/strict"
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import test from "node:test"
import { createMemoryStore } from "../src/memory.js"

test("loads Markdown memory on every request", async () => {
  const directory = await mkdtemp(join(tmpdir(), "free-models-memory-"))
  const file = join(directory, "memory.md")
  const store = createMemoryStore({ memoryFile: file, memoryMaxChars: 1000 })

  try {
    await writeFile(file, "# Memory\n\n- Name: Pavan\n")
    const first = await store.load()
    assert.equal(first.status, "loaded")
    assert.match(first.message.content, /Name: Pavan/)

    await writeFile(file, "# Memory\n\n- Preferred language: English\n")
    const second = await store.load()
    assert.match(second.message.content, /Preferred language: English/)
    assert.doesNotMatch(second.message.content, /Name: Pavan/)
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("missing memory file does not block requests", async () => {
  const directory = await mkdtemp(join(tmpdir(), "free-models-missing-"))
  const originalCwd = process.cwd()

  try {
    process.chdir(directory)
    const store = createMemoryStore({
      memoryFile: join(directory, "memory.md"),
      memoryMaxChars: 1000,
    })
    const result = await store.load()
    assert.equal(result.status, "missing")
    assert.equal(result.message, undefined)
  } finally {
    process.chdir(originalCwd)
    await rm(directory, { recursive: true, force: true })
  }
})

test("truncates oversized memory", async () => {
  const directory = await mkdtemp(join(tmpdir(), "free-models-memory-"))
  const file = join(directory, "memory.md")
  const store = createMemoryStore({ memoryFile: file, memoryMaxChars: 10 })

  try {
    await writeFile(file, "1234567890EXTRA")
    const result = await store.load()
    assert.equal(result.status, "truncated")
    assert.equal(result.characters, 10)
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test("copies packaged memory to an outer project memory path", async () => {
  const directory = await mkdtemp(join(tmpdir(), "free-models-project-"))
  const packageDirectory = join(directory, "free-models-gateway")
  const target = join(directory, "memory.md")
  const originalCwd = process.cwd()

  try {
    await mkdir(packageDirectory)
    await writeFile(join(packageDirectory, "memory.md"), "# Migrated memory\n")
    process.chdir(packageDirectory)

    const store = createMemoryStore({ memoryFile: target, memoryMaxChars: 1000 })
    const result = await store.load()
    assert.equal(result.status, "loaded")
    assert.match(result.message.content, /Migrated memory/)
    assert.equal(await readFile(target, "utf8"), "# Migrated memory\n")
  } finally {
    process.chdir(originalCwd)
    await rm(directory, { recursive: true, force: true })
  }
})
