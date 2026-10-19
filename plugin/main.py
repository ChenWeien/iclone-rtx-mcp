from __future__ import print_function

rl_plugin_info = {"ap": "Any", "ap_version": "8.0"}

import ctypes
import os
import sys
import traceback

sys.dont_write_bytecode = True

import json
import PySide2
import RLPy
from PySide2 import QtCore, QtNetwork, QtWidgets
from shiboken2 import wrapInstance

import iclone_mcp_commands
from iclone_mcp_protocol import (
    FrameTooLarge,
    InvalidRequest,
    NdjsonBuffer,
    decode_request,
)


LISTENER_HOST = "127.0.0.1"


def _host_process_name():
    if os.name != "nt":
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(260)
        length = ctypes.windll.kernel32.GetModuleFileNameW(None, buffer, len(buffer))
        if length:
            return os.path.basename(buffer.value)
    except (AttributeError, OSError):
        pass
    return ""


HOST_PROCESS_NAME = _host_process_name()
IS_CHARACTER_CREATOR = HOST_PROCESS_NAME.lower() == "charactercreator.exe"
APPLICATION_NAME = "Character Creator" if IS_CHARACTER_CREATOR else "iClone"
SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ICMCP.ini")
DEFAULT_PORT = 9881 if IS_CHARACTER_CREATOR else 9880

_plugin = None


class ICloneMcpListener(QtCore.QObject):
    def __init__(self, parent=None):
        QtCore.QObject.__init__(self, parent)
        self._server = QtNetwork.QTcpServer(self)
        self._server.newConnection.connect(self._accept_connections)
        self._buffers = {}
        self._port = DEFAULT_PORT

    @property
    def port(self):
        return self._port

    def is_listening(self):
        return self._server.isListening()

    def error_string(self):
        return self._server.errorString()

    def start(self, port):
        self.stop()
        self._port = int(port)
        address = QtNetwork.QHostAddress(LISTENER_HOST)
        listening = self._server.listen(address, self._port)
        if listening:
            print(
                "[{0} MCP] Listening on {1}:{2}".format(
                    APPLICATION_NAME, LISTENER_HOST, self._port
                )
            )
        else:
            print(
                "[{0} MCP] Listener failed on {1}:{2}: {3}".format(
                    APPLICATION_NAME,
                    LISTENER_HOST,
                    self._port,
                    self._server.errorString(),
                ),
                file=sys.stderr,
            )
        return listening

    def stop(self):
        if self._server.isListening():
            self._server.close()
        for socket in list(self._buffers):
            socket.disconnectFromHost()
        self._buffers.clear()

    @QtCore.Slot()
    def _accept_connections(self):
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            self._buffers[socket] = NdjsonBuffer()
            socket.readyRead.connect(self._read)
            socket.disconnected.connect(self._discard)

    @QtCore.Slot()
    def _discard(self):
        socket = self.sender()
        self._buffers.pop(socket, None)
        socket.deleteLater()

    def _send(self, socket, response):
        try:
            encoded = (
                json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode(
                    "utf-8"
                )
                + b"\n"
            )
            socket.write(encoded)
            socket.flush()
        except (TypeError, ValueError):
            socket.write(b'{"status":"error","message":"Response is not JSON serializable."}\n')
            socket.flush()

    @QtCore.Slot()
    def _read(self):
        socket = self.sender()
        frame_buffer = self._buffers.get(socket)
        if frame_buffer is None:
            return

        try:
            frames = frame_buffer.feed(bytes(socket.readAll()))
        except FrameTooLarge as error:
            self._send(socket, {"status": "error", "message": str(error)})
            socket.disconnectFromHost()
            return

        for frame in frames:
            QtCore.QTimer.singleShot(
                0,
                lambda pending_frame=frame, connected_socket=socket: self._handle_frame(
                    connected_socket, pending_frame
                ),
            )

    def _handle_frame(self, socket, frame):
        if socket not in self._buffers:
            return
        try:
            request = decode_request(frame)
            result = iclone_mcp_commands.dispatch(
                request.get("type"),
                request.get("params", {}),
                LISTENER_HOST,
                self._port,
            )
            response = {"status": "success", "result": result}
        except (InvalidRequest, iclone_mcp_commands.CommandError) as error:
            response = {"status": "error", "message": str(error)}
        except Exception:
            traceback.print_exc(file=sys.stderr)
            response = {
                "status": "error",
                "message": "Unexpected iClone host error. See the iClone Python log.",
            }
        self._send(socket, response)


