import importlib
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


PLUGIN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "plugin"))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)
sys.modules.setdefault("RLPy", types.ModuleType("RLPy"))
project = importlib.import_module("iclone_mcp_tool_project")
render = importlib.import_module("iclone_mcp_tool_render")


class ProjectLoadTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = os.path.join(folder.name, "test.iProject")
        with open(self.path, "wb") as stream:
            stream.write(b"fixture")
        self.callbacks = []
        self.loads = []
        self.dialogs = []
        self.system = 11
        self.rlpy = types.SimpleNamespace(
            RStatus=types.SimpleNamespace(Success="success"),
            RFileIO=types.SimpleNamespace(LoadProject=self.load),
            ERenderSystem_DX11=11, ERenderSystem_DX12=12,
            RGlobal=types.SimpleNamespace(
                GetRenderSystem=lambda: self.system,
                SwitchRenderSystem=self.switch,
            ),
        )
        pyside = types.ModuleType("PySide2")
        pyside.QtCore = types.SimpleNamespace(QTimer=types.SimpleNamespace(
            singleShot=lambda delay, callback: self.callbacks.append(callback)))
        self.patches = [
            patch.dict(sys.modules, {"PySide2": pyside}),
            patch.object(project, "RLPy", self.rlpy),
            patch.object(project, "_LOAD_JOBS", {}),
            patch.object(render, "RLPy", self.rlpy),
            patch.object(render, "_TRANSITION_JOBS", {}),
            patch.object(render, "_transition_dialogs", lambda: list(self.dialogs)),
            patch.object(render, "_restart_mcp_listener"),
        ]
        for replacement in self.patches:
            replacement.start()
            self.addCleanup(replacement.stop)

    def load(self, path):
        self.loads.append(path)
        return "success"

    def switch(self, system):
        self.system = system
        return "success"

    def start(self):
        return project.load_project({"action": "start", "path": self.path})

    def test_start_returns_before_loading_and_get_reports_completion(self):
        job = self.start()
        self.assertEqual(job["state"], "queued")
        self.assertEqual(self.loads, [])
        self.callbacks.pop(0)()
        result = project.load_project({"action": "get", "job_id": job["job_id"]})
        self.assertEqual(result["state"], "completed")
        self.assertTrue(result["completion"])
        self.assertFalse(result["cancellable"])
        self.assertEqual(self.loads, [self.path])

    def test_queued_cancel_prevents_loading(self):
        job = self.start()
        result = project.load_project({"action": "cancel", "job_id": job["job_id"]})
        self.callbacks.pop(0)()
        self.assertEqual(result["state"], "cancelled")
        self.assertFalse(result["completion"])
        self.assertEqual(self.loads, [])

    def test_existing_dialog_defers_loading_until_dismissed(self):
        self.dialogs.append({"dialog_id": "save-prompt"})
        job = self.start()
        self.callbacks.pop(0)()
        self.assertEqual(self.loads, [])
        result = project.load_project({"action": "get", "job_id": job["job_id"]})
        self.assertEqual(result["state"], "waiting_for_dialog")
        self.assertTrue(result["cancellable"])
        self.dialogs.clear()
        self.callbacks.pop(0)()
        self.assertEqual(self.loads, [self.path])

    def test_nested_load_dialog_can_be_observed_without_claiming_cancellation(self):
        job = self.start()

        def modal_load(path):
            self.dialogs.append({"dialog_id": "qtRtxProjectLoadPreparationDialog"})
            result = project.load_project({"action": "get", "job_id": job["job_id"]})
            self.assertEqual(result["state"], "waiting_for_dialog")
            self.assertEqual(result["dialogs"], self.dialogs)
            self.assertFalse(result["cancellable"])
            with self.assertRaisesRegex(RuntimeError, "get_ui/invoke_ui"):
                project.load_project({"action": "cancel", "job_id": job["job_id"]})
            with self.assertRaisesRegex(RuntimeError, "already running"):
                render.start_render_system_transition({"system": "dx12"})
            self.dialogs.clear()
            return "success"

        self.rlpy.RFileIO.LoadProject = modal_load
        self.callbacks.pop(0)()
        result = project.load_project({"action": "get", "job_id": job["job_id"]})
        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["dialogs"], [])

    def test_native_failure_is_reported_without_retry(self):
        job = self.start()
        self.rlpy.RFileIO.LoadProject = lambda path: "failed"
        self.callbacks.pop(0)()
        result = project.load_project({"action": "get", "job_id": job["job_id"]})
        self.assertEqual(result["state"], "failed")
        self.assertFalse(result["completion"])
        self.assertIn("could not load", result["error"])
        self.assertEqual(self.callbacks, [])

    def test_overlapping_load_and_render_jobs_are_rejected(self):
        self.start()
        with self.assertRaisesRegex(RuntimeError, "already running"):
            self.start()
        with self.assertRaisesRegex(RuntimeError, "already running"):
            render.start_render_system_transition({"system": "dx12"})
        project._LOAD_JOBS.clear()
        render.start_render_system_transition({"system": "dx12"})
        with self.assertRaisesRegex(RuntimeError, "already running"):
            self.start()
        with self.assertRaisesRegex(RuntimeError, "already running"):
            render.set_render_system({"system": "dx11"})

    def test_timer_failure_never_falls_back_to_synchronous_load(self):
        with patch.object(sys.modules["PySide2"].QtCore.QTimer, "singleShot", side_effect=RuntimeError("timer unavailable")):
            with self.assertRaisesRegex(RuntimeError, "timer unavailable"):
                self.start()
            with self.assertRaisesRegex(RuntimeError, "timer unavailable"):
                render.start_render_system_transition({"system": "dx12"})
        self.assertFalse(project._project_load_is_active())
        self.assertFalse(render._render_system_transition_is_active())
        self.assertEqual(self.loads, [])
        self.assertEqual(self.system, 11)

    def test_path_only_call_keeps_synchronous_behavior(self):
        self.assertEqual(project.load_project({"path": self.path}), {"status": "ok", "path": self.path})
        self.assertEqual(self.loads, [self.path])
        self.assertEqual(self.callbacks, [])

    def test_bad_path_and_unknown_job_fail_before_scheduling(self):
        with self.assertRaises(ValueError):
            project.load_project({"action": "start"})
        with self.assertRaises(FileNotFoundError):
            project.load_project({"action": "start", "path": self.path + ".missing"})
        with self.assertRaises(ValueError):
            project.load_project({"action": "get", "job_id": "unknown"})
        self.assertEqual(self.callbacks, [])

    def test_render_dialog_cancel_does_not_report_completed_switch(self):
        job = render.start_render_system_transition({"system": "dx12"})

        def cancelled_switch(system):
            self.dialogs.append({"dialog_id": "qtRtxScenePreparationDialog"})
            result = render.get_render_system_transition({"job_id": job["job_id"]})
            self.assertEqual(result["state"], "waiting_for_dialog")
            self.assertFalse(result["cancellable"])
            with self.assertRaisesRegex(RuntimeError, "get_ui/invoke_ui"):
                render.cancel_render_system_transition({"job_id": job["job_id"]})
            self.dialogs.clear()
            return "success"

        self.rlpy.RGlobal.SwitchRenderSystem = cancelled_switch
        self.callbacks.pop(0)()
        result = render.get_render_system_transition({"job_id": job["job_id"]})
        self.assertEqual(result["state"], "cancelled")
        self.assertFalse(result["completion"])
        self.assertEqual(result["current_system"], "dx11")


class AtmosphereFileTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = os.path.join(folder.name, "test.iAtm")
        self.calls = []
        file_api = types.SimpleNamespace(SaveFile=self.save, LoadFile=self.load)
        module = types.ModuleType("RLPy2")
        module.File = types.SimpleNamespace(GetInterface=lambda: file_api)
        module.EFileType = types.SimpleNamespace(Atmosphere="atmosphere")
        module.RResult = types.SimpleNamespace(RL_OK="ok")
        self.patch = patch.dict(sys.modules, {"RLPy2": module})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def save(self, obj, path, file_type):
        self.calls.append(("save", obj, path, file_type))
        with open(path, "wb") as stream:
            stream.write(b"atmosphere")
        return "ok"

    def load(self, path, file_type):
        self.calls.append(("load", path, file_type))
        return "ok"

    def test_save_and_load_use_native_atmosphere_file_api(self):
        saved = project.atmosphere_file({"action": "save", "path": self.path})
        self.assertEqual(saved, {"status": "ok", "action": "save", "path": self.path, "size_bytes": 10})
        self.assertEqual(self.calls, [("save", None, self.path, "atmosphere")])

        loaded = project.atmosphere_file({"action": "load", "path": self.path})
        self.assertEqual(loaded, {"status": "ok", "action": "load", "path": self.path})
        self.assertEqual(self.calls[-1], ("load", self.path, "atmosphere"))

    def test_save_will_not_overwrite_or_accept_unknown_extensions(self):
        project.atmosphere_file({"action": "save", "path": self.path})
        with self.assertRaises(FileExistsError):
            project.atmosphere_file({"action": "save", "path": self.path})
        with self.assertRaisesRegex(ValueError, "extension"):
            project.atmosphere_file({"action": "save", "path": os.path.join(os.path.dirname(self.path), "test.txt")})

    def test_load_requires_an_existing_atmosphere_file(self):
        with self.assertRaises(FileNotFoundError):
            project.atmosphere_file({"action": "load", "path": self.path})

    def test_registers_atmosphere_file_as_an_mcp_tool(self):
        registry = {}
        project.register(registry)
        tool = registry["atmosphere_file"]
        self.assertTrue(tool["main_thread"])
        self.assertEqual(tool["inputSchema"]["required"], ["action", "path"])


if __name__ == "__main__":
    unittest.main()
