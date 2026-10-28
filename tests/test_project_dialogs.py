"""Real Qt modal-loop + TCP regression, without loading or changing an AP scene.

Run separately from the fake-Qt unit tests, using a Python with PySide2 installed:
    QT_QPA_PLATFORM=offscreen python -m pytest tests/test_project_dialogs.py
"""
import asyncio
import importlib.util
import os
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

try:
    from PySide2 import QtCore, QtWidgets
except ImportError:
    QtCore = None


@unittest.skipIf(QtCore is None, "Requires a real PySide2 runtime; run separately")
class ModalProjectBridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        sys.path.insert(0, os.path.join(root, "plugin"))
        sys.path.insert(0, os.path.join(root, "server", "src"))
        sys.modules.setdefault("RLPy", types.ModuleType("RLPy"))
        spec = importlib.util.spec_from_file_location("modal_listener_test", os.path.join(root, "plugin", "main.py"))
        cls.plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.plugin)

    def check_modal_operation(self, operation, accept):
        from iclone_mcp.connection import ICloneConnection
        import iclone_mcp_tool_diagnostics as diagnostics
        import iclone_mcp_tool_project as project
        import iclone_mcp_tool_render as render

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = os.path.join(folder.name, "test.iProject")
        with open(path, "wb") as stream:
            stream.write(b"fixture")
        dialog_id = "qtRtxProjectLoadPreparationDialog" if operation == "load_project" else "qtRtxScenePreparationDialog"
        button_prefix = "qtRtxProjectLoadPreparation" if operation == "load_project" else "qtRtxScenePreparation"
        observed = []
        errors = []
        system = [11]
        dialogs = []
        finished = threading.Event()

        def native_operation(value):
            dialog = QtWidgets.QDialog()
            dialogs.append(dialog)
            dialog.setObjectName(dialog_id)
            dialog.setWindowTitle("Convert Project Data for RTX Render")
            layout = QtWidgets.QVBoxLayout(dialog)
            layout.addWidget(QtWidgets.QLabel("Prepare project data for RTX", dialog))
            for label, callback in (("OK", dialog.accept), ("Cancel", dialog.reject)):
                button = QtWidgets.QPushButton(label, dialog)
                button.setObjectName(button_prefix + ("OkButton" if label == "OK" else "CancelButton"))
                button.clicked.connect(callback)
                layout.addWidget(button)
            # A watchdog ensures a regression cannot strand the test in exec().
            watchdog = QtCore.QTimer(dialog)
            watchdog.setSingleShot(True)
            watchdog.timeout.connect(dialog.reject)
            watchdog.start(8000)
            accepted = dialog.exec_() == QtWidgets.QDialog.Accepted
            watchdog.stop()
            if operation == "render_system" and accepted:
                system[0] = value
            # Native RTX-load Cancel skips preparation, but still loads the project.
            return "success"

        rlpy = types.SimpleNamespace(
            RStatus=types.SimpleNamespace(Success="success"),
            RFileIO=types.SimpleNamespace(LoadProject=native_operation),
            ERenderSystem_DX11=11, ERenderSystem_DX12=12,
            RGlobal=types.SimpleNamespace(GetRenderSystem=lambda: system[0], SwitchRenderSystem=native_operation),
        )
        handlers = {"load_project": project.load_project,
                    "render_system": render.render_system,
                    "get_ui": diagnostics.get_ui,
                    "invoke_ui": diagnostics.invoke_ui}

        def dispatch(command, params, host, port):
            if command == "get_status":
                return {"protocol_version": 1}
            return handlers[command](params)

        listener = self.plugin.ICloneMcpListener()
        self.assertTrue(listener.start(0))
        port = listener._server.serverPort()

        async def scenario():
            connection = ICloneConnection(port=port)
            try:
                start = {"action": "start", "path": path} if operation == "load_project" else {"action": "start", "system": "dx12"}
                job = await connection.request(operation, start)
                job_args = {"action": "get", "job_id": job["job_id"]}
                for unused in range(100):
                    state = await connection.request(operation, job_args)
                    if state["state"] == "waiting_for_dialog":
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(state["state"], "waiting_for_dialog")
                self.assertFalse(state["cancellable"])
                self.assertIn(dialog_id, [dialog["dialog_id"] for dialog in state["dialogs"]])
                ui = await connection.request("get_ui", {"scope": "dialogs"})
                self.assertIn(dialog_id, [dialog["dialog_id"] for dialog in ui["dialogs"]])
                action_id = button_prefix + ("OkButton" if accept else "CancelButton")
                invoked = await connection.request("invoke_ui", {
                    "action": "invoke_dialog", "dialog_id": dialog_id, "action_id": action_id,
                })
                self.assertTrue(invoked["invoked"])
                self.assertFalse(invoked["dialog_visible"])
                for unused in range(100):
                    state = await connection.request(operation, job_args)
                    if state["state"] in ("completed", "cancelled", "failed"):
                        break
                    await asyncio.sleep(0.01)
                expected = "cancelled" if operation == "render_system" and not accept else "completed"
                self.assertEqual(state["state"], expected)
                self.assertEqual(state["completion"], expected == "completed")
                self.assertEqual(state["dialogs"], [])
                observed.append(state)
            finally:
                await connection.close()

        def worker():
            try:
                asyncio.run(asyncio.wait_for(scenario(), timeout=6))
            except BaseException as error:
                errors.append(error)
            finally:
                finished.set()

        replacements = (
            patch.object(project, "RLPy", rlpy),
            patch.object(project, "_LOAD_JOBS", {}),
            patch.object(render, "RLPy", rlpy),
            patch.object(render, "_TRANSITION_JOBS", {}),
            patch.object(render, "_restart_mcp_listener"),
            patch.object(self.plugin.iclone_mcp_commands, "dispatch", side_effect=dispatch),
        )
        for replacement in replacements:
            replacement.start()
        thread = threading.Thread(target=worker, daemon=True)
        try:
            thread.start()
            deadline = QtCore.QElapsedTimer()
            deadline.start()
            while not finished.is_set() and deadline.elapsed() < 10000:
                self.app.processEvents()
                QtCore.QThread.msleep(1)
        finally:
            for dialog in dialogs:
                dialog.reject()
            thread.join(timeout=1)
            listener.stop()
            for replacement in reversed(replacements):
                replacement.stop()
        self.assertTrue(finished.is_set(), "Bridge request did not complete")
        if errors:
            raise errors[0]
        self.assertEqual(len(observed), 1)

    def test_load_dialog_ok_over_same_connection(self):
        self.check_modal_operation("load_project", True)

    def test_load_dialog_cancel_over_same_connection(self):
        self.check_modal_operation("load_project", False)

    def test_render_dialog_ok_over_same_connection(self):
        self.check_modal_operation("render_system", True)

    def test_render_dialog_cancel_over_same_connection(self):
        self.check_modal_operation("render_system", False)


if __name__ == "__main__":
    unittest.main()
