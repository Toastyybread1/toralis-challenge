"""Integration / visual check. Run in a NEW Slicer instance with --testing."""
import json
from pathlib import Path
import sys
import time
import traceback
import faulthandler

import qt
import slicer

root = Path(__file__).resolve().parents[1]
out = root / "artifacts" / "qa"
out.mkdir(parents=True, exist_ok=True)
class ProgressChecks(list):
    def append(self, message):
        super().append(message)
        print("CHECK: " + message, flush=True)


report = {"checks": ProgressChecks()}
thread_dump = (out / "ui-thread-dump.log").open("w")
faulthandler.dump_traceback_later(90, repeat=True, file=thread_dump)


def pump(ms):
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        slicer.app.processEvents()
        time.sleep(.01)


def await_process(widget, timeout=25):
    deadline = time.monotonic() + timeout
    ticks = 0
    while widget.process is not None and time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(.01)
        ticks += 1
    assert widget.process is None, "Pipeline did not complete in the test timeout"
    return ticks

try:
    print("BEGIN native UI smoke", flush=True)
    slicer.util.selectModule("BranchForge")
    widget = slicer.modules.branchforge.widgetRepresentation().self()
    # Isolate pipeline preferences even if this test is run without --testing.
    widget.settings = qt.QSettings(str(out / "test-preferences.ini"), qt.QSettings.IniFormat)
    window = slicer.util.mainWindow()
    window.showMaximized()
    pump(300)
    assert widget.workspace_open and widget.toast is not None and len(widget.shortcuts) == 10
    assert set(widget.slice_headers) == {"Red", "Yellow", "Green"}
    screen = qt.QApplication.desktop().availableGeometry(window)
    assert window.minimumSizeHint.width() <= screen.width(), (window.minimumSizeHint.width(), screen.width())
    report["checks"].append("Workspace opened with toast, shortcuts, slice headers; minimum width fits the screen")
    widget._load_sample()
    pump(200)
    assert widget.prediction["case_id"] == "synthetic_demo"
    assert widget.table.rowCount == 4 and widget.table_stack.currentIndex == 1
    assert not widget.run_button.enabled
    assert widget.sample_warning.visible
    assert widget.count_label.text in ("00", "01", "02", "03", "04")
    report["checks"].append("Synthetic scene, 4 branches, clearly labelled, detection disabled")
    from BranchForgeLib.contract import lps_to_ras
    point = [0., 0., 0.]
    widget.scene.points.GetNthControlPointPositionWorld(0, point)
    expected = lps_to_ras(widget.prediction["daughters"][0]["ostium_xyz_mm"])
    assert all(abs(a-b) < 1e-5 for a, b in zip(point, expected))
    report["checks"].append("LPS to RAS verified against actual MRML fiducial position")
    widget.export_prediction_path(out / "synthetic_export.json")
    assert json.loads((out / "synthetic_export.json").read_text()) == widget.prediction
    widget.table.selectRow(2)
    pump(150)
    assert widget.detail_title.text == "branch_003" and widget.details_stack.currentIndex == 1
    assert widget.scene.selected == 2 and widget.rose.vector is not None
    widget.step_branch(1)
    assert widget.table.currentRow() == 3
    widget.fly_to_branch()
    widget.copy_branch()
    assert json.loads(slicer.app.clipboard().text())["instance_id"] == "branch_004"
    pump(700)
    widget.save_screenshot(out / "branchforge-synthetic.png")
    report["checks"].append("JSON export preserved all coordinates; selection, details, stepping, fly-to and screenshot")
    assert len(widget.case_items) >= 3, "Provide at least three real studies"
    for name in [case[0] for case in widget.case_items[:3]]:
        case = next(c for c in widget.case_items if c[0] == name)
        widget.case_edit.setText(case[0])
        widget.image_edit.setText(case[1])
        widget.mask_edit.setText(case[2])
        widget._load_study()
        pump(100)
        assert widget.scene.ct is not None and widget.scene.aorta is not None
        assert widget.prediction is None and not widget.export_button.enabled
        assert not widget.sample_warning.visible and widget.table_stack.currentIndex == 0
        assert widget.run_button.enabled and widget.nav.done[0] and not widget.nav.done[1]
        assert widget.header_case.text == name.upper()
        empty = {"case_id": name, "parent": {"instance_id": "aorta"}, "daughters": []}
        widget.apply_prediction(empty, "TEST ONLY / empty-schema fixture, not detection")
        assert widget.export_button.enabled and widget.table_stack.currentIndex == 0
        assert "No branches detected" in widget.table_empty.title.text
        widget.clear_prediction()
        widget.save_screenshot(out / (name + "-loaded.png"))
        report["checks"].append(name + ": real CT and binary mask loaded; stale results cleared; empty JSON supported")
    widget.origins_check.setChecked(False)
    assert not widget.origins_check.checked
    widget.toggle_layout()
    widget.toggle_layout()
    original_style = widget.workspace_state["style"]
    widget.close_workspace()
    assert window.styleSheet == original_style
    assert widget.shortcuts == [] and widget.toast is None and widget.slice_headers == {}
    widget.open_workspace()
    assert widget.workspace_open and widget.toast is not None
    report["checks"].append("Layout switching and restoration of the original Slicer styling")
    widget.python_edit.setText(str(Path(slicer.app.applicationDirPath()) / ("PythonSlicer.exe" if sys.platform == "win32" else "PythonSlicer")))
    for fixture in ["success", "failure", "invalid", "cancel"]:
        widget.pipeline_edit.setText(str(root / "tests" / "fixtures" / (fixture + ".py")))
        assert widget.pipeline_pill.text.startswith("Connected"), widget.pipeline_pill.text
        widget._run_detection()
        assert widget.process is not None
        assert not widget.load_button.enabled and widget.activity.visible
        if fixture == "cancel":
            qt.QTimer.singleShot(300, widget.cancel_run)
        ticks = await_process(widget)
        assert widget.load_button.enabled and not widget.activity.visible
        if fixture == "success":
            assert widget.prediction is not None and widget.prediction["daughters"] == []
            # _run_detection returned while the child was still running (asserted above) and
            # the event loop was pumped at least once before completion: the run is asynchronous.
            assert ticks >= 1, "GUI event loop did not remain active"
        elif fixture == "failure":
            assert "failed (exit 3)" in widget.status.text, widget.status.text
            assert widget.prediction is None and widget.banner.current_kind == "error"
            widget.log_dialog.close()
        elif fixture == "invalid":
            assert "rejected" in widget.status.text, widget.status.text
            assert widget.prediction is None
            widget.log_dialog.close()
        else:
            assert "cancelled" in widget.status.text, widget.status.text
            assert widget.prediction is None and widget.banner.current_kind == "warning"
        report["checks"].append("Separate-process pipeline fixture: " + fixture)
    # Missing pipeline configuration must explain itself instead of running.
    widget.pipeline_edit.setText("")
    widget.run_detection()
    assert widget.process is None and widget.pipeline_section.expanded and widget.banner.current_kind == "error"
    report["checks"].append("Unconfigured pipeline opens the connection section with an explanation")
    # Wrong-case imports must leave the current prediction unchanged.
    widget.apply_prediction({"case_id": widget.loaded_case, "parent": {"instance_id": "aorta"}, "daughters": []}, "Test fixture")
    previous = widget.prediction
    try:
        widget.import_prediction_path(out / "synthetic_export.json")
        raise AssertionError("Mismatched-case JSON was accepted")
    except ValueError:
        assert widget.prediction is previous
    report["checks"].append("Mismatched case rejected without replacing previous results")
    # The module must survive File > Close Scene without stale node pointers.
    slicer.mrmlScene.Clear(0)
    pump(300)
    assert widget.loaded_case is None and widget.prediction is None
    assert widget.header_case.text == "No study loaded"
    view_node = slicer.app.layoutManager().threeDWidget(0).mrmlViewNode()
    assert not view_node.GetAxisLabelsVisible() and not view_node.GetBoxVisible(), "workspace view styling was not re-applied after scene close"
    assert len(widget.slice_observers) == 3
    widget._load_sample()
    widget.controls_tabs.setCurrentIndex(2)
    pump(300)
    assert widget.nav.index == 2
    widget.save_screenshot(out / "branchforge-display-controls.png")
    widget.tabs.setCurrentIndex(2)
    pump(300)
    assert widget.result_nav.index == 2
    widget.save_screenshot(out / "branchforge-json.png")
    report["checks"].append("Scene close and reload; display controls and JSON tab captured")
    report["success"] = True
except Exception:
    report["success"] = False
    report["traceback"] = traceback.format_exc()
    print(report["traceback"])
finally:
    faulthandler.cancel_dump_traceback_later()
    (out / "slicer-smoke-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    sys.exit(0 if report.get("success") else 1)
