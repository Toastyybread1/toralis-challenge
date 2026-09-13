import { readFile, writeFile } from "node:fs/promises";
const base = "http://127.0.0.1:5173";
const out = new URL("../../slicer-extension/artifacts/ar-qa/", import.meta.url);
const create = await fetch(base + "/api/session", {
  method: "POST",
  headers: {
    Authorization: "Bearer local-only-branchforge-demo-publisher-key",
  },
});
const session = await create.json();
if (!create.ok) throw Error(session.error);
const glb = await readFile(new URL("synthetic.glb", out));
const meta = JSON.parse(await readFile(new URL("synthetic-meta.json", out)));
const uploaded = await fetch(`${base}/api/session?id=${session.id}`, {
  method: "PUT",
  headers: {
    Authorization: `Bearer ${session.writeToken}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ glb: glb.toString("base64"), meta }),
});
if (!uploaded.ok) throw Error(await uploaded.text());
await writeFile(new URL("browser-fixture.json", out), JSON.stringify(session));
console.log(session.url);
