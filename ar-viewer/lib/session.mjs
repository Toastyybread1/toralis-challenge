import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { gzipSync, gunzipSync } from "node:zlib";
import QRCode from "qrcode";
import { Redis } from "@upstash/redis";

export const TTL = 3600;
export const MAX_GLB = 2_000_000;
const hash = (value) =>
  createHash("sha256")
    .update(value || "")
    .digest("hex");
const equal = (a, b) =>
  timingSafeEqual(Buffer.from(hash(a)), Buffer.from(hash(b)));
const fail = (status, message) => {
  throw Object.assign(new Error(message), { status });
};
let redis;
const local = new Map();
function store() {
  if (process.env.BRANCHFORGE_LOCAL_DEMO === "1" && !process.env.VERCEL)
    return null;
  const url = process.env.UPSTASH_REDIS_REST_URL || process.env.KV_REST_API_URL;
  const token =
    process.env.UPSTASH_REDIS_REST_TOKEN || process.env.KV_REST_API_TOKEN;
  if (!url || !token)
    fail(
      503,
      "Sharing storage is not configured. Connect Upstash Redis to this Vercel project.",
    );
  return (redis ||= new Redis({ url, token, automaticDeserialization: false }));
}
async function read(id) {
  const db = store();
  const value = db ? await db.get(`bf:${id}`) : local.get(id);
  const session = typeof value === "string" ? JSON.parse(value) : value;
  if (!session || session.expiresAt <= Date.now()) {
    if (!db) local.delete(id);
    fail(
      410,
      "Sharing ended or this link expired. Scan a new QR code in Slicer.",
    );
  }
  return session;
}
async function insert(id, data) {
  const db = store();
  if (db) await db.set(`bf:${id}`, JSON.stringify(data), { ex: TTL, nx: true });
  else local.set(id, data);
}
// Conditional writes prevent a queued upload resurrecting a revoked session.
async function change(id, expectedVersion, data) {
  const db = store();
  if (!data) {
    if (db) await db.del(`bf:${id}`, `bf:${id}:model`);
    else local.delete(id);
    return;
  }
  if (db) {
    const { packed, ...metadata } = data;
    const ok = await db.eval(
      `
      local raw = redis.call('GET', KEYS[1])
      if not raw then return 0 end
      local old = cjson.decode(raw)
      if old.version ~= tonumber(ARGV[1]) then return 0 end
      local ttl = redis.call('PTTL', KEYS[1])
      if ttl <= 0 then return 0 end
      redis.call('SET', KEYS[1], ARGV[2], 'KEEPTTL')
      if ARGV[3] ~= '' then redis.call('SET', KEYS[2], ARGV[3], 'PX', ttl) end
      return 1`,
      [`bf:${id}`, `bf:${id}:model`],
      [expectedVersion, JSON.stringify(metadata), packed || ""],
    );
    if (!ok)
      fail(409, "Session changed or ended. Retry with the latest state.");
  } else {
    if (!local.has(id) || local.get(id).version !== expectedVersion)
      fail(409, "Session changed or ended.");
    if (data) local.set(id, data);
    else local.delete(id);
  }
}
export function validateModel(input) {
  if (
    !input ||
    typeof input.glb !== "string" ||
    input.glb.length > Math.ceil(MAX_GLB / 3) * 4
  )
    fail(413, "Model exceeds the 2 MB sharing limit. Simplify the surface.");
  const glb = Buffer.from(input.glb, "base64");
  if (
    glb.length < 20 ||
    glb.readUInt32LE(0) !== 0x46546c67 ||
    glb.readUInt32LE(4) !== 2 ||
    glb.readUInt32LE(8) !== glb.length ||
    glb.readUInt32LE(16) !== 0x4e4f534a
  )
    fail(400, "Expected a self-contained binary glTF 2.0 model.");
  const jsonLength = glb.readUInt32LE(12);
  if (jsonLength > glb.length - 20) fail(400, "Invalid model header.");
  let model;
  try {
    model = JSON.parse(glb.subarray(20, 20 + jsonLength).toString());
  } catch {
    fail(400, "Invalid model description.");
  }
  if (
    (model.buffers || []).some((b) => b.uri) ||
    (model.images || []).length ||
    model.extensionsRequired?.length
  )
    fail(
      400,
      "External files, images and required extensions are not permitted.",
    );
  const meta = input.meta;
  if (
    !meta ||
    !Array.isArray(meta.dimensionsMm) ||
    meta.dimensionsMm.length !== 3 ||
    !meta.dimensionsMm.every(
      (n) => Number.isFinite(n) && n >= 0 && n <= 10000,
    ) ||
    !Number.isInteger(meta.branchCount) ||
    meta.branchCount < 0 ||
    meta.branchCount > 500 ||
    !Number.isInteger(meta.meshCount) ||
    meta.meshCount < 0 ||
    meta.meshCount > 3000
  )
    fail(400, "Invalid scene measurements.");
  return {
    packed: gzipSync(glb).toString("base64"),
    meta: {
      dimensionsMm: meta.dimensionsMm,
      branchCount: meta.branchCount,
      meshCount: meta.meshCount,
      synthetic: meta.synthetic === true,
      labelsVisible: meta.labelsVisible === true,
      units: "metres",
      scale: 1,
    },
  };
}
export async function operation({
  method,
  id,
  action,
  token,
  body,
  now = Date.now(),
}) {
  if (!id && method === "POST") {
    const key = process.env.BRANCHFORGE_PUBLISH_KEY;
    if (!key || key.length < 32)
      fail(503, "A publisher key has not been configured on the server.");
    if (!equal(token, key)) fail(401, "Publisher key rejected.");
    const db = store();
    if (db) {
      const counter = `bf:create:${Math.floor(now / 3600000)}`;
      const count = await db.incr(counter);
      if (count === 1) await db.expire(counter, TTL);
      if (count > 20)
        fail(429, "Session creation limit reached. Try again next hour.");
    }
    const origin = process.env.BRANCHFORGE_PUBLIC_URL;
    if (
      !origin ||
      (!origin.startsWith("https://") &&
        !(process.env.BRANCHFORGE_LOCAL_DEMO === "1" && !process.env.VERCEL))
    )
      fail(503, "Configure the HTTPS viewer URL on the server.");
    const sessionId = randomBytes(16).toString("hex");
    const readToken = randomBytes(32).toString("base64url");
    const writeToken = randomBytes(32).toString("base64url");
    const url = `${new URL(origin).origin}/#${sessionId}.${readToken}`;
    const expiresAt = now + TTL * 1000;
    await insert(sessionId, {
      readHash: hash(readToken),
      writeHash: hash(writeToken),
      version: 0,
      expiresAt,
      updatedAt: now,
      publisherSeenAt: now,
      packed: "",
      meta: null,
    });
    return {
      id: sessionId,
      writeToken,
      url,
      expiresAt,
      qr: (
        await QRCode.toDataURL(url, {
          width: 256,
          margin: 4,
          errorCorrectionLevel: "M",
        })
      ).split(",")[1],
    };
  }
  if (!/^[a-f0-9]{32}$/.test(id || "")) fail(400, "Invalid sharing session.");
  const current = await read(id);
  const writing = ["PUT", "PATCH", "DELETE"].includes(method);
  if (!equal(hash(token), writing ? current.writeHash : current.readHash))
    fail(401, "This sharing key is not valid.");
  if (method === "DELETE") {
    await change(id, current.version, null);
    return { stopped: true };
  }
  if (method === "PATCH") {
    await change(id, current.version, { ...current, publisherSeenAt: now });
    return { alive: true };
  }
  if (method === "PUT") {
    if (current.version && now - current.updatedAt < 1000)
      fail(429, "Wait one second between updates.");
    const validated = validateModel(body);
    const next = {
      ...current,
      ...validated,
      version: current.version + 1,
      updatedAt: now,
      publisherSeenAt: now,
    };
    await change(id, current.version, next);
    return { version: next.version, expiresAt: next.expiresAt };
  }
  if (method !== "GET") fail(405, "Method not allowed.");
  if (action === "model") {
    const db = store();
    const packed = db ? await db.get(`bf:${id}:model`) : current.packed;
    if (!packed) fail(404, "Waiting for Slicer to send the first model.");
    return gunzipSync(Buffer.from(packed, "base64"), {
      maxOutputLength: MAX_GLB,
    });
  }
  return {
    version: current.version,
    updatedAt: current.updatedAt,
    publisherSeenAt: current.publisherSeenAt,
    expiresAt: current.expiresAt,
    ...current.meta,
  };
}
