// Only fictional geometry from ar_smoke.py; never load scans or prediction files.
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
const out = new URL("../../slicer-extension/artifacts/ar-qa/", import.meta.url);
const key = (
  await readFile(
    new URL(
      "../../slicer-extension/artifacts/ar/publisher-key.txt",
      import.meta.url,
    ),
    "utf8",
  )
).trim();
const base = "https://branchforge-ar.vercel.app";
const report = { checks: [] };
let session;
async function call(method, token, id, body, extra = "") {
  const response = await fetch(
    base + "/api/session" + (id ? `?id=${id}` + extra : ""),
    {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(25000),
    },
  );
  const data =
    extra.includes("model") && response.ok
      ? Buffer.from(await response.arrayBuffer())
      : await response.json();
  if (!response.ok)
    throw Object.assign(Error(data.error || `HTTP ${response.status}`), {
      status: response.status,
    });
  return data;
}
try {
  assert.equal((await fetch(base)).status, 200);
  await assert.rejects(call("POST", "invalid"), { status: 401 });
  session = await call("POST", key);
  assert.ok(session.qr.startsWith("iVBOR"));
  const token = new URL(session.url).hash.slice(1).split(".")[1];
  const meta = JSON.parse(await readFile(new URL("synthetic-meta.json", out)));
  assert.equal(
    meta.synthetic,
    true,
    "Cloud test only permits synthetic anatomy",
  );
  const glb = await readFile(new URL("synthetic.glb", out));
  await call("PUT", session.writeToken, session.id, {
    glb: glb.toString("base64"),
    meta,
  });
  const state = await call("GET", token, session.id);
  assert.equal(state.version, 1);
  assert.equal(state.synthetic, true);
  const geometry = await call("GET", token, session.id, null, "&action=model");
  assert.deepEqual(geometry, glb);
  report.checks.push(
    "Public HTTPS site, authenticated session creation + QR, real Redis storage, identical binary GLB fetched",
  );
  await call("PATCH", session.writeToken, session.id);
  assert.deepEqual(
    await call("GET", token, session.id, null, "&action=model"),
    glb,
  );
  report.checks.push("Publisher heartbeat preserves geometry and revision");
  await assert.rejects(
    call("PUT", token, session.id, { glb: glb.toString("base64"), meta }),
    { status: 401 },
  );
  await call("DELETE", session.writeToken, session.id);
  await assert.rejects(call("GET", token, session.id), { status: 410 });
  await assert.rejects(
    call("PUT", session.writeToken, session.id, {
      glb: glb.toString("base64"),
      meta,
    }),
    { status: 410 },
  );
  report.checks.push(
    "Read token cannot upload; revoked sessions cannot be viewed or resurrected",
  );
  session = null;
  report.passed = true;
} catch (error) {
  report.passed = false;
  report.error = error.message;
} finally {
  if (session)
    await call("DELETE", session.writeToken, session.id).catch(() => {});
  await writeFile(
    new URL("cloud-report.json", out),
    JSON.stringify(report, null, 2),
  );
  console.log(JSON.stringify(report, null, 2));
  if (!report.passed) process.exitCode = 1;
}
