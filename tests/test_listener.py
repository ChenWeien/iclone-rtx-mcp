import gc
import importlib.util
import os
import sys
import time
import types
import unittest
from unittest import mock

try:
    from PySide2 import QtCore, QtNetwork
    import shiboken2
except ImportError:
    QtCore = None


@unittest.skipIf(QtCore is None, "Requires the application's PySide2 runtime")
class ListenerLifecycleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
        plugin_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "plugin"))
        sys.path.insert(0, plugin_dir)
        sys.modules.setdefault("RLPy", types.ModuleType("RLPy"))
        spec = importlib.util.spec_from_file_location("listener_plugin_test", os.path.join(plugin_dir, "main.py"))
        cls.plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.plugin)

    def setUp(self):
        self.listener = self.plugin.ICloneMcpListener()
        self.clients = []
        self.assertTrue(self.listener.start(0))

    def tearDown(self):
        if self.listener is not None:
            self.listener.stop()
            self.listener = None
        gc.collect()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        for client in self.clients:
            shiboken2.delete(client)

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            QtCore.QThread.msleep(1)
        self.assertTrue(predicate())

    def connect_client(self):
        count = len(self.listener._buffers)
        client = QtNetwork.QTcpSocket()
        self.clients.append(client)
        client.connectToHost("127.0.0.1", self.listener._server.serverPort())
        self.assertTrue(client.waitForConnected(2000))
        self.wait_for(lambda: len(self.listener._buffers) == count + 1)
        return client

    def test_connected_shutdown_drains_deferred_deletes(self):
        # A socket-capturing signal lambda crashed here during QObject destruction.
        for unused in range(20):
            self.connect_client()
            self.listener.stop()
            self.assertFalse(self.listener._buffers)
            self.listener = None
            gc.collect()
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
            self.listener = self.plugin.ICloneMcpListener()
            self.assertTrue(self.listener.start(0))

    def test_disconnect_removes_only_its_client(self):
        first = self.connect_client()
        second = self.connect_client()
        first.disconnectFromHost()
        self.wait_for(lambda: len(self.listener._buffers) == 1)
        second.disconnectFromHost()
        self.wait_for(lambda: not self.listener._buffers)

    def test_ready_read_dispatches_request_and_restart_accepts_clients(self):
        client = self.connect_client()
        with mock.patch.object(self.plugin.iclone_mcp_commands, "dispatch", return_value={"pong": True}) as dispatch:
            client.write(b'{"type":"ping","params":{}}\n')
            client.flush()
            self.wait_for(lambda: client.bytesAvailable() > 0)
            self.assertIn(b'"pong":true', bytes(client.readAll()))
            dispatch.assert_called_once_with("ping", {}, "127.0.0.1", 0)
        self.assertTrue(self.listener.start(0))
        self.assertFalse(self.listener._buffers)
        self.connect_client()


if __name__ == "__main__":
    result = unittest.main(argv=[__file__], exit=False).result
    if not result.wasSuccessful():
        raise RuntimeError("Listener lifecycle tests failed")
