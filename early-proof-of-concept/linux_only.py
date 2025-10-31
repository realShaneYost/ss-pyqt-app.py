#!/usr/bin/env python3
from PySide6.QtCore import QObject, Slot
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
from PySide6.QtWidgets import QApplication

import sys


PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PTH = "/org/freedesktop/portal/desktop"
IFACES_SCR = "org.freedesktop.portal.Screenshot"
IFACES_RQS = "org.freedesktop.portal.Request"

app = QApplication(sys.argv)
bus = QDBusConnection.sessionBus()

# Kind of guessing we approach this like the following for calling the native screenshot
ifc = QDBusInterface(PORTAL_BUS, PORTAL_PTH, IFACES_SCR, bus)
msg = QDBusMessage.createMethodCall(PORTAL_BUS, PORTAL_PTH, IFACES_SCR, "Screenshot")

# We then set interactive mode if we want it but we might mode this out w/ auto capture option
msg.setArguments(["", {"Interactive": True}])
rsp = bus.call(msg)

# I'm not sure how we validate good response yet so just exit if we fail here?!
if not rsp.arguments():
  sys.exit(1)

# We should see a valid object path in the response that is our handle
pth = rsp.arguments()[0]
print(f"request object path: {pth}")

# Set up a callback
def on_response(response_code, results):
  print(f"portal responded code: {response_code}")
  uri = results.get("uri", "")
  print(f"screenshot file uri: {uri}")
  app.quit()

# Wire it up and wait for signal
bus.connect(PORTAL_BUS, pth, IFACES_RQS, "Response", on_response)
app.exec()

