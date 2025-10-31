#!/usr/bin/env python3
"""
Qt-only Screenshot Proof of Concept (PySide6)

No BS, here is what I'll do ...

- One Linux we will ask the desktop's screenshot portal via D-Bus. This is the most agnostic and 
  practical approach as it adheres to better security practices. The portal will then show us a 
  native UI to pick a region hopefully and give us a file uri in repsonse.

- On macOS/Windows just use Qt calls directly to capture the screen. If INTERACTIVE is True, we
  show a translucent Qt overlay for us to drag a box around the area to capture. I think that is 
  sufficient for now.

My technical understanding ...

- Linux uses org.freedesktop.portal.Screenshot via QtDBus. There's security practices that get 
  enforced w/ modern Linux Desktops now (e.g. Wayland) thus Portal/DBus is the preferred approach

- macOS/Windows use QScreen.grabWindow(0). The overlay avoids creating a new macOS "Space" that 
  would otherwise yield a black screen. What I have now I think will work around this weird issue
"""

import sys
import time
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtGui import QGuiApplication, QPainter
from PySide6.QtWidgets import QApplication, QWidget


# Sets up whether we capture automatically (i.e. whole screen) or not, and a path to save it
INTERACTIVE = True
OUTDIR = Path.home() / "Pictures"

# Some dumb helpers
def outpath() -> Path:
    """Generate ~/Pictures/screenshot-YYYYMMDD-HHMMSS.png"""
    OUTDIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return OUTDIR / f"screenshot-{stamp}.png"


def save(pm: QtGui.QPixmap) -> None:
    """Save QPixmap to disk and print the path"""
    p = outpath()
    pm.save(str(p))
    print(p)


# Qt overlay for macOS/Windows region selection
class RegionPicker(QWidget):
    """
    No BS explanation here is ...
      This will show me a semi-transparent overlay so we can drag/select our box. Then it emits
      that box.

    Technical understanding here is ...
      We create this "frameless stays-on-top window sized to scree" behavior. We dim the display
      and punch out the selected rectangle using transparent painting. Hoping this works.
    """
    picked = QtCore.Signal(QtCore.QRect)

    def __init__(self):
        super().__init__(
            None, QtCore.Qt.FramelessWindowHint | QtCore.Qt.Tool | QtCore.Qt.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setCursor(QtCore.Qt.CrossCursor)

        # Size overlay to current screen instead of using native fullscreen mode.
        scr = QGuiApplication.primaryScreen()
        geo = scr.geometry() if scr else QtCore.QRect(0, 0, 1920, 1080)
        self.setGeometry(geo)

        self._p0 = None
        self._p1 = None

    def _selection_rect(self) -> QtCore.QRect:
        if not self._p0 or not self._p1:
            return QtCore.QRect()
        return QtCore.QRect(self._p0, self._p1).normalized()

    def paintEvent(self, _):
        if not (self._p0 and self._p1):
            return
        painter = QPainter(self)
        # I think this is how I dim the entire screen
        painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 80))
        # Clear the selected region (e.g. "hole")
        r = self._selection_rect()
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.fillRect(r, QtCore.Qt.transparent)
        # Outline the box
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setPen(QtGui.QPen(QtCore.Qt.white, 2))
        painter.drawRect(r)

    def mousePressEvent(self, e: QtGui.QMouseEvent):
        if e.button() == QtCore.Qt.LeftButton:
            p = e.position().toPoint()
            self._p0 = self._p1 = p
            self.update()

    def mouseMoveEvent(self, e: QtGui.QMouseEvent):
        if self._p0:
            self._p1 = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent):
        if e.button() == QtCore.Qt.LeftButton and self._p0:
            self._p1 = e.position().toPoint()
            r = self._selection_rect()
            self.hide()
            self.picked.emit(r)
            self.close()


# Linux: use XDG Desktop Portal via QtDBus
def grab_linux_portal(app: QApplication) -> None:
    """
    No BS explanation is ...
      We ask the desktop's screenshot service (portal) to capture the screen for us. The portal
      shows its own permission and picker UI then.

    My technical understanding is ...
      This calls org.freedesktop.portal.Screenshot.Screenshot, then connects to the request object
      which is returned to us "org.freedesktop.protal.Request::Response signal to get the file uri
    """
    from PySide6.QtDBus import QDBusConnection, QDBusMessage

    BUS = "org.freedesktop.portal.Desktop"
    PATH = "/org/freedesktop/portal/desktop"
    IF_SCR = "org.freedesktop.portal.Screenshot"
    IF_REQ = "org.freedesktop.portal.Request"

    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        raise RuntimeError("No D-Bus session bus. Is xdg-desktop-portal running?")

    msg = QDBusMessage.createMethodCall(BUS, PATH, IF_SCR, "Screenshot")
    msg.setArguments(["", {"Interactive": bool(INTERACTIVE)}])

    rsp = bus.call(msg)
    args = rsp.arguments() if rsp else []
    if not args:
        raise RuntimeError("Portal call failed")
    req_path = args[0]

    @QtCore.Slot("u", "a{sv}")
    def on_resp(code, results):
        if code == 0:
            print(results.get("uri", ""))
        else:
            print(f"portal error {code}")
        app.quit()

    if not bus.connect(BUS, req_path, IF_REQ, "Response", on_resp):
        raise RuntimeError("Failed to connect portal Response signal")
    app.exec()


# macOS/Windows capture via Qt
def grab_qt_full() -> None:
    """
    Capture full primary screen. On macOS, Python itself needs Screen Recording permission in
    Settings. I noticed that it prompted me to do that. However, it didn't apply those seettings 
    until I explicitly closed my terminal and reopened it myself. Only then did the settings apply
    """
    scr = QGuiApplication.primaryScreen()
    if not scr:
        raise RuntimeError("No primary screen")
    pm = scr.grabWindow(0)
    if pm.isNull():
        raise RuntimeError("Grab failed (macOS: check Screen Recording permission)")
    save(pm)


def grab_qt_region(app: QApplication) -> None:
    """
    Show region picker, then crop and save the selection.
    """
    scr = QGuiApplication.primaryScreen()
    pm_full = scr.grabWindow(0)
    if pm_full.isNull():
        raise RuntimeError("Grab failed (macOS: check Screen Recording permission)")
    dpr = pm_full.devicePixelRatio()

    picker = RegionPicker()

    def on_pick(r: QtCore.QRect):
        if r.isEmpty():
            save(pm_full)
        else:
            crop = QtCore.QRect(
                int(r.x() * dpr), int(r.y() * dpr),
                int(r.width() * dpr), int(r.height() * dpr)
            )
            save(pm_full.copy(crop))
        app.quit()

    picker.picked.connect(on_pick)
    picker.show()
    app.exec()


def main():
    app = QApplication(sys.argv)

    if sys.platform.startswith("linux"):
        grab_linux_portal(app)
    elif sys.platform == "darwin":
        if INTERACTIVE:
            grab_qt_region(app)
        else:
            grab_qt_full()
    elif sys.platform.startswith("win"):
        if INTERACTIVE:
            grab_qt_region(app)
        else:
            grab_qt_full()
    else:
        raise NotImplementedError(f"Unsupported platform: {sys.platform}")


if __name__ == "__main__":
    main()

