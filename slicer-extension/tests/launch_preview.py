"""Open the finished workspace and save a startup check. Leaves the app open."""
import json
from pathlib import Path
import runpy
import traceback
import qt
import slicer

root = Path(__file__).resolve().parents[1]
runpy.run_path(str(root / "scripts" / "launch.py"))


def capture_startup():
    report = {}
    try:
        widget = slicer.modules.branchforge.widgetRepresentation().self()
        assert widget.workspace_open
        assert widget.loaded_case == "subject001"
        assert widget.scene.ct is not None and widget.scene.aorta is not None
        assert widget.prediction is None and widget.run_button.enabled
        assert widget.controls_tabs.count == 3
        window = slicer.util.mainWindow()
        screen = qt.QApplication.desktop().availableGeometry(window)
        assert window.minimumSizeHint.width() <= screen.width(), (window.minimumSizeHint.width(), screen.width())
        widget.save_screenshot(root / "artifacts" / "qa" / "branchforge-ready.png")
        widget.status.setText("Study loaded. Run detection or import your team's JSON.")
        report = {"success": True, "case": widget.loaded_case, "workspace_open": widget.workspace_open, "prediction": None}
    except Exception:
        report = {"success": False, "traceback": traceback.format_exc()}
    (root / "artifacts" / "qa" / "launch-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)


qt.QTimer.singleShot(4500, capture_startup)
