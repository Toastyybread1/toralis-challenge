"""Presentation layer for BranchForge: design tokens, icons, painted controls and motion.

Everything in this module is cosmetic. Prediction data, physical coordinates and
the pipeline boundary live in contract.py, scene.py and BranchForge.py and are
never changed here. Widgets are plain PythonQt objects: custom looks are painted
with QPainter and mouse input arrives through event filters, which is the
combination that Slicer's PythonQt bindings reliably support.
"""

import html
import logging
import math
import re
from pathlib import Path

import qt

# --------------------------------------------------------------------------- tokens

T = {
    "canvas": "#070B12",
    "surface": "#0C1320",
    "card": "#111A2A",
    "raised": "#172234",
    "hover": "#1C293C",
    "line": "#1E2A3C",
    "line2": "#2B3A50",
    "text": "#EEF3F9",
    "text2": "#9FB0C4",
    "muted": "#64758B",
    "mint": "#6EF0C2",
    "mint2": "#23A882",
    "mintdim": "#173F36",
    "ink": "#0B2A22",
    "amber": "#FFB86B",
    "ivory": "#EAF2FF",
    "red": "#FF6B7A",
    "gold": "#F5C56B",
    "blue": "#7FB4FF",
    "violet": "#C4A6FF",
    "axial": "#FF7A7A",
    "sagittal": "#FFD166",
    "coronal": "#7CE37B",
}

KIND_COLORS = {"info": "blue", "success": "mint", "warning": "gold", "error": "red", "muted": "muted", "mint": "mint", "amber": "amber"}
KIND_ICONS = {"info": "info", "success": "check", "warning": "warning", "error": "error"}

ICON_DIR = Path(__file__).resolve().parents[1] / "Resources" / "Icons"
MAX_SIZE = 16777215


def _pick_font(*families):
    try:
        available = set(qt.QFontDatabase().families())
    except Exception:
        available = set()
    for family in families:
        if family in available:
            return family
    return families[-1]


FONT_UI = _pick_font("Segoe UI Variable Text", "Segoe UI", "Arial")
FONT_DISPLAY = _pick_font("Segoe UI Variable Display", "Segoe UI Semibold", "Segoe UI", "Arial")
FONT_MONO = _pick_font("Cascadia Mono", "Consolas", "Courier New")


def color(name, alpha=None):
    """Token name or #hex to QColor, optionally with a 0-255 alpha."""
    c = qt.QColor(T.get(name, name))
    if alpha is not None:
        c.setAlpha(int(alpha))
    return c


def mix(a, b, t):
    a, b = color(a), color(b)
    t = max(0.0, min(1.0, t))
    return qt.QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t), int(a.blue() + (b.blue() - a.blue()) * t), int(a.alpha() + (b.alpha() - a.alpha()) * t))


def font(px, weight=qt.QFont.Normal, mono=False, display=False, spacing=0.0):
    f = qt.QFont(FONT_MONO if mono else FONT_DISPLAY if display else FONT_UI)
    f.setPixelSize(int(round(px)))
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(qt.QFont.AbsoluteSpacing, spacing)
    return f


def text_width(f, text):
    return qt.QFontMetrics(f).horizontalAdvance(text)


def raise_widget(widget):
    # PythonQt exposes QWidget::raise under a keyword-safe name.
    method = getattr(widget, "raise_", None) or getattr(widget, "raise", None)
    if method:
        method()


def pixmap(name, tint="text2", size=16):
    """Crisp high-DPI pixmap of an icon for QLabel marks and painter calls."""
    key = ("pm", name, tint, size)
    if key not in _ICONS:
        _ICONS[key] = _tinted_pixmap(ICON_DIR / (name + ".svg"), size * 2, tint)
    return _ICONS[key]


# --------------------------------------------------------------------------- icons

_ICONS = {}


def _render_svg(path, px):
    """Rasterise an SVG at an exact pixel size.

    Slicer's Qt build has no SVG icon engine, so QIcon(path).pixmap() never renders
    larger than the file's native 24 px. The SVG image-format plugin does honour a
    scaled size through QImageReader, which keeps icons crisp at any size and DPI.
    """
    reader = qt.QImageReader(str(path))
    reader.setScaledSize(qt.QSize(px, px))
    image = reader.read()
    if image is None or image.isNull():
        return qt.QIcon(str(path)).pixmap(px, px)
    return qt.QPixmap.fromImage(image)


def _tinted_pixmap(base, px, tint, opacity=1.0):
    src = _render_svg(base, px) if isinstance(base, (str, Path)) else base.pixmap(px, px)
    out = qt.QPixmap(px, px)
    out.fill(qt.Qt.transparent)
    p = qt.QPainter(out)
    p.setOpacity(opacity)
    p.drawPixmap(0, 0, src)
    p.setCompositionMode(qt.QPainter.CompositionMode_SourceIn)
    p.fillRect(qt.QRect(0, 0, px, px), color(tint))
    p.end()
    out.setDevicePixelRatio(2.0)
    return out


def icon(name, tint="text2", size=18):
    """Monochrome SVG icon tinted at runtime; rendered at 2x for high-DPI displays."""
    key = (name, tint, size)
    if key not in _ICONS:
        path = ICON_DIR / (name + ".svg")
        if tint is None:
            _ICONS[key] = qt.QIcon(str(path))
        else:
            result = qt.QIcon(_tinted_pixmap(path, size * 2, tint))
            result.addPixmap(_tinted_pixmap(path, size * 2, tint, 0.38), qt.QIcon.Disabled)
            _ICONS[key] = result
    return _ICONS[key]


