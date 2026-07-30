import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("GitHub Pages workflow publishes the gh branch with official Pages actions", async () => {
  const workflow = await read("../.github/workflows/deploy-pages.yml");
  assert.ok(workflow.includes('branches: ["gh"]'));
  assert.ok(workflow.includes("actions/configure-pages@v5"));
  assert.ok(workflow.includes("actions/upload-pages-artifact@v4"));
  assert.ok(workflow.includes("actions/deploy-pages@v4"));
  assert.ok(workflow.includes("pages: write"));
  assert.ok(workflow.includes("id-token: write"));
  assert.ok(workflow.includes("SECATLAS_BASE_PATH"));
  assert.ok(workflow.includes("run: pnpm test"));
  assert.ok(workflow.includes("path: dist/client"));
});

test("catalog requests support a repository base path without probing a server API", async () => {
  const app = await read("../app/catalog-app.tsx");
  const vite = await read("../vite.config.ts");
  assert.ok(app.includes("function catalogAssetUrl"));
  assert.ok(app.includes("STATIC_BASE_PATH"));
  assert.ok(app.includes("STATIC_READ_ONLY = true"));
  assert.equal(app.includes('fetch("/catalog'), false);
  assert.equal(app.includes('fetch("/api'), false);
  assert.ok(vite.includes("SECATLAS_BASE_PATH"));
});

test("static export includes GitHub Pages fallback files", async () => {
  const index = await read("../dist/client/index.html");
  const fallback = await read("../dist/client/404.html");
  await access(new URL("../dist/client/.nojekyll", import.meta.url));
  assert.equal(fallback, index);
});
