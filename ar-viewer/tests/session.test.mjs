import test from "node:test";
import assert from "node:assert/strict";
import { operation, validateModel } from "../lib/session.mjs";
process.env.BRANCHFORGE_LOCAL_DEMO = "1";
process.env.BRANCHFORGE_PUBLIC_URL = "http://127.0.0.1:5173";
process.env.BRANCHFORGE_PUBLISH_KEY =
  "test-publisher-key-longer-than-32-characters";
function model(
  json = { asset: { version: "2.0" }, scenes: [{ nodes: [] }], scene: 0 },
) {
  let text = JSON.stringify(json);
  text += " ".repeat((4 - (text.length % 4)) % 4);
  const header = Buffer.alloc(20);
  [0x46546c67, 2, 20 + text.length, text.length, 0x4e4f534a].forEach((n, i) =>
    header.writeUInt32LE(n, i * 4),
  );
  return {
    glb: Buffer.concat([header, Buffer.from(text)]).toString("base64"),
    meta: {
      dimensionsMm: [20, 150, 30],
      branchCount: 4,
      meshCount: 1,
      synthetic: true,
    },
  };
}
const create = () =>
  operation({ method: "POST", token: process.env.BRANCHFORGE_PUBLISH_KEY });
test("publisher authentication is required", async () => {
  await assert.rejects(operation({ method: "POST", token: "wrong" }), {
    status: 401,
  });
});
test("QR carries only a read capability and lives in URL fragment", async () => {
  const s = await create();
  const url = new URL(s.url);
  assert.equal(url.search, "");
  assert.match(url.hash, /^#[a-f0-9]{32}\.[\w-]{43}$/);
  assert.ok(!s.url.includes(s.writeToken));
  assert.ok(s.qr.startsWith("iVBOR"));
  assert.equal(s.expiresAt > Date.now(), true);
});
test("model update, metadata poll, binary fetch, isolation and revocation", async () => {
  const s = await create(),
    readToken = s.url.split(".")[1];
  // Parse fragment; localhost dotted IP must not influence token extraction.
  const token = new URL(s.url).hash.slice(1).split(".")[1];
  await assert.rejects(
    operation({ method: "PUT", id: s.id, token, body: model() }),
    { status: 401 },
  );
  await operation({
    method: "PUT",
    id: s.id,
    token: s.writeToken,
    body: model(),
  });
  const state = await operation({ method: "GET", id: s.id, token });
  assert.equal(state.version, 1);
  assert.equal(state.branchCount, 4);
  assert.equal(state.readHash, undefined);
  assert.equal(state.packed, undefined);
  const glb = await operation({
    method: "GET",
    id: s.id,
    token,
    action: "model",
  });
  assert.equal(glb.readUInt32LE(0), 0x46546c67);
  const other = await create();
  await assert.rejects(operation({ method: "GET", id: other.id, token }), {
    status: 401,
  });
  await assert.rejects(operation({ method: "DELETE", id: s.id, token }), {
    status: 401,
  });
  await operation({ method: "DELETE", id: s.id, token: s.writeToken });
  await assert.rejects(operation({ method: "GET", id: s.id, token }), {
    status: 410,
  });
  await assert.rejects(
    operation({ method: "PUT", id: s.id, token: s.writeToken, body: model() }),
    { status: 410 },
  );
});
test("bounded payloads, embedded geometry only, no arbitrary metadata", () => {
  assert.throws(() => validateModel({ glb: "x".repeat(3_000_000) }), {
    status: 413,
  });
  assert.throws(
    () =>
      validateModel(
        model({ buffers: [{ uri: "https://evil.invalid/track" }] }),
      ),
    { status: 400 },
  );
  assert.throws(
    () =>
      validateModel({
        ...model(),
        meta: { ...model().meta, dimensionsMm: [NaN, 1, 2] },
      }),
    { status: 400 },
  );
  const value = model();
  value.meta.patientName = "DO NOT SHARE";
  assert.equal(validateModel(value).meta.patientName, undefined);
});
test("uploads are rate limited and expired sessions cannot be read", async () => {
  const s = await create();
  await operation({
    method: "PUT",
    id: s.id,
    token: s.writeToken,
    body: model(),
  });
  await assert.rejects(
    operation({ method: "PUT", id: s.id, token: s.writeToken, body: model() }),
    { status: 429 },
  );
  const expired = await operation({
    method: "POST",
    token: process.env.BRANCHFORGE_PUBLISH_KEY,
    now: Date.now() - 4_000_000,
  });
  const token = new URL(expired.url).hash.slice(1).split(".")[1];
  await assert.rejects(operation({ method: "GET", id: expired.id, token }), {
    status: 410,
  });
});
