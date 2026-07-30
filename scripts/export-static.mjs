import { mkdir, writeFile } from "node:fs/promises";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("static-export", `${process.pid}-${Date.now()}`);
const { default: worker } = await import(workerUrl.href);

const response = await worker.fetch(
  new Request("http://localhost/", { headers: { accept: "text/html" } }),
  { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
  { waitUntil() {}, passThroughOnException() {} },
);

if (!response.ok) {
  throw new Error(`Static export failed with HTTP ${response.status}`);
}

const outputDirectory = new URL("../dist/client/", import.meta.url);
const html = await response.text();
await mkdir(outputDirectory, { recursive: true });
await Promise.all([
  writeFile(new URL("index.html", outputDirectory), html, "utf8"),
  writeFile(new URL("404.html", outputDirectory), html, "utf8"),
  writeFile(new URL(".nojekyll", outputDirectory), "", "utf8"),
]);
console.log("Static site exported to dist/client with GitHub Pages fallbacks");