def dot_pixmap(rgb, size=10, ring=None):
    """Small colored disc used for legends and table rows."""
    px = size * 2
    pm = qt.QPixmap(px, px)
    pm.fill(qt.Qt.transparent)
    p = qt.QPainter(pm)
    p.setRenderHint(qt.QPainter.Antialiasing)
    p.setPen(qt.Qt.NoPen)
    p.setBrush(qt.QBrush(qt.QColor.fromRgbF(*rgb) if isinstance(rgb, tuple) else color(rgb)))
    p.drawEllipse(qt.QRectF(2, 2, px - 4, px - 4))
    if ring:
        pen = qt.QPen(color(ring), 2)
        p.setPen(pen)
        p.setBrush(qt.QBrush())
        p.drawEllipse(qt.QRectF(1, 1, px - 2, px - 2))
    p.end()
    pm.setDevicePixelRatio(2.0)
    return pm


# --------------------------------------------------------------------------- motion

_LIVE = set()


def animate(start, end, duration, on_value, on_finish=None, easing=qt.QEasingCurve.OutCubic, loops=1):
    """Drive a float from start to end. The animation object is kept alive until it finishes."""
    anim = qt.QVariantAnimation()
    anim.setStartValue(float(start))
    anim.setEndValue(float(end))
    anim.setDuration(int(duration))
    anim.setEasingCurve(qt.QEasingCurve(easing))
    anim.setLoopCount(loops)

    def value(v):
        try:
            on_value(float(v))
        except Exception as exc:
            # Typically the target was destroyed (e.g. a replaced graphics effect); end quietly.
            logging.debug("BranchForge animation stopped: %s", exc)
            stop(anim)

    def finished():
        _LIVE.discard(anim)
        if on_finish:
            try:
                on_finish()
            except Exception:
                logging.exception("BranchForge animation completion failed")

    anim.connect("valueChanged(QVariant)", value)
    anim.connect("finished()", finished)
    _LIVE.add(anim)
    anim.start()
    return anim


def stop(anim):
    if anim is not None:
        try:
            anim.stop()
        except Exception:
            pass
        _LIVE.discard(anim)


def fade_in(widget, duration=220, start=0.0):
    """Fade a regular widget in; the graphics effect is removed afterwards so text stays crisp."""
    if widget.graphicsEffect() is not None:
        return None  # A fade is already running on this widget.
    effect = qt.QGraphicsOpacityEffect(widget)
    effect.setOpacity(start)
    widget.setGraphicsEffect(effect)

    def done():
        try:
            widget.setGraphicsEffect(None)
        except Exception:
            pass

    return animate(start, 1.0, duration, effect.setOpacity, done)


class EventRelay(qt.QObject):
    """Forwards Qt events to a Python callable; the confirmed way to receive input in PythonQt."""

    def __init__(self, handler):
        qt.QObject.__init__(self)
        self.handler = handler

    def eventFilter(self, obj, event):
        try:
            return bool(self.handler(obj, event))
        except Exception:
            logging.exception("BranchForge event handler failed")
            return False


# --------------------------------------------------------------------------- painted base

class Painted(qt.QWidget):
    """QWidget whose look is painted in Python. Subclasses override paint() and on_* hooks."""

    def __init__(self, parent=None):
        if parent is None:
            qt.QWidget.__init__(self)
        else:
            qt.QWidget.__init__(self, parent)
        self.hovered = False
        self.pressed = False
        self._relay = EventRelay(self._event)
        self.installEventFilter(self._relay)
        self.setMouseTracking(True)

    def _event(self, obj, event):
        kind = event.type()
        if kind == qt.QEvent.Enter:
            self.hovered = True
            self.update()
            return self.on_enter()
        if kind == qt.QEvent.Leave:
            self.hovered = False
            self.pressed = False
            self.update()
            return self.on_leave()
        if kind == qt.QEvent.MouseButtonPress and event.button() == qt.Qt.LeftButton:
            self.pressed = True
            self.update()
            return self.on_press(event.pos())
        if kind == qt.QEvent.MouseButtonRelease:
            self.pressed = False
            self.update()
            return self.on_release(event.pos())
        if kind == qt.QEvent.MouseMove:
            return self.on_move(event.pos())
        return False

    def on_enter(self):
        return False

    def on_leave(self):
        return False

    def on_press(self, pos):
        return False

    def on_release(self, pos):
        return False

    def on_move(self, pos):
        return False

    def painter(self):
        p = qt.QPainter(self)
        p.setRenderHint(qt.QPainter.Antialiasing)
        p.setRenderHint(qt.QPainter.TextAntialiasing)
        p.setRenderHint(qt.QPainter.SmoothPixmapTransform)
        return p

    def paintEvent(self, event):
        p = self.painter()
        try:
            self.paint(p)
        except Exception:
            logging.exception("BranchForge paint failed")
        finally:
            p.end()

    def paint(self, p):
        pass


def rounded(p, rect, radius, fill=None, stroke=None, width=1.0):
    path = qt.QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    if fill is not None:
        p.fillPath(path, qt.QBrush(fill))
    if stroke is not None:
        p.setPen(qt.QPen(stroke, width))
        p.setBrush(qt.QBrush())
        p.drawPath(path)
    return path


# --------------------------------------------------------------------------- ripple buttons

