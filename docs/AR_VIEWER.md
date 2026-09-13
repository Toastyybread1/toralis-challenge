# BranchForge readable results + phone AR

## Use it on this computer

1. Restart 3D Slicer using the existing BranchForge launcher so it loads the new code.
2. Load a study and run detection (or import the matching prediction).
3. In the right-hand **JSON** tab, read the plain-language report first. The unchanged, selectable JSON is underneath. Scroll the panel on smaller screens. Copy JSON and Export JSON still preserve the original LPS coordinates and numbers.
4. Open the right-hand **AR** tab. This computer's website address and publisher key are already configured. Connection settings are collapsible.
5. Confirm **Approved de-identified demo data**, then choose **Start sharing & show QR**.
6. Scan the QR with your phone camera and open the link. Tap **View in your space** on an AR-capable device. Good lighting and a textured floor/table help tracking.
7. Hide/show the aorta, origins, labels, arrows or radius rings in Slicer. New detections and branch selection also update the shared scene. Updates normally arrive within a few seconds, depending on mesh export, network and device speed.
8. **Stop sharing / revoke link** stops new uploads and revokes server access. Closing the workspace or clearing the scene also attempts revocation. If the network is unavailable or Slicer crashes, the existing link expires after one hour; the webpage indicates when publisher heartbeats stop.

Website: https://branchforge-ar.vercel.app

## iPhone versus Android: important limitation

| Feature | Compatible Android Chrome / WebXR | iPhone Safari / Quick Look |
|---|---|---|
| Live 3D webpage | Yes | Yes |
| Place model in the real world | WebXR AR | Apple Quick Look |
| Updates while still inside AR | Browser-based live updates | No: return to webpage and reopen AR |
| Scale | Fixed 100% anatomical scale | Fixed 100% anatomical scale |

AR is feature-detected, not promised for every phone. A device without AR support can still use the orbitable 3D viewer. Neither physical camera tracking nor in-AR live updates has been tested on an actual phone during development; do a rehearsal on the team's devices before presenting. The desktop/mobile-viewport browser test verifies rendering, not real-world AR tracking.

The distinction is documented in Google's [model-viewer AR examples](https://modelviewer.dev/examples/augmentedreality/index.html) and [scene graph examples](https://modelviewer.dev/examples/scenegraph/). Quick Look launches Apple's native viewer, so the webpage cannot continuously edit an already-open Quick Look scene. Building true live iPhone AR would require a different/native client, beyond this website implementation.

## What is shared, and what is not

- Visible BranchForge-owned aorta/preview surfaces, origin and seed spheres, direction arrows, radius rings, and generic B1/B2 labels. Transformed nodes are exported in world space.
- Layer visibility, segment visibility, aorta opacity and selected-branch emphasis. The selection pulse animation is intentionally not streamed frame by frame.
- No CT voxels, NIfTI files, raw prediction JSON, study names, patient identifiers, filesystem paths, or unrelated Slicer scene objects.
- Direction arrows and radius rings remain illustrative markers, **not reconstructed complete daughter-vessel walls**. The pipeline itself is unchanged.
- Only the anatomy is life-size. Slicer RAS millimetres become glTF Y-up metres using `(x, y, z) -> (x, z, -y) / 1000`, with a translation based on the aorta bounds. No arbitrary fit-to-human enlargement. AR tracking is not a calibrated measurement system and this is not for clinical use.

## Privacy and limits

Sharing is **off by default**, requires explicit confirmation, and should be used only with approved de-identified demonstration data. Removing a name does not guarantee a medical surface is anonymous. This prototype is not an approved clinical-data hosting service.

