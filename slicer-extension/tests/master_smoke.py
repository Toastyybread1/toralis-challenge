"""Run in a NEW Slicer process. Leave the verified subject-21 window open."""
import json
from pathlib import Path
import time
import traceback
import qt
import slicer

root = Path(__file__).resolve().parents[2]
out = root / 'slicer-extension/artifacts/master'
out.mkdir(parents=True, exist_ok=True)
report = {'success': False, 'accuracy_validated': False}


def check():
    try:
        from BranchForgeLib.contract import lps_to_ras
        slicer.util.selectModule('BranchForge')
        widget = slicer.modules.branchforge.widgetRepresentation().self()
        widget.settings = qt.QSettings(str(out / 'test-settings.ini'), qt.QSettings.IniFormat)
        widget.python_edit.setText(str(root / '.venv/Scripts/python.exe'))
        widget.pipeline_edit.setText(str(root / 'run.py'))
        source = root / 'tmp/integration-handoff/data/TORALIS CHALLENGE/subject021'
        widget.image_edit.setText(str(source / 'orig21.nii'))
        widget.mask_edit.setText(str(source / 'mask21.nii'))
        widget.case_edit.setText('subject021')
        widget.fold_combo.setCurrentIndex(3)
        slicer.util.mainWindow().showMaximized()
        slicer.util.mainWindow().raise_()
        slicer.util.mainWindow().activateWindow()
        widget._load_study()
        start = time.monotonic()
        widget._run_detection()
        ticks = 0
        while widget.process is not None and time.monotonic() - start < 600:
            slicer.app.processEvents()
            time.sleep(.01)
            ticks += 1
        assert widget.process is None, 'Detector did not complete within test timeout'
        assert widget.prediction is not None, widget.run_log
        expected = json.loads((root / 'outputs/predictions/subject021.json').read_text())
        assert widget.prediction == expected, 'Output differs from held-out reference prediction'
        assert len(widget.scene.paths) == 4 and len(widget.path_evidence) == 4
        assert widget.table.rowCount == 4
        for i, branch in enumerate(expected['daughters']):
            actual = [0., 0., 0.]
            widget.scene.points.GetNthControlPointPositionWorld(i, actual)
            assert all(abs(a-b) < 1e-5 for a,b in zip(actual, lps_to_ras(branch['ostium_xyz_mm'])))
            assert widget.scene.paths[i].GetAttribute('BranchForge.SourceCandidate') == widget.path_evidence[branch['instance_id']]['source_candidate']
        exported = out / 'subject021.json'
        widget.export_prediction_path(exported)
        assert json.loads(exported.read_text()) == expected
        widget.table.selectRow(0)
        widget.scene.focus_aorta()
        widget.show_page(1)
        for _ in range(30):
            slicer.app.processEvents()
            time.sleep(.02)
        widget.save_screenshot(out / 'subject021.png')
        report.update(success=True, branches=4, actual_centerlines=4,
                      exact_reference_json=True, ras_markers_verified=True,
                      responsive_event_ticks=ticks, seconds=time.monotonic()-start,
                      slicer_version=slicer.app.applicationVersion)
        report['path_source_ids'] = {key: value['source_candidate'] for key,value in widget.path_evidence.items()}
        (out / 'pipeline.log').write_text(widget.run_log, encoding='utf-8')
    except Exception:
        report['traceback'] = traceback.format_exc()
        print(report['traceback'], flush=True)
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report), flush=True)


qt.QTimer.singleShot(0, check)