class RippleOverlay(Painted):
    """Material-style press ripple drawn over any button, clipped to its rounded corners."""

    def __init__(self, host, radius=9, dark=False):
        Painted.__init__(self, host)
        self.host = host
        self.radius = radius
        self.dark = dark
        self.ripples = []
        self.setAttribute(qt.Qt.WA_TransparentForMouseEvents)
        self.setGeometry(0, 0, host.width, host.height)
        self._host_relay = EventRelay(self._host_event)
        host.installEventFilter(self._host_relay)
        self.hide()

    def _host_event(self, obj, event):
        kind = event.type()
        if kind == qt.QEvent.Resize:
            self.setGeometry(0, 0, self.host.width, self.host.height)
        elif kind == qt.QEvent.MouseButtonPress and event.button() == qt.Qt.LeftButton and self.host.isEnabled():
            self.start(event.pos())
        return False

    def start(self, pos):
        self.setGeometry(0, 0, self.host.width, self.host.height)
        self.show()
        raise_widget(self)
        ripple = {"x": pos.x(), "y": pos.y(), "t": 0.0}

        def tick(v):
            ripple["t"] = v
            self.update()

        def done():
            if ripple in self.ripples:
                self.ripples.remove(ripple)
            if not self.ripples:
                self.hide()
            self.update()

        self.ripples.append(ripple)
        animate(0.0, 1.0, 560, tick, done, easing=qt.QEasingCurve.OutQuad)

    def paint(self, p):
        if not self.ripples:
            return
        w, h = self.width, self.height
        clip = qt.QPainterPath()
        clip.addRoundedRect(qt.QRectF(0.5, 0.5, w - 1, h - 1), self.radius, self.radius)
        p.setClipPath(clip)
        reach = math.hypot(w, h)
        p.setPen(qt.Qt.NoPen)
        for ripple in self.ripples:
            t = ripple["t"]
            alpha = int((1.0 - t) * (70 if self.dark else 80))
            base = qt.QColor(0, 0, 0, alpha) if self.dark else qt.QColor(255, 255, 255, alpha)
            radius = 8 + t * reach
            p.setBrush(qt.QBrush(base))
            p.drawEllipse(qt.QPointF(ripple["x"], ripple["y"]), radius, radius)


BUTTON_NAMES = {"primary": "BFPrimary", "secondary": "BFSecondary", "ghost": "BFGhost", "icon": "BFIconButton", "danger": "BFDanger", "link": "BFLink"}
BUTTON_TINTS = {"primary": "ink", "secondary": "text", "ghost": "text2", "icon": "text2", "danger": "text", "link": "mint"}
# PythonQt does not allow new Python attributes on plain C++ widgets, so overlay
# objects are kept alive here rather than on their host buttons.
_OVERLAYS = []


def button(text, callback, kind="secondary", icon_name=None, tooltip=None, name=None, radius=9):
    """Styled push button with a press ripple. `name` overrides the QSS object name."""
    widget = qt.QPushButton(text)
    widget.setObjectName(name or BUTTON_NAMES.get(kind, "BFSecondary"))
    widget.setCursor(qt.Qt.PointingHandCursor)
    widget.setFocusPolicy(qt.Qt.NoFocus)
    if icon_name:
        widget.setIcon(icon(icon_name, BUTTON_TINTS.get(kind, "text2")))
        widget.setIconSize(qt.QSize(18, 18) if kind == "icon" else qt.QSize(16, 16))
    if tooltip:
        widget.setToolTip(tooltip)
    widget.connect("clicked()", callback)
    _OVERLAYS.append(RippleOverlay(widget, radius=radius, dark=(kind == "primary")))
    return widget


def label(text, name=None, wrap=False):
    widget = qt.QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    widget.setTextFormat(qt.Qt.PlainText)
    return widget


def divider(layout):
    line = qt.QFrame()
    line.setObjectName("BFDivider")
    line.setFixedHeight(1)
    layout.addWidget(line)
    return line


def card(title=None, icon_name=None, name="BFCard", spacing=8):
    """Elevated section container. Returns (frame, body_layout)."""
    frame = qt.QFrame()
    frame.setObjectName(name)
    layout = qt.QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 12)
    layout.setSpacing(spacing)
    if title:
        head = qt.QHBoxLayout()
        head.setSpacing(6)
        if icon_name:
            mark = qt.QLabel()
            mark.setPixmap(pixmap(icon_name, "muted", 14))
            head.addWidget(mark)
        head.addWidget(label(title, "BFCardTitle"))
        head.addStretch(1)
        layout.addLayout(head)
    return frame, layout


