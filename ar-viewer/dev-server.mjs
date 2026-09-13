// Loopback-only test server. No cloud resources or patient data needed.
import http from "node:http";
import { createServer } from "vite";
import handler from "./api/session.js";
process.env.BRANCHFORGE_LOCAL_DEMO = "1";
process.env.BRANCHFORGE_PUBLISH_KEY ||=
  "local-only-branchforge-demo-publisher-key";
process.env.BRANCHFORGE_PUBLIC_URL = "http://127.0.0.1:5173";
const vite = await createServer({
  server: { middlewareMode: true },
  appType: "spa",
});
http
  .createServer(async (req, res) => {
    if (!req.url.startsWith("/api/session")) return vite.middlewares(req, res);
    res.status = (code) => {
      res.statusCode = code;
      return res;
    };
    res.json = (body) => {
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify(body));
    };
    res.send = (body) => res.end(body);
    let size = 0,
      chunks = [];
    for await (const chunk of req) {
      size += chunk.length;
      if (size > 2_800_000) return res.status(413).json({ error: "Too large" });
      chunks.push(chunk);
    }
    req.body = Buffer.concat(chunks).toString() || undefined;
    await handler(req, res);
  })
  .listen(5173, "127.0.0.1", () =>
    console.log("Local-only AR demo: http://127.0.0.1:5173"),
  );
