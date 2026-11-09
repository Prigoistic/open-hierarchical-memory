import { build } from "esbuild";
import { readFile, writeFile, copyFile, mkdir } from "node:fs/promises";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
const root = dirname(fileURLToPath(import.meta.url));
const result = await build({
  entryPoints: [resolve(root, "src/scene.mjs")],
  bundle: true,
  format: "iife",
  globalName: "SomnaVisuals",
  target: "es2022",
  minify: true,
  legalComments: "inline",
  write: false,
});
const bytes = result.outputFiles[0].contents,
  css = await readFile(resolve(root, "scene.css"));
for (const app of ["somna-live", "task-lab"]) {
  await writeFile(resolve(root, "..", app, "spatial.bundle.js"), bytes);
  await writeFile(resolve(root, "..", app, "spatial.css"), css);
  await copyFile(
    resolve(root, "embedded.css"),
    resolve(root, "..", app, "embedded.css"),
  );
  await copyFile(
    resolve(root, "panel-boot.js"),
    resolve(root, "..", app, "panel-boot.js"),
  );
}
await mkdir(resolve(root, "licenses"), { recursive: true });
await copyFile(
  resolve(root, "node_modules/three/LICENSE"),
  resolve(root, "licenses/THREE.txt"),
);
const manifest = {
  libraries: { three: "0.187.0", gsap: "3.15.1", esbuild: "0.28.2" },
  bundle_bytes: bytes.length,
  bundle_sha256: createHash("sha256").update(bytes).digest("hex"),
  css_sha256: createHash("sha256").update(css).digest("hex"),
  embedded_sha256: createHash("sha256")
    .update(await readFile(resolve(root, "embedded.css")))
    .digest("hex"),
  panel_boot_sha256: createHash("sha256")
    .update(await readFile(resolve(root, "panel-boot.js")))
    .digest("hex"),
};
await writeFile(
  resolve(root, "build-manifest.json"),
  JSON.stringify(manifest, null, 2) + "\n",
);
console.log(JSON.stringify(manifest));