def restyle(widget):
    """Re-apply QSS after a dynamic property used by a selector changes."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


# --------------------------------------------------------------------------- controls

class Segmented(Painted):
    """Pill-style segmented control with a sliding indicator and optional step numbers."""

    def __init__(self, items, on_change=None, height=36):
        Painted.__init__(self)
        self.items = [(text, badge) for text, badge in items]
        self.on_change = on_change
        self.index = 0
        self.position = 0.0
        self.hover_index = -1
        self.done = [False] * len(items)
        self.anim = None
        self.setFixedHeight(height)
        self.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Fixed)
        self.setCursor(qt.Qt.PointingHandCursor)

    def sizeHint(self):
        return qt.QSize(240, self.height)

    def set_done(self, index, done):
        if 0 <= index < len(self.done) and self.done[index] != done:
            self.done[index] = done
            self.update()

    def set_index(self, index, animate_move=True, notify=True):
        index = max(0, min(len(self.items) - 1, int(index)))
        changed = index != self.index
        self.index = index
        if not changed:
            if self.anim is None or self.anim.state == 0:
                self._slide(index)
            return
        stop(self.anim)
        if animate_move:
            self.anim = animate(self.position, index, 240, self._slide)
        else:
            self._slide(index)
        if changed and notify and self.on_change:
            self.on_change(index)

    def _slide(self, value):
        self.position = value
        self.update()

    def _segment_at(self, x):
        width = max(1.0, (self.width - 6) / len(self.items))
        return max(0, min(len(self.items) - 1, int((x - 3) / width)))

    def on_press(self, pos):
        self.set_index(self._segment_at(pos.x()))
        return True

    def on_move(self, pos):
        index = self._segment_at(pos.x())
        if index != self.hover_index:
            self.hover_index = index
            self.update()
        return False

    def on_leave(self):
        self.hover_index = -1
        self.update()
        return False

    def paint(self, p):
        w, h = self.width, self.height
        n = len(self.items)
        rounded(p, qt.QRectF(0.5, 0.5, w - 1, h - 1), 10, color("card"), color("line"))
        seg = (w - 6) / n
        if 0 <= self.hover_index < n and self.hover_index != self.index:
            rounded(p, qt.QRectF(3 + seg * self.hover_index, 3, seg, h - 6), 8, color("hover"))
        x = 3 + seg * self.position
        rounded(p, qt.QRectF(x, 3, seg, h - 6), 8, color("raised"), color("mint", 110))
        # Soft glow under the indicator.
        glow = qt.QLinearGradient(x, 3, x, h - 3)
        glow.setColorAt(0.0, color("mint", 26))
        glow.setColorAt(1.0, color("mint", 0))
        rounded(p, qt.QRectF(x, 3, seg, h - 6), 8, qt.QBrush(glow))
        text_font = font(12, qt.QFont.DemiBold)
        badge_font = font(10, qt.QFont.Bold, mono=True)
        for i, (text, badge) in enumerate(self.items):
            active = i == self.index
            left = 3 + seg * i
            tone = color("text") if active else color("text2") if self.done[i] else color("muted")
            content = text_width(text_font, text) + (22 if badge else 0)
            cx = left + (seg - content) / 2
            if badge:
                circle = qt.QRectF(cx, (h - 16) / 2, 16, 16)
                if self.done[i] and not active:
                    p.setPen(qt.Qt.NoPen)
                    p.setBrush(qt.QBrush(color("mint2")))
                    p.drawEllipse(circle)
                    pen = qt.QPen(color("ink"), 1.8)
                    pen.setCapStyle(qt.Qt.RoundCap)
                    p.setPen(pen)
                    p.drawLine(qt.QPointF(cx + 4.5, h / 2), qt.QPointF(cx + 7, h / 2 + 2.6), )
                    p.drawLine(qt.QPointF(cx + 7, h / 2 + 2.6), qt.QPointF(cx + 11.6, h / 2 - 3))
                else:
                    p.setPen(qt.Qt.NoPen)
                    p.setBrush(qt.QBrush(color("mint") if active else color("line2")))
                    p.drawEllipse(circle)
                    p.setFont(badge_font)
                    p.setPen(qt.QPen(color("ink") if active else color("text2")))
                    p.drawText(circle, qt.Qt.AlignCenter, badge)
                cx += 22
            p.setFont(text_font)
            p.setPen(qt.QPen(tone))
            p.drawText(qt.QRectF(cx, 0, seg, h), qt.Qt.AlignVCenter | qt.Qt.AlignLeft, text)


class ToggleSwitch(Painted):
    """Animated on/off switch. `checked` mirrors QCheckBox's property for existing call sites."""

    def __init__(self, checked=True, accent="mint", on_toggle=None):
        Painted.__init__(self)
        self.checked = bool(checked)
        self.accent = accent
        self.on_toggle = on_toggle
        self.position = 1.0 if checked else 0.0
        self.anim = None
        self.setFixedSize(40, 22)
        self.setCursor(qt.Qt.PointingHandCursor)

    def isChecked(self):
        return self.checked

    def setChecked(self, value, animate_move=True):
        value = bool(value)
        if value == self.checked:
            return
        self.checked = value
        stop(self.anim)
        if animate_move:
            self.anim = animate(self.position, 1.0 if value else 0.0, 200, self._slide, easing=qt.QEasingCurve.OutBack)
        else:
            self._slide(1.0 if value else 0.0)
        if self.on_toggle:
            self.on_toggle(value)

    def toggle(self):
        self.setChecked(not self.checked)

    def _slide(self, value):
        self.position = value
        self.update()

    def on_press(self, pos):
        if self.isEnabled():
            self.toggle()
        return True

    def paint(self, p):
        t = max(0.0, min(1.0, self.position))
        track = mix("line2", self.accent, t)
        if not self.isEnabled():
            track.setAlpha(110)
        rounded(p, qt.QRectF(0.5, 0.5, 39, 21), 10.5, track)
        if self.hovered and self.isEnabled():
            rounded(p, qt.QRectF(0.5, 0.5, 39, 21), 10.5, None, color("text", 60))
        knob_x = 11 + t * 18
        p.setPen(qt.Qt.NoPen)
        p.setBrush(qt.QBrush(qt.QColor(0, 0, 0, 70)))
        p.drawEllipse(qt.QPointF(knob_x, 12.2), 7.5, 7.5)
        p.setBrush(qt.QBrush(mix("text2", "ivory", t)))
        p.drawEllipse(qt.QPointF(knob_x, 11), 7.5, 7.5)


class ToggleRow(Painted):
    """A full-width layer row: colour swatch, title, description and a ToggleSwitch."""

    def __init__(self, title, subtitle, swatch, checked=True, on_toggle=None):
        Painted.__init__(self)
        self.title = title
        self.subtitle = subtitle
        self.swatch = swatch
        self.switch = ToggleSwitch(checked, swatch if swatch in T else "mint", on_toggle)
        layout = qt.QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.addStretch(1)
        layout.addWidget(self.switch)
        self.setFixedHeight(46)
        self.setCursor(qt.Qt.PointingHandCursor)

    def on_press(self, pos):
        if self.isEnabled():
            self.switch.toggle()
        return True

    def paint(self, p):
        if self.hovered:
            rounded(p, qt.QRectF(0.5, 0.5, self.width - 1, self.height - 1), 8, color("hover"))
        swatch = qt.QColor.fromRgbF(*self.swatch) if isinstance(self.swatch, tuple) else color(self.swatch)
        p.setPen(qt.Qt.NoPen)
        p.setBrush(qt.QBrush(swatch))
        p.drawEllipse(qt.QPointF(17, self.height / 2), 5, 5)
        p.setFont(font(12, qt.QFont.DemiBold))
        p.setPen(qt.QPen(color("text") if self.switch.checked else color("text2")))
        p.drawText(qt.QRectF(32, 6, self.width - 90, 18), qt.Qt.AlignVCenter | qt.Qt.AlignLeft, self.title)
        p.setFont(font(10))
        p.setPen(qt.QPen(color("muted")))
        p.drawText(qt.QRectF(32, 24, self.width - 90, 16), qt.Qt.AlignVCenter | qt.Qt.AlignLeft, self.subtitle)


