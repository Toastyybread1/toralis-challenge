"""Native Slicer round-trip test. Run in a NEW process; leaves the demo open."""
import hashlib
import json
from pathlib import Path
import traceback
import numpy as np
import qt
import slicer
import vtk

root = Path(__file__).resolve().parents[2]
out = root / 'slicer-extension/artifacts/nifti-export'
out.mkdir(parents=True, exist_ok=True)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check():
    report = {'success': False}
    try:
        from BranchForgeLib.paths import load_path_evidence
        slicer.util.selectModule('BranchForge')
        widget = slicer.modules.branchforge.widgetRepresentation().self()
        widget.settings = qt.QSettings(str(out / 'settings.ini'), qt.QSettings.IniFormat)
        source = root / 'tmp/integration-handoff/data/TORALIS CHALLENGE/subject021'
        inputs = [source / 'orig21.nii', source / 'mask21.nii']
        before = [digest(path) for path in inputs]
        widget.image_edit.setText(str(inputs[0]))
        widget.mask_edit.setText(str(inputs[1]))
        widget.case_edit.setText('subject021')
        widget.fold_combo.setCurrentIndex(3)
        widget._load_study()
        prediction_file = root / 'outputs/master-smoke/subject021.json'
        prediction = json.loads(prediction_file.read_text())
        paths, note = load_path_evidence(prediction_file, prediction)
        assert len(paths) == 4
        widget.apply_prediction(prediction, 'Verified saved detector run', paths=paths, path_note=note)
        assert widget.nifti_button.enabled
        matrix = vtk.vtkMatrix4x4()
        widget.scene.ct.GetIJKToRASMatrix(matrix)
        original_geometry = slicer.util.arrayFromVTKMatrix(matrix)
        seg_id = widget.scene.aorta.GetSegmentation().GetNthSegmentID(0)
        parent = slicer.util.arrayFromSegmentBinaryLabelmap(widget.scene.aorta, seg_id, widget.scene.ct)
        # A real scene edit must survive export; restore it for the final demo.
        edited = parent.copy()
        parent_locations = np.argwhere(parent != 0)
        location = tuple(parent_locations[len(parent_locations) // 2])
        edited[location] = 0
        slicer.util.updateSegmentBinaryLabelmapFromArray(edited, widget.scene.aorta, seg_id, widget.scene.ct)
        for suffix in ('.nii', '.nii.gz'):
            target = widget.export_edited_nifti_path(out / ('subject021_edited_labels' + suffix))
            loaded = slicer.util.loadLabelVolume(str(target), {'show': False})
            try:
                loaded.GetIJKToRASMatrix(matrix)
                np.testing.assert_allclose(slicer.util.arrayFromVTKMatrix(matrix), original_geometry, atol=1e-4)
                voxels = slicer.util.arrayFromVolume(loaded)
                assert voxels.shape == parent.shape
                assert set(np.unique(voxels)) == {0, 1, 2}
                np.testing.assert_array_equal(voxels == 1, edited != 0)
                assert voxels[location] != 1
                report[suffix] = {'bytes': target.stat().st_size, 'trace_voxels': int(np.count_nonzero(voxels == 2))}
            finally:
                widget.scene.remove_nodes([loaded])
        slicer.util.updateSegmentBinaryLabelmapFromArray(parent, widget.scene.aorta, seg_id, widget.scene.ct)
        widget.scene.aorta.CreateClosedSurfaceRepresentation()
        for original in inputs:
            try:
                widget.export_edited_nifti_path(original)
            except ValueError:
                pass
            else:
                raise AssertionError('Input overwrite was not blocked')
        widget.apply_prediction(prediction, 'JSON-only test')
        assert not widget.nifti_button.enabled
        try:
            widget.export_edited_nifti_path(out / 'missing-paths.nii')
        except ValueError:
            pass
        else:
            raise AssertionError('JSON-only export was not blocked')
        widget.apply_prediction(prediction, 'Verified saved detector run', paths=paths, path_note=note)
        assert [digest(path) for path in inputs] == before
        widget.table.selectRow(0)
        widget.show_page(1)
        widget.scene.focus_aorta()
        slicer.util.mainWindow().showMaximized()
        slicer.util.mainWindow().raise_()
        slicer.util.mainWindow().activateWindow()
        slicer.app.processEvents()
        widget.save_screenshot(out / 'export-button.png')
        report.update(success=True, branches=4, original_inputs_unchanged=True,
                      segmentation_edit_preserved=True, json_only_export_blocked=True,
                      geometry_roundtrip=True, slicer_version=slicer.app.applicationVersion)
    except Exception:
        report['traceback'] = traceback.format_exc()
        print(report['traceback'], flush=True)
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report), flush=True)


qt.QTimer.singleShot(0, check)