class ICloneMcpPlugin(object):
    def __init__(self):
        self._settings = QtCore.QSettings(SETTINGS_PATH, QtCore.QSettings.IniFormat)
        self._listener = ICloneMcpListener()
        self._menu = None
        self._enable_action = None
        self._status_action = None
        self._port_action = None

    def initialize(self):
        iclone_mcp_commands.start_initialization_grace()
        self._create_menu()
        self._start(show_error=False)
        QtCore.QTimer.singleShot(90000, lambda: self._start(show_error=False) if not self._listener.is_listening() else None)

    def close(self):
        self._listener.stop()
        self._update_menu()

    def _configured_port(self):
        value = self._settings.value("listener_port", DEFAULT_PORT)
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = DEFAULT_PORT
        return value if 1024 <= value <= 65535 else DEFAULT_PORT

    def _create_menu(self):
        menu_pointer = RLPy.RUi.AddMenu(
            "{0} MCP".format(APPLICATION_NAME), RLPy.EMenu_Plugins
        )
        self._menu = wrapInstance(int(menu_pointer), QtWidgets.QMenu)

        self._enable_action = self._menu.addAction("Enable Listener")
        self._enable_action.setCheckable(True)
        self._enable_action.triggered.connect(self._toggle_listener)

        self._status_action = self._menu.addAction("Status: Stopped")
        self._status_action.setEnabled(False)

        self._menu.addSeparator()
        self._port_action = self._menu.addAction("Set Port...")
        self._port_action.triggered.connect(self._set_port)

        restart_action = self._menu.addAction("Restart Listener")
        restart_action.triggered.connect(self._restart)
        self._update_menu()

    def _update_menu(self):
        if self._enable_action is None:
            return
        listening = self._listener.is_listening()
        self._enable_action.blockSignals(True)
        self._enable_action.setChecked(listening)
        self._enable_action.blockSignals(False)
        if listening:
            text = "Status: Listening on {0}:{1}".format(
                LISTENER_HOST, self._listener.port
            )
        else:
            text = "Status: Stopped"
        self._status_action.setText(text)
        self._port_action.setText("Set Port... (current: {0})".format(self._configured_port()))

    def _start(self, show_error):
        if not self._listener.start(self._configured_port()) and show_error:
            QtWidgets.QMessageBox.warning(
                None,
                "{0} MCP".format(APPLICATION_NAME),
                "Could not start the loopback listener:\n{0}".format(
                    self._listener.error_string()
                ),
            )
        self._update_menu()

    @QtCore.Slot(bool)
    def _toggle_listener(self, enabled):
        if enabled:
            self._start(show_error=True)
        else:
            self._listener.stop()
            self._update_menu()

    @QtCore.Slot()
    def _restart(self):
        self._start(show_error=True)

    @QtCore.Slot()
    def _set_port(self):
        port, accepted = QtWidgets.QInputDialog.getInt(
            None,
            "{0} MCP".format(APPLICATION_NAME),
            "Loopback port:",
            self._configured_port(),
            1024,
            65535,
            1,
        )
        if not accepted:
            return
        self._settings.setValue("listener_port", port)
        self._start(show_error=True)


def initialize_plugin():
    global _plugin
    if _plugin is None:
        _plugin = ICloneMcpPlugin()
        _plugin.initialize()


def uninitialize_plugin():
    global _plugin
    if _plugin is not None:
        _plugin.close()
        _plugin = None


def run_script():
    if _plugin is None:
        initialize_plugin()