class Pill(Painted):
    """Small status capsule with a coloured dot; `tone` is a token name."""

    def __init__(self, text="", tone="muted", mono=False):
        Painted.__init__(self)
        self.text = text
        self.tone = tone
        self.mono = mono
        self.setFixedHeight(24)
        self.setSizePolicy(qt.QSizePolicy.Fixed, qt.QSizePolicy.Fixed)
        self.setText(text, tone)

    def _font(self):
        return font(11 if not self.mono else 10, qt.QFont.DemiBold, mono=self.mono, spacing=0.6)

    def sizeHint(self):
        return qt.QSize(text_width(self._font(), self.text) + 34, 24)

    def setText(self, text, tone=None):
        self.text = text
        if tone:
            self.tone = tone
        self.updateGeometry()
        self.setFixedWidth(self.sizeHint().width())
        self.update()

    def paint(self, p):
        accent = color(self.tone)
        fill = qt.QColor(accent)
        fill.setAlpha(28)
        border = qt.QColor(accent)
        border.setAlpha(90)
        rounded(p, qt.QRectF(0.5, 0.5, self.width - 1, self.height - 1), 11.5, fill, border)
        p.setPen(qt.Qt.NoPen)
        p.setBrush(qt.QBrush(accent))
        p.drawEllipse(qt.QPointF(12, self.height / 2), 3.2, 3.2)
        p.setFont(self._font())
        p.setPen(qt.QPen(mix(self.tone, "text", 0.35)))
        p.drawText(qt.QRectF(22, 0, self.width - 26, self.height), qt.Qt.AlignVCenter | qt.Qt.AlignLeft, self.text)


class Stepper(Painted):
    """Header workflow rail: numbered steps with done / active / pending states and a live glow."""

    def __init__(self, steps):
        Painted.__init__(self)
        self.steps = list(steps)
        self.states = ["pending"] * len(steps)
        self.states[0] = "active"
        self.glow = 0.0
        self.busy = False
        self.setFixedHeight(34)
        self.label_font = font(11, qt.QFont.DemiBold, spacing=1.4)
        self.num_font = font(10, qt.QFont.Bold, mono=True)
        self.anim = None

    def start(self):
        """Begin the soft glow on the active step; call while the workspace is visible."""
        if self.anim is None:
            self.anim = animate(0.0, 1.0, 1600, self._pulse, loops=-1, easing=qt.QEasingCurve.InOutSine)

    def stop(self):
        stop(self.anim)
        self.anim = None

    def _pulse(self, v):
        self.glow = v
        if self.isVisible():
            self.update()

    def sizeHint(self):
        width = 8
        for step in self.steps:
            width += 24 + 8 + text_width(self.label_font, step.upper()) + 30
        return qt.QSize(width - 30 + 8, 34)

    def set_states(self, states, busy=False):
        self.states = list(states)
        self.busy = busy
        self.update()

    def paint(self, p):
        x = 8.0
        cy = self.height / 2
        for i, step in enumerate(self.steps):
            state = self.states[i]
            circle = qt.QRectF(x, cy - 12, 24, 24)
            text = step.upper()
            if state == "done":
                p.setPen(qt.Qt.NoPen)
                p.setBrush(qt.QBrush(color("mint2")))
                p.drawEllipse(circle)
                pen = qt.QPen(color("ink"), 2.2)
                pen.setCapStyle(qt.Qt.RoundCap)
                p.setPen(pen)
                p.drawLine(qt.QPointF(x + 7.5, cy + 0.5), qt.QPointF(x + 10.5, cy + 3.5))
                p.drawLine(qt.QPointF(x + 10.5, cy + 3.5), qt.QPointF(x + 16.5, cy - 3.5))
            elif state == "active":
                halo = 4 + 3 * math.sin(self.glow * math.pi)
                p.setPen(qt.Qt.NoPen)
                p.setBrush(qt.QBrush(color("mint", 22)))
                p.drawEllipse(qt.QPointF(x + 12, cy), 12 + halo, 12 + halo)
                p.setBrush(qt.QBrush(color("mint")))
                p.drawEllipse(circle)
                p.setFont(self.num_font)
                p.setPen(qt.QPen(color("ink")))
                p.drawText(circle, qt.Qt.AlignCenter, str(i + 1))
            else:
                p.setPen(qt.QPen(color("line2"), 1.5))
                p.setBrush(qt.QBrush(color("surface")))
                p.drawEllipse(circle)
                p.setFont(self.num_font)
                p.setPen(qt.QPen(color("muted")))
                p.drawText(circle, qt.Qt.AlignCenter, str(i + 1))
            p.setFont(self.label_font)
            tone = color("text") if state == "active" else color("text2") if state == "done" else color("muted")
            p.setPen(qt.QPen(tone))
            width = text_width(self.label_font, text)
            p.drawText(qt.QRectF(x + 32, 0, width + 4, self.height), qt.Qt.AlignVCenter | qt.Qt.AlignLeft, text)
            x += 32 + width
            if i < len(self.steps) - 1:
                pen = qt.QPen(color("mint2") if state == "done" else color("line2"), 1.5)
                p.setPen(pen)
                p.drawLine(qt.QPointF(x + 8, cy), qt.QPointF(x + 22, cy))
                x += 30


