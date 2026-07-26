import { constants } from "node:fs"
import { copyFile, mkdir, readFile } from "node:fs/promises"
import { dirname, resolve } from "node:path"

const INTRO = [
  "Persistent memory from a local Markdown file, manually maintained by the user.",
  "Use this context when it is relevant. If it conflicts with the user's current request or newer information, follow the current request or newer information.",
  "",
].join("\n")

export function createMemoryStore(config) {
  const file = resolve(config.memoryFile)
  const packagedFile = resolve("memory.md")

  async function load() {
    let content
    try {
      content = await readFile(file, "utf8")
    } catch (error) {
      if (error?.code === "ENOENT") {
        content = await migratePackagedMemory(file, packagedFile)
        if (content === undefined) {
          return { message: undefined, status: "missing", characters: 0 }
        }
      } else {
        return { message: undefined, status: "error", characters: 0 }
      }
    }

    const cleaned = content.trim()
    if (!cleaned) return { message: undefined, status: "empty", characters: 0 }

    const truncated = cleaned.length > config.memoryMaxChars
    const memory = truncated ? cleaned.slice(0, config.memoryMaxChars) : cleaned

    return {
      message: {
        role: "system",
        content: `${INTRO}${memory}`,
      },
      status: truncated ? "truncated" : "loaded",
      characters: memory.length,
    }
  }

  return { file, load }
}

async function migratePackagedMemory(file, packagedFile) {
  if (file === packagedFile) return undefined

  try {
    await mkdir(dirname(file), { recursive: true })
    await copyFile(packagedFile, file, constants.COPYFILE_EXCL)
  } catch (error) {
    if (error?.code !== "EEXIST") return undefined
  }

  return readFile(file, "utf8").catch(() => undefined)
}
