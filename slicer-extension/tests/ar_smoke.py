"""New Slicer instance only. Synthetic native UI/export + optional local HTTP end-to-end."""
import base64
import json
from pathlib import Path
import struct
import time
import traceback
import faulthandler
import slicer
import qt
import vtk
from BranchForgeLib.ar_export import export_scene, build_glb, signature
from BranchForgeLib.ar_share import request
from BranchForgeLib.report import prediction_html

out = Path(__file__).resolve().parents[1] / 'artifacts' / 'ar-qa'
out.mkdir(parents=True, exist_ok=True)
report = {'checks': []}
trace_file = (out / 'thread-dump.log').open('w')
faulthandler.dump_traceback_later(30, repeat=True, file=trace_file)
def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        slicer.app.processEvents()
        time.sleep(.01)
def wait_for(predicate, timeout=25):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline: pump(.1)
    assert predicate(), 'Timed out waiting for sharing controller'

try:
    print('AR SMOKE: selecting module', flush=True)
    slicer.util.selectModule('BranchForge')
    print('AR SMOKE: module selected', flush=True)
    widget = slicer.modules.branchforge.widgetRepresentation().self()
    widget.settings = qt.QSettings(str(out / 'test-preferences.ini'), qt.QSettings.IniFormat)
    widget._load_sample()
    print('AR SMOKE: synthetic scene loaded', flush=True)
    pump(.5)
    assert 'Estimated radius' in widget.readable_view.toPlainText()
    assert json.loads(widget.json_view.toPlainText()) == widget.prediction
    assert widget.tabs.count == 4
    assert '&lt;script&gt;' in prediction_html({**widget.prediction, 'case_id': '<script>'})
    report['checks'].append('Readable results appear above parseable unchanged JSON; HTML escaped; AR tab built')
    cube = vtk.vtkCubeSource(); cube.SetXLength(100); cube.SetYLength(200); cube.SetZLength(300); cube.Update()
    glb, dims, _ = build_glb([(cube.GetOutput(), (.5, .8, .6), 1.)], [0, 0, 0])
    assert all(abs(a-b) < .001 for a,b in zip(dims, [100,300,200])), dims
    size = struct.unpack_from('<I', glb, 12)[0]
    doc = json.loads(glb[20:20+size])
    positions = doc['accessors'][0]
    assert abs(positions['max'][1] - .15) < 1e-6
    report['checks'].append('RAS-mm to Y-up metres: 100x200x300 mm becomes 0.1x0.3x0.2 metres without enlargement')
    glb, meta = export_scene(widget.scene, widget.prediction, True)
    assert meta['meshCount'] > 10 and meta['branchCount'] == 4 and len(glb) < 2_000_000
    assert b'synthetic_demo' not in glb and b'case_id' not in glb
    (out / 'synthetic.glb').write_bytes(glb)
    (out / 'synthetic-meta.json').write_text(json.dumps(meta))
    before = signature(widget.scene)
    widget.arrows_check.setChecked(False); widget.update_visibility()
    smaller, changed = export_scene(widget.scene, widget.prediction, True)
    assert changed['meshCount'] == meta['meshCount'] - 4 and signature(widget.scene) != before
    report['checks'].append('Visible aorta, reference branches, origins, seeds, rings, labels exported; arrows hide in export')
    widget.arrows_check.setChecked(True); widget.update_visibility()
    widget.ar_url.setText('http://127.0.0.1:5173')
    widget.ar_key.setText('local-only-branchforge-demo-publisher-key')
    widget.ar_consent.setChecked(True)
    widget.start_ar_sharing()
    wait_for(lambda: widget.ar_sharing.session is not None)
    wait_for(lambda: 'revision 1' in widget.ar_status.text)
    assert widget.ar_qr.pixmap is not None
    (out / 'local-viewer-url.txt').write_text(widget.ar_link)
    widget.tabs.setCurrentIndex(2); pump(.4)
    widget.save_screenshot(out / 'readable-results.png')
    widget.tabs.setCurrentIndex(3); pump(.4)
    widget.save_screenshot(out / 'ar-panel.png')
    session = widget.ar_sharing.session.copy()
    token = session['url'].split('#')[1].split('.')[1]
    assert request('http://127.0.0.1:5173', 'GET', token, session['id'])['version'] >= 1
    widget.arrows_check.setChecked(False); widget.update_visibility()
    wait_for(lambda: 'revision 2' in widget.ar_status.text)
    report['checks'].append('End-to-end: Qt QR created, background upload, phone metadata, visibility change publishes revision 2')
    widget.ar_sharing.stop()
    wait_for(lambda: 'revoked' in widget.ar_status.text)
    try:
        request('http://127.0.0.1:5173', 'GET', token, session['id'])
        raise AssertionError('Revoked link remained readable')
    except ValueError as error:
        assert 'expired' in str(error) or 'ended' in str(error)
    report['checks'].append('Stop sharing revokes link; cloud cannot be read afterward')
    widget.cleanup()
    report['passed'] = True
except Exception:
    report['passed'] = False
    report['error'] = traceback.format_exc()
finally:
    (out / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)
    slicer.app.exit(0 if report['passed'] else 1)
