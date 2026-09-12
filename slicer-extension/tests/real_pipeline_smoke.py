"""NEW Slicer --testing instance only: actual detector -> UI -> JSON, three cases."""
import json
from pathlib import Path
import time
import traceback
import faulthandler
import qt
import slicer

root = Path(__file__).resolve().parents[2]
out = root / "slicer-extension" / "artifacts" / "integration"
out.mkdir(parents=True, exist_ok=True)
report = {"cases": [], "success": False, "accuracy_validated": False}
thread_dump = (out / "real-thread-dump.log").open("w")
faulthandler.dump_traceback_later(120, repeat=True, file=thread_dump)


def pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(.01)


try:
    print("BEGIN real-pipeline smoke", flush=True)
    slicer.util.selectModule("BranchForge")
    widget = slicer.modules.branchforge.widgetRepresentation().self()
    widget.settings = qt.QSettings(str(out / "isolated-settings.ini"), qt.QSettings.IniFormat)
    from BranchForgeLib.integration import detector_paths
    from BranchForgeLib.contract import lps_to_ras
    executable, script = detector_paths(root)
    assert executable and script, "Run scripts/setup_environment.py first"
    widget.python_edit.setText(executable)
    widget.pipeline_edit.setText(script)
    window = slicer.util.mainWindow()
    window.showMaximized()
    assert len(widget.case_items) >= 3, "Provide at least three real studies"
    for i, name in enumerate(case[0] for case in widget.case_items[:3]):
        case = next(c for c in widget.case_items if c[0] == name)
        # First run deliberately differs from the folder name (regression).
        case_id = "custom_case_001" if i == 0 else name
        widget.case_edit.setText(case_id)
        print("Loading " + name, flush=True)
        widget.image_edit.setText(case[1])
        widget.mask_edit.setText(case[2])
        widget._load_study()
        assert widget.prediction is None
        start = time.monotonic()
        widget._run_detection()
        assert widget.process is not None
        ticks = 0
        while widget.process is not None and time.monotonic() - start < 150:
            slicer.app.processEvents()
            time.sleep(.01)
            ticks += 1
        assert widget.process is None, "Detector timed out"
        assert widget.prediction is not None, widget.run_log
        data = widget.prediction
        assert data["case_id"] == case_id and not widget.synthetic
        assert widget.table.rowCount == len(data["daughters"])
        for j, branch in enumerate(data["daughters"]):
            position = [0., 0., 0.]
            widget.scene.points.GetNthControlPointPositionWorld(j, position)
            assert all(abs(a - b) < 1e-5 for a, b in zip(position, lps_to_ras(branch["ostium_xyz_mm"])))
            widget.table.selectRow(j)
            assert widget.detail_title.text == branch["instance_id"]
        path = out / (name + ".json")
        widget.export_prediction_path(path)
        assert json.loads(path.read_text()) == data
        widget.scene.focus_aorta()
        pump(.8)
        widget.save_screenshot(out / (name + ".png"))
        report["cases"].append({"subject": name, "case_id": case_id,
                                "count": len(data["daughters"]), "seconds": time.monotonic() - start,
                                "responsive_event_ticks": ticks, "json_roundtrip": True,
                                "ras_markers_verified": True})
        print(json.dumps(report["cases"][-1]), flush=True)
    # Check that the dedicated workspace still restores standard Slicer afterwards.
    widget.close_workspace()
    widget.open_workspace()
    assert widget.workspace_open
    report["success"] = True
except Exception:
    report["traceback"] = traceback.format_exc()
    print(report["traceback"], flush=True)
finally:
    faulthandler.cancel_dump_traceback_later()
    (out / "real-pipeline-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)
    slicer.util.exit(0 if report["success"] else 1)