- Separate random read and write capabilities; the QR contains only the read token in the URL fragment. Tokens are sent to the API in Authorization headers, not query strings.
- A private publisher key is required to create a session. It never goes in the QR or website client bundle.
- One-hour absolute expiry, Redis TTL on both metadata and model, immediate server revocation, and compare-and-set uploads to prevent queued writes resurrecting a deleted session.
- Binary GLB is compressed for storage. Small metadata polls do not retrieve the model from Redis; the geometry is fetched only after a revision changes.
- 2 MB GLB limit; larger surfaces are simplified with topology preservation, or sharing fails with an explanation. New uploads at most once every two seconds; phone polling every 2.5 seconds, with error backoff. Publisher heartbeat every 15 seconds; offline warning after 45 seconds.
- Free Redis plan selected, with paid auto-upgrades disabled. Vercel/Redis quotas still apply; sessions are intended for short demos, not continuous all-day streaming.
- Anyone with the viewing link can potentially save geometry. Revocation cannot delete models already downloaded/cached by a phone or stop an already-open native Quick Look snapshot.

## Code map

- `slicer-extension/BranchForge/BranchForgeLib/report.py`: readable report without changing the prediction contract.
- `.../ar_export.py`: visible native scene -> self-contained GLB, with physical-unit conversion.
- `.../ar_share.py`: opt-in Qt controller; MRML on the UI thread, HTTP in background workers.
- `ar-viewer/src/`: mobile webpage using Google's open-source `@google/model-viewer` component.
- `ar-viewer/api/session.js` and `lib/session.mjs`: authenticated Vercel API and expiring Redis storage.
- `slicer-extension/ar-host.json`: public website address; safe to commit.
- `slicer-extension/artifacts/ar/publisher-key.txt`: **local secret**, ignored by Git, never deploy or commit. It is not copied to other teammates automatically. Transfer it only through a trusted private channel if they need publishing access, or configure a separate deployment/key.

The new Python modules are included in the extension CMake packaging list. Slicer already supplies Qt, VTK and NumPy; the extension does not need a new pip package for QR rendering. The server generates the QR PNG without using an external QR service. Existing Windows/macOS detector environment instructions remain applicable.

## Web development

From `ar-viewer`:

```text
npm ci
npm test
npm run build
npm run dev
```

The dev server binds only to `127.0.0.1:5173`, uses a local in-memory store and a clearly development-only publisher key (`local-only-branchforge-demo-publisher-key`). It does not connect to Redis. It is a test harness, **not** a phone-accessible deployment. Production refuses the in-memory mode on Vercel.

For a new Vercel account/project, link **only this ar-viewer directory**, provision free Upstash Redis through the Marketplace, and accept the provider terms yourself. Set `BRANCHFORGE_PUBLISH_KEY` (32+ random characters) and `BRANCHFORGE_PUBLIC_URL` to the canonical HTTPS origin. Redis credentials can use either `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` or Vercel Marketplace's `KV_REST_API_URL` / `KV_REST_API_TOKEN`. Do not use the read-only Redis token for the server.

`scripts/configure-publisher.mjs` is deliberately scoped to the current `branchforge-ar` project/team. It creates a local secret once and sends it to Vercel through stdin without logging it. Adapt its explicit project/team checks before using it for a different deployment. Redeploy after changing environment variables.

Never deploy from the repository root: it contains scan data. `.vercelignore` excludes local environment files, test/configuration scripts and Marketplace-installed agent skills. Do not disable deployment protection to debug preview URLs; the production website must be phone-accessible without a Vercel login.

## Verification

Executed locally:

- 40 existing detector tests and 6 existing extension contract tests passed.
- Web API tests: authentication, distinct capabilities, validation/size bounds, isolation, update limits, expiry, revocation and no resurrection.
- Fresh native Slicer test: readable/JSON output, unit conversion of a known 100 × 200 × 300 mm object, visible mesh export, QR generation, two published revisions and revocation.
- Desktop + 390 px browser: exported fictional GLB loads, four branches displayed, no horizontal overflow or browser errors.
- Production HTTPS/Redis smoke: create session, upload fictional GLB, byte-identical download, heartbeat preservation, read-token write rejection, revoke, and reject subsequent reads/uploads.

Test reports and screenshots are in ignored `slicer-extension/artifacts/ar-qa/`. Native tests must run in a **new Slicer instance** because they create/clear scenes and exit. `ar_smoke.py` uses the local dev server; `ar_layout_smoke.py` uses a tiny fictional cylinder for faster layout checks. `node tests/cloud-smoke.mjs` uploads only the fictional fixture and revokes its test session afterward. None of these tests uploads challenge scans.
