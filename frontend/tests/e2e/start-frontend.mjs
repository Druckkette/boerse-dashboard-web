// Serve the same standalone artifact used by the frontend Docker image.
import { existsSync, symlinkSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
for (const [source, target] of [["public", ".next/standalone/public"], [".next/static", ".next/standalone/.next/static"]]) {
  if (!existsSync(target)) {
    try { symlinkSync(resolve(source), resolve(target), "dir"); }
    catch (error) { if (error.code !== "EEXIST") throw error; }
  }
}
await import(pathToFileURL(resolve(".next/standalone/server.js")).href);
