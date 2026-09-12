"""Open the workspace, walk through its main states and save screenshots. Leaves the app open.

Run in a NEW interactive Slicer instance, for example on Windows:

    & 'C:\\path\\to\\Slicer.exe' --no-splash --additional-module-paths "$PWD\\slicer-extension\\BranchForge" --python-script "$PWD\\slicer-extension\\tests\\visual_tour.py"

Screenshots and a small report land in slicer-extension/artifacts/qa/tour (ignored by Git).
This is a development aid for checking the interface, not a detector test.
"""
import json
import runpy
import time
import traceback
from pathlib import Path

import ctk
import qt
import slicer

root = Path(__file__).resolve().parents[1]
out = root / "artifacts" / "qa" / "tour"
out.mkdir(parents=True, exist_ok=True)
runpy.run_path(str(root / "scripts" / "launch.py"))


def pump(ms):
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        slicer.app.processEvents()
        time.sleep(0.01)


def shot(name):
    image = ctk.ctkWidgetsUtils.grabWidget(slicer.util.mainWindow())
    image.save(str(out / (name + ".png")))


def tour():
    report = {"steps": []}
    try:
        w = slicer.modules.branchforge.widgetRepresentation().self()
        deadline = time.monotonic() + 40
        while w.scene.ct is None and time.monotonic() < deadline:
            pump(200)
        pump(800)
        assert w.workspace_open, "workspace not open"
        assert w.scene.ct is not None, "study did not load"
        window = slicer.util.mainWindow()
        screen = qt.QApplication.desktop().availableGeometry(window)
        report["window"] = [window.width, window.height]
        report["min_hint"] = [window.minimumSizeHint.width(), window.minimumSizeHint.height()]
        report["screen"] = [screen.width(), screen.height()]
        report["fits"] = window.minimumSizeHint.width() <= screen.width()
        shot("01-ready-detect")
        report["steps"].append("ready")
        w.show_page(0)
        pump(400)
        shot("02-study")
        w.show_page(2)
        pump(400)
        shot("03-display")
        w.files_section.set_expanded(True)
        w.show_page(0)
        pump(500)
        shot("04-study-files")
        w.files_section.set_expanded(False)
        w.show_page(1)
        w.pipeline_section.set_expanded(True)
        pump(500)
        shot("05-detect-pipeline")
        w.pipeline_section.set_expanded(False)
        w._load_sample()
        pump(900)
        w.table.selectRow(2)
        pump(1400)
        shot("06-synthetic-branches")
        report["steps"].append("synthetic")
        w.tabs.setCurrentIndex(1)
        pump(500)
        shot("07-details")
        w.tabs.setCurrentIndex(2)
        pump(400)
        shot("08-json")
        w.tabs.setCurrentIndex(0)
        w.fly_to_branch()
        pump(1000)
        shot("09-fly")
        w.toggle_layout()
        pump(600)
        shot("10-3d-only")
        w.toggle_layout()
        pump(400)
        w.toast.show_message("Toast rendering check", "success")
        pump(450)
        shot("11-toast")
        w.show_page(1)
        pump(300)
        shot("12-detect-after")
        report["toast_visible"] = w.toast.visible
        report["headers"] = {k: v.offset_text for k, v in w.slice_headers.items()}
        report["pipeline_pill"] = w.pipeline_pill.text
        report["nav_index"] = w.nav.index
        report["success"] = True
    except Exception:
        report["success"] = False
        report["traceback"] = traceback.format_exc()
    (out / "tour-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


qt.QTimer.singleShot(6000, tour)