class ActivityBar(Painted):
    """Thin sweeping progress indicator shown while the detector runs."""

    def __init__(self):
        Painted.__init__(self)
        self.phase = 0.0
        self.anim = None
        self.setFixedHeight(4)
        self.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Fixed)
        self.hide()

    def start(self):
        stop(self.anim)
        self.anim = animate(0.0, 1.0, 1300, self._tick, loops=-1, easing=qt.QEasingCurve.InOutQuad)
        self.show()

    def finish(self):
        stop(self.anim)
        self.anim = None
        self.hide()

    def _tick(self, v):
        self.phase = v
        self.update()

    def paint(self, p):
        w, h = self.width, self.height
        rounded(p, qt.QRectF(0, 0, w, h), 2, color("line"))
        span = w * 0.35
        x = -span + (w + span) * self.phase
        grad = qt.QLinearGradient(x, 0, x + span, 0)
        grad.setColorAt(0.0, color("mint", 0))
        grad.setColorAt(0.5, color("mint"))
        grad.setColorAt(1.0, color("mint", 0))
        rounded(p, qt.QRectF(x, 0, span, h), 2, qt.QBrush(grad))


class MetricLabel(qt.QLabel):
    """Large numeric readout that counts up to its new value."""

    def __init__(self, name="BFMetric"):
        qt.QLabel.__init__(self, "--")
        self.setObjectName(name)
        self.setTextFormat(qt.Qt.PlainText)
        self.value = None
        self.anim = None

    def set_value(self, value):
        stop(self.anim)
        if value is None:
            self.value = None
            self.setObjectName("BFMetricEmpty")
            restyle(self)
            self.setText("—")
            return
        if self.objectName != "BFMetric":
            self.setObjectName("BFMetric")
            restyle(self)
        start = self.value or 0
        self.value = int(value)
        # Show the starting figure at once so the label is never stale while the
        # first animation tick waits behind a heavy render.
        self.setText(f"{start:02d}")
        if start == self.value:
            return
        self.anim = animate(start, self.value, 520, lambda v: self.setText(f"{int(round(v)):02d}"), lambda: self.setText(f"{self.value:02d}"))


class Collapsible(qt.QWidget):
    """Disclosure section whose body height animates open and closed."""

    def __init__(self, title, content, icon_name=None, expanded=False):
        qt.QWidget.__init__(self)
        self.expanded = expanded
        self.anim = None
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.toggle_button = button(title, self.toggle, "ghost", icon_name="chevron-right", radius=8)
        self.toggle_button.setObjectName("BFDisclosure")
        layout.addWidget(self.toggle_button)
        self.body = qt.QWidget()
        body_layout = qt.QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.addWidget(content)
        layout.addWidget(self.body)
        self.body.setMaximumHeight(MAX_SIZE if expanded else 0)
        self._sync_icon()

    def _sync_icon(self):
        self.toggle_button.setIcon(icon("chevron-down" if self.expanded else "chevron-right", "text2"))

    def toggle(self):
        self.set_expanded(not self.expanded)

    def set_expanded(self, expanded, animate_move=True):
        expanded = bool(expanded)
        if expanded == self.expanded:
            return
        self.expanded = expanded
        self._sync_icon()
        stop(self.anim)
        target = self.body.sizeHint.height() if expanded else 0
        current = min(self.body.maximumHeight, self.body.sizeHint.height() + 4)
        if not animate_move:
            self.body.setMaximumHeight(MAX_SIZE if expanded else 0)
            return

        def done():
            if self.expanded:
                self.body.setMaximumHeight(MAX_SIZE)

        self.anim = animate(current, target, 220, lambda v: self.body.setMaximumHeight(int(v)), done)


class Banner(qt.QFrame):
    """Status banner with a coloured rule and icon. `kind` drives the QSS palette."""

    def __init__(self, text="", kind="info"):
        qt.QFrame.__init__(self)
        self.setObjectName("BFBanner")
        # Deliberately not named "kind": a Python attribute sharing a name with the
        # Qt dynamic property below is shadowed by PythonQt (writes go to the
        # property, reads return the stale Python value).
        self.current_kind = None
        layout = qt.QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        self.mark = qt.QLabel()
        self.mark.setFixedSize(16, 16)
        self.mark.setAlignment(qt.Qt.AlignTop)
        layout.addWidget(self.mark, 0, qt.Qt.AlignTop)
        self.text_label = label(text, "BFBannerText", True)
        self.text_label.setMinimumHeight(18)
        layout.addWidget(self.text_label, 1)
        self.set_kind(kind)

    def set_kind(self, kind):
        if kind == self.current_kind:
            return
        self.current_kind = kind
        self.setProperty("kind", kind)
        self.mark.setPixmap(pixmap(KIND_ICONS.get(kind, "info"), KIND_COLORS.get(kind, "blue"), 16))
        restyle(self)
        restyle(self.text_label)

    def show_message(self, text, kind="info", animate_change=True):
        changed = text != self.text_label.text
        self.set_kind(kind)
        self.text_label.setText(text)
        if changed and animate_change and self.isVisible():
            fade_in(self, 260, 0.35)


class EmptyState(qt.QWidget):
    """Centered icon + title + hint for panels without content yet."""

    def __init__(self, icon_name, title, hint):
        qt.QWidget.__init__(self)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(6)
        layout.addStretch(1)
        self.mark = qt.QLabel()
        self.mark.setAlignment(qt.Qt.AlignCenter)
        self.mark.setPixmap(pixmap(icon_name, "muted", 44))
        layout.addWidget(self.mark)
        self.title = label(title, "BFEmptyTitle", True)
        self.title.setAlignment(qt.Qt.AlignCenter)
        layout.addWidget(self.title)
        self.hint = label(hint, "BFEmptyHint", True)
        self.hint.setAlignment(qt.Qt.AlignCenter)
        layout.addWidget(self.hint)
        layout.addStretch(1)

    def set_text(self, title, hint, icon_name=None):
        self.title.setText(title)
        self.hint.setText(hint)
        if icon_name:
            self.mark.setPixmap(pixmap(icon_name, "muted", 44))


