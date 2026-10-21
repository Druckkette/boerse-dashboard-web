import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { getRootDirs } = require("@next/eslint-plugin-next/dist/utils/get-root-dirs.js");
test("Next lint rules still discover roots through the safe glob replacement", () => {
  const root = mkdtempSync(join(tmpdir(), "lint-root-"));
  try {
    mkdirSync(join(root, "a")); mkdirSync(join(root, "b"));
    writeFileSync(join(root, "file"), "ignored");
    const context = { cwd: root, settings: { next: { rootDir: `${root}/{a,b,file}` } } };
    // The consumer joins these paths with pages/app; absolute and cwd-relative
    // roots must therefore identify the same directories.
    assert.deepEqual(getRootDirs(context).map(path => resolve(path)).sort(), [join(root, "a"), join(root, "b")]);
    assert.deepEqual(getRootDirs({ cwd: root, settings: {} }), [root]);
  } finally { rmSync(root, { recursive: true }); }
});
