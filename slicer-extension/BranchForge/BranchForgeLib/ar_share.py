"""Opt-in sharing controller. MRML/Qt stay on the UI thread; HTTP runs in a worker.

No tokens in logs, URLs (except the viewer read capability fragment), or MRML.
"""
import base64
import json
import queue
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
import qt
from .ar_export import export_scene, signature


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Sharing server redirected the request; use its canonical HTTPS URL.')


def request(base, method, token, session=None, body=None):
    url = base + '/api/session' + ('?id=' + session if session else '')
    payload = json.dumps(body, separators=(',', ':'), allow_nan=False).encode() if body is not None else None
    req = Request(url, data=payload, method=method,
                  headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    try:
        with build_opener(NoRedirect()).open(req, timeout=12) as response:
            return json.loads(response.read(100000))
    except HTTPError as error:
        try:
            message = json.loads(error.read(2000)).get('error', 'Sharing request failed.')
        except Exception:
            message = f'Sharing request failed (HTTP {error.code}). Check the website URL and deployment protection.'
        raise ValueError(message) from None


class SharingController:
    def __init__(self, widget):
        self.widget = widget
        self.session = None
        self.base = None
        self.enabled = False
        self.generation = 0
        self.busy = False
        self.last_signature = None
        self.last_upload = 0
        self.last_heartbeat = 0
        self.retry_at = 0
        self.events = queue.Queue()
        self.timer = qt.QTimer()
        self.timer.setInterval(1000)
        self.timer.connect('timeout()', self.tick)
        self.timer.start()

    def background(self, kind, fn):
        generation = self.generation
        target_base = self.base
        self.busy = True
        def work():
            try:
                self.events.put((generation, kind, fn(), None, target_base))
            except Exception as exc:
                self.events.put((generation, kind, None, str(exc), target_base))
        threading.Thread(target=work, daemon=True, name='BranchForge AR HTTP').start()

    def start(self, base, key):
        parsed = urlsplit(base.strip())
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost')):
            raise ValueError('Enter an HTTPS website URL. HTTP is allowed only for loopback testing.')
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
            raise ValueError('Use only the website origin, without paths, credentials or query strings.')
        if not parsed.hostname or len(key.strip()) < 32:
            raise ValueError('Enter the publisher key configured for the AR website (at least 32 characters).')
        if not self.widget.scene.aorta:
            raise ValueError('Load a study before starting AR sharing.')
        if self.enabled or self.busy:
            return
        self.base = f'{parsed.scheme}://{parsed.netloc}'
        self.enabled = True
        self.generation += 1
        self.last_signature = None
        self.widget.ar_status.setText('Creating a private, one-hour sharing link…')
        self.background('create', lambda b=self.base, k=key.strip(): request(b, 'POST', k))
        self.widget.ar_start.setEnabled(False)
        self.widget.ar_stop.setEnabled(True)

    def stop(self):
        self.enabled = False
        self.generation += 1
        self.busy = False
        session, base = self.session, self.base
        self.session = None
        self.widget.ar_qr.clear()
        self.widget.ar_link = None
        self.widget.ar_copy.setEnabled(False)
        self.widget.ar_start.setEnabled(True)
        self.widget.ar_stop.setEnabled(False)
        if session:
            self.widget.ar_start.setEnabled(False)
            self.widget.ar_status.setText('Revoking the phone link…')
            self.background('revoke', lambda: request(base, 'DELETE', session['writeToken'], session['id']))
        else:
            self.widget.ar_status.setText('Sharing is off. Nothing is uploaded.')

    def tick(self):
        while not self.events.empty():
            generation, kind, result, error, target_base = self.events.get_nowait()
            if generation != self.generation:
                if kind == 'create' and result:
                    # The user stopped while creation was in flight. Revoke the orphan.
                    # Capture its original host; a new session may use a different one.
                    def revoke_orphan(s=result, b=target_base):
                        try:
                            request(b, 'DELETE', s['writeToken'], s['id'])
                        except Exception:
                            pass  # Empty orphan still has the fixed one-hour TTL.
                    threading.Thread(target=revoke_orphan, daemon=True).start()
                continue
            self.busy = False
            if error:
                self.retry_at = time.monotonic() + 10
                self.last_signature = None
                if kind == 'create':
                    self.enabled = False
                    self.widget.ar_start.setEnabled(True)
                    self.widget.ar_stop.setEnabled(False)
                if kind == 'revoke':
                    self.widget.ar_start.setEnabled(True)
                prefix = 'Could not revoke; the link may remain readable until its one-hour expiry. ' if kind == 'revoke' else 'Sharing error: '
                self.widget.ar_status.setText(prefix + error)
                continue
            if kind == 'create':
                self.session = result
                self.widget.ar_link = result['url']
                pixmap = qt.QPixmap()
                pixmap.loadFromData(qt.QByteArray.fromBase64(result['qr']))
                self.widget.ar_qr.setPixmap(pixmap.scaled(176, 176, qt.Qt.KeepAspectRatio, qt.Qt.SmoothTransformation))
                self.widget.ar_copy.setEnabled(True)
                self.widget.ar_status.setText('Scan with your phone. Sending the first model…')
                qt.QTimer.singleShot(0, lambda: self.widget.ar_scroll.ensureWidgetVisible(self.widget.ar_qr, 0, 8))
            elif kind == 'upload':
                self.widget.ar_status.setText(f"Live · scene revision {result['version']}\nPhone updates within a few seconds. Link expires after one hour.")
            elif kind == 'revoke':
                self.widget.ar_start.setEnabled(True)
                self.widget.ar_status.setText('Sharing stopped. The phone link has been revoked.')
        if not self.enabled or not self.session or self.busy or time.monotonic() < self.retry_at:
            return
        if time.time() * 1000 >= self.session['expiresAt']:
            self.stop()
            return
        try:
            state = signature(self.widget.scene) + str(self.widget.synthetic)
            if state == self.last_signature:
                if time.monotonic() - self.last_heartbeat > 15:
                    session, base = self.session, self.base
                    self.last_heartbeat = time.monotonic()
                    self.background('heartbeat', lambda: request(base, 'PATCH', session['writeToken'], session['id']))
                return
            if time.monotonic() - self.last_upload < 2:
                return
            glb, meta = export_scene(self.widget.scene, self.widget.prediction, self.widget.synthetic)
            self.last_signature = state
            self.last_upload = time.monotonic()
            self.last_heartbeat = self.last_upload
            session, base = self.session, self.base
            self.background('upload', lambda: request(base, 'PUT', session['writeToken'], session['id'],
                              {'glb': base64.b64encode(glb).decode(), 'meta': meta}))
        except Exception as exc:
            self.retry_at = time.monotonic() + 10
            self.widget.ar_status.setText('Unable to share this scene: ' + str(exc))

    def cleanup(self):
        self.stop()
        self.timer.stop()
