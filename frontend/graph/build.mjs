import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import esbuild from "esbuild";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..", "..");
const assetDir = path.join(projectRoot, "src", "sediment", "assets");
const entryFile = path.join(__dirname, "src", "index.js");

await mkdir(assetDir, { recursive: true });

await esbuild.build({
  entryPoints: [entryFile],
  outfile: path.join(assetDir, "graph.bundle.js"),
  bundle: true,
  format: "iife",
  platform: "browser",
  target: ["es2020"],
  charset: "utf8",
  sourcemap: false,
  minify: true,
  logLevel: "info",
  loader: {
    ".css": "css",
  },
});
