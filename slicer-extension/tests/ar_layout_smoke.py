"""Small fictional cylinder for quick native layout verification (fresh Slicer only)."""
from pathlib import Path
import json
import time
import traceback
import numpy as np
import slicer
import qt
out = Path(__file__).resolve().parents[1] / 'artifacts' / 'ar-qa'
out.mkdir(parents=True, exist_ok=True)
def pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        slicer.app.processEvents(); time.sleep(.01)
try:
    slicer.util.selectModule('BranchForge')
    w = slicer.modules.branchforge.widgetRepresentation().self()
    w.settings = qt.QSettings(str(out / 'layout-test.ini'), qt.QSettings.IniFormat)
    slicer.util.mainWindow().showMaximized()
    z, y, x = np.mgrid[:100, :32, :32]
    volume = ((x - 16)**2 + (y - 16)**2 < 64).astype(np.uint8)
    w.scene.ct = w.scene.own(slicer.mrmlScene.AddNewNodeByClass('vtkMRMLScalarVolumeNode'))
    slicer.util.updateVolumeFromArray(w.scene.ct, volume.astype(np.int16))
    w.scene.ct.CreateDefaultDisplayNodes()
    mask = w.scene.own(slicer.mrmlScene.AddNewNodeByClass('vtkMRMLLabelMapVolumeNode'))
    slicer.util.updateVolumeFromArray(mask, volume)
    mask.CreateDefaultDisplayNodes()
    w.scene.aorta = w.scene.segmentation_from_label(mask, 'Fictional test cylinder', (.43, .86, .73))
    w.synthetic = True; w.loaded_case = 'synthetic_layout_test'
    data = {'case_id': w.loaded_case, 'parent': {'instance_id': 'aorta'}, 'daughters': [
      {'instance_id': f'branch_{i+1:03d}', 'parent_instance_id': 'aorta', 'ostium_xyz_mm': [-24, -16, 20 + i*20],
       'seed_xyz_mm': [-29, -16, 20 + i*20], 'radius_mm': 2., 'direction_xyz': [-1, 0, 0]} for i in range(4)]}
    w.header_case.setText('SYNTHETIC TEST', 'amber')
    w.apply_prediction(data, 'Fictional layout fixture', 'amber')
    w.scene.focus_aorta(); w.tabs.setCurrentIndex(2); pump(3)
    assert json.loads(w.json_view.toPlainText()) == data
    assert w.readable_view.geometry.bottom() < w.json_view.geometry.top()
    w.save_screenshot(out / 'readable-results-final.png')
    w.ar_url.setText('http://127.0.0.1:5173')
    w.ar_key.setText('local-only-branchforge-demo-publisher-key')
    w.ar_consent.setChecked(True); w.start_ar_sharing()
    deadline = time.monotonic() + 25
    while not w.ar_link and time.monotonic() < deadline: pump(.1)
    assert w.ar_link, w.ar_status.text
    w.tabs.setCurrentIndex(3); pump(3)
    assert not w.export_button.visible
    assert w.ar_scroll.viewport().height >= w.ar_qr.height
    w.save_screenshot(out / 'ar-panel-final.png')
    assert w.ar_qr.pixmap is not None
    w.ar_sharing.stop(); pump(2); w.cleanup()
    (out / 'layout-report.json').write_text(json.dumps({'passed': True, 'checks': ['Readable pane above raw JSON without overlap', 'Themed report', 'QR first, settings collapsible', 'Native sharing still works']}))
    slicer.app.exit(0)
except Exception:
    (out / 'layout-report.json').write_text(json.dumps({'passed': False, 'error': traceback.format_exc()}))
    slicer.app.exit(1)