class DirectionRose(Painted):
    """Axial compass for a branch's unit direction in LPS, plus a superior/inferior gauge.

    Radiological convention: the patient's left (LPS +x) is drawn on the right,
    posterior (LPS +y) at the bottom. Nothing is inferred beyond the vector itself.
    """

    def __init__(self):
        Painted.__init__(self)
        self.vector = None
        self.shown = None
        self.anim = None
        self.setFixedSize(132, 96)

    def set_direction(self, vector):
        target = tuple(float(v) for v in vector) if vector else None
        stop(self.anim)
        if target is None or self.shown is None:
            self.vector = self.shown = target
            self.update()
            return
        start = self.shown

        def tick(t):
            self.shown = tuple(s + (e - s) * t for s, e in zip(start, target))
            self.update()

        self.vector = target
        self.anim = animate(0.0, 1.0, 320, tick, lambda: tick(1.0))

    def paint(self, p):
        cx, cy, r = 46, 48, 38
        p.setPen(qt.QPen(color("line2"), 1))
        p.setBrush(qt.QBrush(color("surface")))
        p.drawEllipse(qt.QPointF(cx, cy), r, r)
        p.setPen(qt.QPen(color("line"), 1))
        p.drawEllipse(qt.QPointF(cx, cy), r * 0.5, r * 0.5)
        p.drawLine(qt.QPointF(cx - r, cy), qt.QPointF(cx + r, cy))
        p.drawLine(qt.QPointF(cx, cy - r), qt.QPointF(cx, cy + r))
        p.setFont(font(9, qt.QFont.Bold))
        p.setPen(qt.QPen(color("muted")))
        for text, rect in (("A", qt.QRectF(cx - 8, cy - r - 1, 16, 10)), ("P", qt.QRectF(cx - 8, cy + r - 9, 16, 10)), ("R", qt.QRectF(cx - r + 2, cy - 6, 12, 12)), ("L", qt.QRectF(cx + r - 13, cy - 6, 12, 12))):
            p.drawText(rect, qt.Qt.AlignCenter, text)
        # Superior / inferior gauge.
        gx, gy, gh = 112, 12, 72
        rounded(p, qt.QRectF(gx - 3, gy, 6, gh), 3, color("surface"), color("line2"))
        p.setFont(font(9, qt.QFont.Bold))
        p.setPen(qt.QPen(color("muted")))
        p.drawText(qt.QRectF(gx - 10, 0, 20, 11), qt.Qt.AlignCenter, "S")
        p.drawText(qt.QRectF(gx - 10, gy + gh + 1, 20, 11), qt.Qt.AlignCenter, "I")
        if not self.shown:
            return
        x, y, z = self.shown
        planar = math.hypot(x, y)
        end = qt.QPointF(cx + x * r * 0.92, cy + y * r * 0.92)
        pen = qt.QPen(color("mint"), 2.4)
        pen.setCapStyle(qt.Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(qt.QPointF(cx, cy), end)
        if planar > 1e-6:
            ux, uy = x / planar, y / planar
            head = qt.QPainterPath()
            head.moveTo(end)
            head.lineTo(qt.QPointF(end.x() - ux * 8 - uy * 4, end.y() - uy * 8 + ux * 4))
            head.lineTo(qt.QPointF(end.x() - ux * 8 + uy * 4, end.y() - uy * 8 - ux * 4))
            head.closeSubpath()
            p.fillPath(head, qt.QBrush(color("mint")))
        p.setPen(qt.Qt.NoPen)
        p.setBrush(qt.QBrush(color("amber")))
        p.drawEllipse(qt.QPointF(cx, cy), 3.2, 3.2)
        # Gauge marker: +z is superior, drawn upward.
        my = gy + gh / 2 - z * (gh / 2 - 4)
        p.setBrush(qt.QBrush(color("mint")))
        p.drawEllipse(qt.QPointF(gx, my), 5, 5)
        p.setPen(qt.QPen(color("mint", 120), 2))
        p.drawLine(qt.QPointF(gx, gy + gh / 2), qt.QPointF(gx, my))


class SliceHeader(Painted):
    """Compact replacement for Slicer's slice toolbar: orientation, live offset and a hint."""

    def __init__(self, title, tone):
        Painted.__init__(self)
        self.title = title
        self.tone = tone
        self.offset_text = ""
        self.setFixedHeight(26)
        self.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Fixed)

    def set_offset(self, letter, value):
        text = f"{letter} {value:+.1f} mm"
        if text != self.offset_text:
            self.offset_text = text
            self.update()

    def paint(self, p):
        w, h = self.width, self.height
        p.fillRect(qt.QRectF(0, 0, w, h), color("surface"))
        p.setPen(qt.QPen(color("line"), 1))
        p.drawLine(qt.QPointF(0, h - 0.5), qt.QPointF(w, h - 0.5))
        p.setPen(qt.Qt.NoPen)
        p.setBrush(qt.QBrush(color(self.tone)))
        p.drawEllipse(qt.QPointF(13, h / 2), 3.5, 3.5)
        p.setFont(font(10, qt.QFont.Bold, spacing=1.6))
        p.setPen(qt.QPen(color("text2")))
        p.drawText(qt.QRectF(24, 0, 120, h), qt.Qt.AlignVCenter | qt.Qt.AlignLeft, self.title.upper())
        p.setFont(font(10, qt.QFont.Normal, mono=True))
        p.setPen(qt.QPen(color("text")))
        p.drawText(qt.QRectF(w - 130, 0, 120, h), qt.Qt.AlignVCenter | qt.Qt.AlignRight, self.offset_text)
        if w > 300:
            p.setFont(font(10))
            p.setPen(qt.QPen(color("muted")))
            p.drawText(qt.QRectF(110, 0, w - 250, h), qt.Qt.AlignVCenter | qt.Qt.AlignLeft, "scroll to move through slices")


