import { operation } from "../lib/session.mjs";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "private, no-store");
  res.setHeader("Vary", "Authorization");
  try {
    const url = new URL(req.url, "http://localhost");
    if (
      req.headers.origin &&
      process.env.BRANCHFORGE_PUBLIC_URL &&
      req.headers.origin !== new URL(process.env.BRANCHFORGE_PUBLIC_URL).origin
    )
      return res
        .status(403)
        .json({ error: "Cross-origin requests are not allowed." });
    if (Number(req.headers["content-length"] || 0) > 2_800_000)
      return res.status(413).json({ error: "Model upload is too large." });
    const result = await operation({
      method: req.method,
      id: url.searchParams.get("id"),
      action: url.searchParams.get("action"),
      token: (req.headers.authorization || "").replace(/^Bearer /, ""),
      body: typeof req.body === "string" ? JSON.parse(req.body) : req.body,
    });
    if (Buffer.isBuffer(result)) {
      res.setHeader("Content-Type", "model/gltf-binary");
      return res.status(200).send(result);
    }
    return res.status(200).json(result);
  } catch (error) {
    const status = error.status || (error instanceof SyntaxError ? 400 : 503);
    // Never return/log credentials, database URLs, or provider error objects.
    return res
      .status(status)
      .json({
        error: error.status
          ? error.message
          : "Sharing service unavailable. Try again shortly.",
      });
  }
}
