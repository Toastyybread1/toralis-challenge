// Run once from ar-viewer after `vercel link`. Secrets go via stdin, never arguments/logs.
import { randomBytes } from "node:crypto";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
const root = new URL("../", import.meta.url);
const project = JSON.parse(
  await readFile(new URL(".vercel/project.json", root)),
);
if (project.projectName !== "branchforge-ar")
  throw Error(
    "Refusing to configure a different project. Link branchforge-ar first.",
  );
const directory = new URL("../slicer-extension/artifacts/ar/", root);
await mkdir(directory, { recursive: true });
const keyFile = new URL("publisher-key.txt", directory);
let key;
try {
  key = (await readFile(keyFile, "utf8")).trim();
} catch (error) {
  if (error.code !== "ENOENT") throw error;
  key = randomBytes(32).toString("base64url");
  await writeFile(keyFile, key, { mode: 0o600, flag: "wx" });
}
if (!/^[\w-]{43}$/.test(key))
  throw Error("Unexpected existing key format. Not overwriting it.");
const host = JSON.parse(
  await readFile(new URL("../slicer-extension/ar-host.json", root)),
);
async function configure(name, value, sensitive) {
  await new Promise((resolve, reject) => {
    const args = [
      "--yes",
      "vercel@59.16.0",
      "env",
      "add",
      name,
      "production",
      "--yes",
      "--force",
      sensitive ? "--sensitive" : "--no-sensitive",
      "--scope",
      "sulaimanqazis-projects",
    ];
    const child = spawn(
      process.platform === "win32" ? "npx.cmd" : "npx",
      args,
      {
        cwd: fileURLToPath(root),
        shell: process.platform === "win32",
        windowsHide: true,
        stdio: ["pipe", "pipe", "pipe"],
      },
    );
    // Deliberately suppress CLI output: credentials must never surface in logs.
    child.stdout.resume();
    child.stderr.resume();
    child.on("error", reject);
    child.on("close", (code) =>
      code === 0
        ? resolve()
        : reject(Error(`Could not configure ${name}; CLI exit ${code}`)),
    );
    child.stdin.end(value);
  });
  console.log(`Configured ${name} (value hidden).`);
}
await configure("BRANCHFORGE_PUBLISH_KEY", key, true);
await configure("BRANCHFORGE_PUBLIC_URL", host.url, false);
console.log(
  "Publisher key saved in ignored Slicer artifacts folder; restart Slicer to load it. Redeploy the website to apply environment changes.",
);