class Toast(Painted):
    """Transient notification that rises from the bottom of its parent and fades away."""

    def __init__(self, parent):
        Painted.__init__(self, parent)
        self.text = ""
        self.kind = "info"
        self.alpha = 0.0
        self.rise = 0.0
        self.anim = None
        self.timer = qt.QTimer()
        self.timer.setSingleShot(True)
        self.timer.connect("timeout()", self.dismiss)
        self.setAttribute(qt.Qt.WA_TransparentForMouseEvents)
        self.text_font = font(12, qt.QFont.DemiBold)
        self.hide()

    def _place(self):
        parent = self.parent()
        if not parent:
            return
        width = min(parent.width - 24, text_width(self.text_font, self.text) + 58)
        height = 40
        x = int((parent.width - width) / 2)
        # Drops in from just under the header, over the 3D view rather than the CT planes.
        y = int(16 - self.rise)
        self.setGeometry(x, y, int(width), height)

    def show_message(self, text, kind="info", duration=2600):
        self.text = text
        self.kind = kind
        stop(self.anim)
        self.timer.stop()
        self.rise = 16.0
        self._place()
        self.show()
        raise_widget(self)

        def tick(v):
            self.alpha = v
            self.rise = 16.0 * (1.0 - v)
            self._place()
            self.update()

        self.anim = animate(self.alpha, 1.0, 260, tick)
        self.timer.start(duration)

    def dismiss(self):
        stop(self.anim)

        def tick(v):
            self.alpha = v
            self.update()

        self.anim = animate(self.alpha, 0.0, 320, tick, self.hide, easing=qt.QEasingCurve.InQuad)

    def paint(self, p):
        if self.alpha <= 0.001:
            return
        p.setOpacity(self.alpha)
        w, h = self.width, self.height
        rounded(p, qt.QRectF(1.5, 3.5, w - 3, h - 3), 10, qt.QColor(0, 0, 0, 90))
        rounded(p, qt.QRectF(0.5, 0.5, w - 1, h - 3), 10, color("raised"), color("line2"))
        accent = KIND_COLORS.get(self.kind, "blue")
        p.setPen(qt.Qt.NoPen)
        p.setBrush(qt.QBrush(color(accent)))
        p.drawRoundedRect(qt.QRectF(0, 8, 3, h - 18), 1.5, 1.5)
        p.drawPixmap(14, int((h - 16) / 2) - 1, pixmap(KIND_ICONS.get(self.kind, "info"), accent, 16))
        p.setFont(self.text_font)
        p.setPen(qt.QPen(color("text")))
        p.drawText(qt.QRectF(38, 0, w - 46, h - 2), qt.Qt.AlignVCenter | qt.Qt.AlignLeft, self.text)


# --------------------------------------------------------------------------- 3D motion helpers

def fly_camera(view, focal, position, scale, duration=650):
    """Smoothly move a parallel-projection camera; the scene geometry is untouched."""
    renderer = view.renderWindow().GetRenderers().GetFirstRenderer()
    camera = renderer.GetActiveCamera()
    f0, p0, s0 = camera.GetFocalPoint(), camera.GetPosition(), camera.GetParallelScale()

    def tick(t):
        camera.SetFocalPoint(*[a + (b - a) * t for a, b in zip(f0, focal)])
        camera.SetPosition(*[a + (b - a) * t for a, b in zip(p0, position)])
        camera.SetParallelScale(s0 + (scale - s0) * t)
        renderer.ResetCameraClippingRange()
        view.scheduleRender()

    return animate(0.0, 1.0, duration, tick, lambda: tick(1.0), easing=qt.QEasingCurve.InOutCubic)


def pulse_opacity(display_nodes, duration=1100, floor=0.3):
    """Two soft pulses on the given display nodes, ending fully opaque."""
    nodes = [node for node in display_nodes if node is not None]

    def tick(t):
        value = 1.0 - (1.0 - floor) * abs(math.sin(2.0 * math.pi * t))
        for node in nodes:
            if node.GetScene():
                node.SetOpacity(value)

    return animate(0.0, 1.0, duration, tick, lambda: tick(1.0), easing=qt.QEasingCurve.Linear)


# --------------------------------------------------------------------------- JSON rich text

_TOKEN = re.compile(r'("(?:\\.|[^"\\])*")(\s*:)?|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false|null)\b|([{}\[\],])')


def json_html(text):
    """Colour a JSON string for a read-only QTextEdit without changing any characters."""
    out = []
    pos = 0
    for match in _TOKEN.finditer(text):
        out.append(html.escape(text[pos:match.start()]))
        pos = match.end()
        if match.group(1):
            if match.group(2):
                out.append(f'<span style="color:{T["mint"]}">{html.escape(match.group(1))}</span>{html.escape(match.group(2))}')
            else:
                out.append(f'<span style="color:{T["gold"]}">{html.escape(match.group(1))}</span>')
        elif match.group(3):
            out.append(f'<span style="color:{T["ivory"]}">{match.group(3)}</span>')
        elif match.group(4):
            out.append(f'<span style="color:{T["blue"]}">{match.group(4)}</span>')
        else:
            out.append(f'<span style="color:{T["muted"]}">{match.group(5)}</span>')
    out.append(html.escape(text[pos:]))
    return f'<pre style="font-family:\'{FONT_MONO}\'; font-size:11px; color:{T["text2"]}; margin:0;">{"".join(out)}</pre>'
