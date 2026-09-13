import "@google/model-viewer";
import "./style.css";

const $ = (id) => document.getElementById(id);
const viewer = $("anatomy");
const match = location.hash.match(/^#([a-f0-9]{32})\.([\w-]{43})$/);
// QR links can open in an existing tab; changing only a fragment does not reload JS.
window.addEventListener("hashchange", () => location.reload());
let revision = -1,
  objectUrl,
  stopped = false,
  failures = 0,
  inAR = false;
const ios =
  /iPad|iPhone|iPod/.test(navigator.userAgent) ||
  (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
if (ios)
  $("sync-note").textContent =
    "Your iPhone webpage stays in sync with Slicer. View in your space opens Apple Quick Look with the latest snapshot. To see a Slicer change in AR, close Quick Look, wait for the scene to update here, and open it again.";
const headers = match ? { Authorization: `Bearer ${match[2]}` } : {};
const endpoint = match ? `/api/session?id=${match[1]}` : "";

async function get(action = "") {
  const response = await fetch(endpoint + action, {
    headers,
    cache: "no-store",
    signal: AbortSignal.timeout(12000),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw Object.assign(
      new Error(body.error || `Sharing service returned ${response.status}.`),
      { status: response.status },
    );
  }
  return response;
}
function clearModel(message) {
  viewer.removeAttribute("src");
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = null;
  $("empty").hidden = false;
  $("empty").querySelector("h2").textContent = message;
  $("empty").querySelector("p").textContent =
    "The phone will show only the geometry currently shared from BranchForge.";
  $("reset").disabled = true;
}
async function loadModel() {
  const response = await get("&action=model");
  const nextUrl = URL.createObjectURL(await response.blob());
  const oldUrl = objectUrl;
  $("loading").hidden = false;
  try {
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(
        () => done(new Error("Model loading timed out.")),
        20000,
      );
      const done = (error) => {
        clearTimeout(timeout);
        viewer.removeEventListener("load", success);
        viewer.removeEventListener("error", errorHandler);
        error ? reject(error) : resolve();
      };
      const success = () => done();
      const errorHandler = () =>
        done(
          new Error(
            "This device could not render the model. Try a current Safari or Chrome browser.",
          ),
        );
      viewer.addEventListener("load", success);
      viewer.addEventListener("error", errorHandler);
      viewer.src = nextUrl;
    });
    objectUrl = nextUrl;
    if (oldUrl) URL.revokeObjectURL(oldUrl);
    $("empty").hidden = true;
    $("reset").disabled = false;
  } catch (error) {
    URL.revokeObjectURL(nextUrl);
    throw error;
  } finally {
    $("loading").hidden = true;
  }
}
async function poll() {
  if (!match || stopped) return;
  let delay = 2500;
  try {
    const state = await (await get()).json();
    if (state.version !== revision) {
      if (state.meshCount > 0) await loadModel();
      else
        clearModel(
          state.version
            ? "All model layers are hidden in Slicer."
            : "Connected. Waiting for the first model…",
        );
      revision = state.version;
      $("branches").textContent = state.branchCount ?? "—";
      $("dimensions").textContent = state.dimensionsMm
        ? state.dimensionsMm.map((n) => (n / 10).toFixed(1)).join(" × ") + " cm"
        : "—";
      $("revision").textContent = String(revision).padStart(3, "0");
    }
    failures = 0;
    const minutes = Math.max(
      0,
      Math.ceil((state.expiresAt - Date.now()) / 60000),
    );
    $("connection").textContent =
      Date.now() - state.publisherSeenAt > 45000
        ? "○ Slicer offline · last shared scene"
        : `● Synced · link expires in ${minutes}m`;
    $("notice").textContent = state.synthetic
      ? "SYNTHETIC EXAMPLE · Fictional anatomy and reference markers, not detector predictions."
      : "Research-only visualisation. Markers are estimates and require CT review.";
    if (state.meshCount > 0 && !viewer.canActivateAR)
      $("notice").textContent +=
        " AR is unavailable on this browser/device. You can still explore in 3D.";
  } catch (error) {
    if ([400, 401, 410].includes(error.status)) {
      stopped = true;
      clearModel("This sharing session has ended.");
      $("connection").textContent = "○ Disconnected";
      $("branches").textContent =
        $("dimensions").textContent =
        $("revision").textContent =
          "—";
      // Do not leave the old model visible in a live WebXR session after revocation.
      if (inAR && viewer.dismissAR) await viewer.dismissAR().catch(() => {});
    } else {
      failures++;
      delay = Math.min(30000, 2500 * 2 ** failures);
      $("connection").textContent = "○ Connection interrupted · retrying";
    }
    $("notice").textContent = error.message;
  }
  if (!stopped) setTimeout(poll, delay);
}
$("reset").addEventListener("click", () => {
  viewer.cameraOrbit = "25deg 75deg auto";
  viewer.cameraTarget = "auto auto auto";
  viewer.fieldOfView = "auto";
});
viewer.addEventListener("ar-status", (event) => {
  inAR = !["not-presenting", "failed"].includes(event.detail.status);
  if (event.detail.status === "failed")
    $("notice").textContent =
      "AR could not start. Check camera permission, use a well-lit space, and try again.";
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && match && !stopped)
    $("connection").textContent = "○ Checking latest Slicer scene…";
});
if (match) {
  $("connection").textContent = "○ Connecting to Slicer…";
  poll();
} else if (location.hash)
  $("notice").textContent =
    "This QR link is incomplete. Scan the code in Slicer again.";
