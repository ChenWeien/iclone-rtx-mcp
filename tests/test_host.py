import math
import os
import sys
import tempfile
import types
import unittest


PLUGIN_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "plugin")
)
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

sys.modules.setdefault("RLPy", types.ModuleType("RLPy"))

import iclone_mcp_commands as commands
REAL_DELETE_WITH_UNDO = commands._delete_with_undo
from iclone_mcp_protocol import (
    FrameTooLarge,
    InvalidRequest,
    NdjsonBuffer,
    decode_request,
)


class Vector3(object):
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x = x
        self.y = y
        self.z = z


class Matrix3(object):
    def __init__(self, euler=None):
        self.euler = list(euler or (0.0, 0.0, 0.0))

    def ToEulerAngle(self, unused_order, unused_x, unused_y, unused_z):
        return list(self.euler)

    @staticmethod
    def FromEulerAngle(unused_order, x, y, z):
        return [Matrix3((x, y, z))]


class Quaternion(object):
    def __init__(self, source=None):
        self.euler = list(source.euler) if isinstance(source, Quaternion) else [0.0] * 3

    def ToRotationMatrix(self):
        return Matrix3(self.euler)

    def FromRotationMatrix(self, matrix):
        self.euler = list(matrix.euler)


class Transform(object):
    def __init__(self, source=None):
        if isinstance(source, Transform):
            self._translation = Vector3(
                source.T().x, source.T().y, source.T().z
            )
            self._rotation = Quaternion(source.R())
            self._scale = Vector3(source.S().x, source.S().y, source.S().z)
        else:
            self._translation = Vector3()
            self._rotation = Quaternion()
            self._scale = Vector3(1.0, 1.0, 1.0)

    def T(self):
        return self._translation

    def R(self):
        return self._rotation

    def S(self):
        return self._scale


class Time(object):
    def __init__(self, value=0):
        self.value = value

    def ToInt64(self):
        return self.value

    @staticmethod
    def FromValue(value):
        return Time(value)


class Fps(object):
    def ToFloat(self):
        return 60.0

    def IndexedFrameTime(self, frame):
        return Time(frame * 10)


class TransformControl(object):
    def __init__(self, owner):
        self.owner = owner
        self.values = {}

    def GetValue(self, time_value, output):
        source = self.values.get(time_value.value, self.owner.local_transform)
        copied = Transform(source)
        output._translation = copied.T()
        output._rotation = copied.R()
        output._scale = copied.S()
        return "success"

    def SetValue(self, time_value, value):
        copied = Transform(value)
        self.values[time_value.value] = copied
        if time_value.value == FakeGlobal.current_time.value:
            self.owner.local_transform = copied
            self.owner.world_transform = Transform(copied)
        return "success"


class SceneObject(object):
    def __init__(self, object_id, name, object_type=1):
        self.object_id = object_id
        self.name = name
        self.object_type = object_type
        self.local_transform = Transform()
        self.world_transform = Transform()
        self.control = TransformControl(self)

    def GetID(self):
        return self.object_id

    def GetName(self):
        return self.name

    def GetType(self):
        return self.object_type

    def SetName(self, name):
        self.name = name
        return "success"

    def GetControl(self, name):
        return self.control if name == "Transform" else None

    def LocalTransform(self):
        return self.local_transform

    def WorldTransform(self):
        return self.world_transform

    def GetBounds(self, max_point, center_point, min_point):
        max_point.x = max_point.y = max_point.z = 10.0
        center_point.x = center_point.y = center_point.z = 5.0
        min_point.x = min_point.y = min_point.z = 0.0
        return "success"


class FakeScene(object):
    objects = []
    selected = []

    @classmethod
    def FindObjects(cls, mask):
        return [scene_object for scene_object in cls.objects if scene_object.GetType() & mask]

    @classmethod
    def GetSelectedObjects(cls):
        return list(cls.selected)

    @classmethod
    def GetCurrentCamera(cls):
        return None

    @classmethod
    def FindObject(cls, object_type, name):
        for scene_object in cls.objects:
            if scene_object.GetType() == object_type and scene_object.GetName() == name:
                return scene_object
        return None

    @classmethod
    def QueryObjectByID(cls, object_id):
        for scene_object in cls.objects:
            if scene_object.GetID() == object_id:
                return scene_object
        return None

    @classmethod
    def SelectObjects(cls, objects):
        cls.selected = list(objects)
        return "success"

    @classmethod
    def SelectObject(cls, scene_object):
        cls.selected = [scene_object]
        return "success"

    @classmethod
    def ClearSelectObjects(cls):
        cls.selected = []
        return "success"

    @classmethod
    def RemoveObject(cls, scene_object):
        cls.objects.remove(scene_object)
        cls.selected = [obj for obj in cls.selected if obj is not scene_object]
        return "success"


class FakeGlobal(object):
    current_time = Time(100)
    actions = []
    render_calls = []
    undo_count = 0
    redo_count = 0

    @classmethod
    def GetTime(cls):
        return cls.current_time

    @staticmethod
    def GetStartTime():
        return Time(0)

    @staticmethod
    def GetEndTime():
        return Time(5000)

    @staticmethod
    def GetFps():
        return Fps()

    @classmethod
    def BeginAction(cls, name):
        cls.actions.append(("begin", name))

    @classmethod
    def EndAction(cls):
        cls.actions.append(("end", None))

    @classmethod
    def Undo(cls):
        cls.undo_count += 1

    @classmethod
    def Redo(cls):
        cls.redo_count += 1

    @classmethod
    def RenderVideo(cls, *args):
        cls.render_calls.append(args)
        return "success"

    @staticmethod
    def RenderPreview(path):
        with open(path, "wb") as output:
            output.write(b"\x89PNG\r\n\x1a\n")
        return "success"


class FakeOpenSystem(object):
    @staticmethod
    def GetInterface():
        return FakeOpenSystem()

    @staticmethod
    def ToHandle(object_id):
        return object_id


class FakeOpenEdit(object):
    calls = []

    @staticmethod
    def GetInterface():
        return FakeOpenEdit()

    def DeleteSceneObjects(self, handles, record_undo=True, object_in_scene=True):
        if type(handles) is list:
            raise TypeError("DeleteSceneObjects requires RArrayListHandle")
        FakeOpenEdit.calls.append((list(handles), record_undo, object_in_scene))
        for object_id in handles:
            FakeScene.RemoveObject(FakeScene.QueryObjectByID(object_id))
        return "success"


def fake_rlopen():
    class HandleList(list):
        def Add(self, handle):
            self.append(handle)
            return True

    return types.SimpleNamespace(
        System=FakeOpenSystem, Edit=FakeOpenEdit, RArrayListHandle=HandleList
    )


class FakeFileIO(object):
    @staticmethod
    def LoadObject(path, unused_record_step):
        object_type = (
            commands.RLPy.EObjectType_LensFlare
            if path.lower().endswith(".ilflare")
            else commands.RLPy.EObjectType_Prop
        )
        scene_object = SceneObject(
            "imported", "Imported", object_type
        )
        FakeScene.objects.append(scene_object)
        FakeScene.selected = [scene_object]
        return scene_object


class FakeApplication(object):
    @staticmethod
    def GetProductName():
        return "iClone"

    @staticmethod
    def GetProductVersion():
        return (8, 8, 0)


def fake_rlpy():
    module = types.SimpleNamespace(
        RStatus=types.SimpleNamespace(Success="success"),
        RVector3=Vector3,
        RMatrix3=Matrix3,
        RTransform=Transform,
        RTime=Time,
        RScene=FakeScene,
        RGlobal=FakeGlobal,
        RFileIO=FakeFileIO,
        RApplication=FakeApplication,
        EEulerOrder_XYZ=0,
        EObjectType_Object=1 << 20,
    )
    for index, constant_name in enumerate(
        name for unused_label, name in commands._TYPE_CONSTANTS
    ):
        setattr(module, constant_name, 1 << index)
    return module


class ProtocolTests(unittest.TestCase):
    def test_partial_and_multiple_frames(self):
        buffer = NdjsonBuffer()
        self.assertEqual(buffer.feed(b'{"type":"a"'), [])
        self.assertEqual(
            buffer.feed(b"}\n{}\r\n"),
            [b'{"type":"a"}', b"{}"],
        )

    def test_oversized_frame(self):
        buffer = NdjsonBuffer(max_frame_size=4)
        with self.assertRaises(FrameTooLarge):
            buffer.feed(b"12345")

    def test_invalid_json_and_request_fields(self):
        with self.assertRaises(InvalidRequest):
            decode_request(b"{not-json}")
        with self.assertRaises(InvalidRequest):
            decode_request(b'{"type":"undo","extra":true}')
        self.assertEqual(
            decode_request(b'{"type":"undo","params":{}}'),
            {"type": "undo", "params": {}},
        )


class CommandTests(unittest.TestCase):
    def setUp(self):
        commands.RLPy = fake_rlpy()
        FakeOpenEdit.calls = []
        self.previous_rlopen = sys.modules.get("RLPy2")
        sys.modules["RLPy2"] = fake_rlopen()
        commands._UPSTREAM_TOOL_REGISTRY = None
        commands._ready_at = 0.0
        commands._delete_with_undo = REAL_DELETE_WITH_UNDO
        first = SceneObject("one", "First", commands.RLPy.EObjectType_Avatar)
        second = SceneObject("two", "Second", commands.RLPy.EObjectType_Prop)
        FakeScene.objects = [first, second]
        FakeScene.selected = [first]
        FakeGlobal.current_time = Time(100)
        FakeGlobal.actions = []
        FakeGlobal.render_calls = []
        FakeGlobal.undo_count = 0
        FakeGlobal.redo_count = 0

    def tearDown(self):
        if self.previous_rlopen is None:
            sys.modules.pop("RLPy2", None)
        else:
            sys.modules["RLPy2"] = self.previous_rlopen

    def test_scene_and_object_info(self):
        scene = commands.dispatch("get_scene_info", {"limit": 1}, "127.0.0.1", 9880)
        self.assertEqual(scene["object_count"], 2)
        self.assertEqual(scene["selected_object_ids"], ["one"])
        self.assertTrue(scene["truncated"])

        info = commands.dispatch(
            "get_object_info", {"object_id": "one"}, "127.0.0.1", 9880
        )
        self.assertEqual(info["name"], "First")
        self.assertTrue(info["selected"])
        self.assertEqual(info["world_bounds"]["max_cm"], [10.0, 10.0, 10.0])

    def test_set_transform_uses_one_key_and_action(self):
        result = commands.dispatch(
            "set_transform",
            {
                "object_id": "one",
                "position_cm": [1, 2, 3],
                "rotation_deg_xyz": [90, 0, -90],
                "scale_xyz": [2, 2, 2],
                "time_ms": 100,
            },
            "127.0.0.1",
            9880,
        )
        keyed = result["keyed_local_transform"]
        self.assertEqual(keyed["position_cm"], [1.0, 2.0, 3.0])
        self.assertAlmostEqual(
            FakeScene.objects[0].control.values[100].R().euler[0],
            math.pi / 2,
        )
        self.assertEqual(
            FakeGlobal.actions,
            [("begin", "MCP Set Transform"), ("end", None)],
        )

    def test_set_transform_accepts_upstream_name_vectors_and_frames(self):
        result = commands.dispatch(
            "set_transform",
            {
                "name": "First",
                "position": {"x": 7},
                "frame": 3,
            },
            "127.0.0.1",
            9880,
        )
        self.assertEqual(result["keyed_time_ms"], 30)
        self.assertEqual(result["keyed_local_transform"]["position_cm"], [7.0, 0.0, 0.0])
        self.assertEqual(FakeScene.objects[0].control.values[30].T().x, 7.0)

    def test_upstream_registry_keeps_catalog_and_safe_delete(self):
        registry = commands._load_upstream_tools()
        self.assertIn("create_primitive", registry)
        self.assertIn("get_materials", registry)
        self.assertIn("ping_iclone", registry)
        self.assertIn("run_python_file", registry)
        self.assertIn("material_texture", registry)
        self.assertTrue(registry["material_texture"].get("advertise", True))
        self.assertIn("reproduce_walkway_path_gizmo", registry)
        self.assertFalse(registry["set_path_width"].get("advertise", True))
        self.assertFalse(registry["select_path_control_point"].get("advertise", True))
        self.assertFalse(registry["remove_material_texture"].get("advertise", True))
        self.assertFalse(registry["ping_iclone"].get("advertise", True))
        advertised = commands.advertised_tool_names(registry)
        self.assertGreaterEqual(len(advertised), 65)
        self.assertLessEqual(len(advertised), 85)
        self.assertIn("material_texture", advertised)
        self.assertNotIn("remove_material_texture", advertised)
        result = registry["delete_object"]["handler"]({"name": "First"})
        self.assertEqual(result["deleted_objects"][0]["name"], "First")
        self.assertEqual(FakeOpenEdit.calls, [(["one"], True, True)])

        self.assertEqual(
            commands.dispatch("ping_iclone", {}, "127.0.0.1", 9880),
            {"status": "ok"},
        )
        self.assertIn("remove_material_texture", registry)
        self.assertIn("export_obj", registry)
        self.assertFalse(registry["export_obj"].get("advertise", True))
        self.assertIn("export_object", advertised)

    def test_optional_export_api_returns_structured_command_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(commands.CommandError, "ExportObjFile"):
                commands.dispatch(
                    "export_obj",
                    {"name": "First", "path": os.path.join(directory, "out.obj")},
                    "127.0.0.1",
                    9880,
                )

    def test_upstream_required_parameters_are_validated(self):
        with self.assertRaisesRegex(commands.CommandError, "path"):
            commands.dispatch("export_obj", {}, "127.0.0.1", 9880)

    def test_render_requires_confirmation(self):
        with self.assertRaisesRegex(commands.CommandError, "RENDER_VIDEO_WITH_CURRENT_SETTINGS"):
            commands.dispatch(
                "render_video",
                {"confirm": "no"},
                "127.0.0.1",
                9880,
            )

    def test_run_python_file_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "script.py")
            with open(path, "w") as script:
                script.write("pass\n")
            with self.assertRaisesRegex(commands.CommandError, "RUN_PYTHON_FILE"):
                commands.dispatch(
                    "run_python_file",
                    {"path": path, "confirm": "no"},
                    "127.0.0.1",
                    9880,
                )

    def test_run_python_file_executes_absolute_python_file(self):
        with tempfile.TemporaryDirectory() as directory:
            script_path = os.path.join(directory, "script.py")
            marker_path = os.path.join(directory, "ran.txt")
            with open(script_path, "w") as script:
                script.write("open({0!r}, 'w').write('ran')\n".format(marker_path))

            result = commands.dispatch(
                "run_python_file",
                {"path": script_path, "confirm": "RUN_PYTHON_FILE"},
                "127.0.0.1",
                9880,
            )

            self.assertEqual(result, {"status": "completed", "path": os.path.normpath(script_path)})
            with open(marker_path) as marker:
                self.assertEqual(marker.read(), "ran")

    def test_run_python_file_rejects_non_python_or_missing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = (
                os.path.join(directory, "script.txt"),
                os.path.join(directory, "missing.py"),
            )
            with open(paths[0], "w") as script:
                script.write("pass\n")
            for path in paths:
                with self.subTest(path=path):
                    with self.assertRaisesRegex(commands.CommandError, "path|Python file"):
                        commands.dispatch(
                            "run_python_file",
                            {"path": path, "confirm": "RUN_PYTHON_FILE"},
                            "127.0.0.1",
                            9880,
                        )

    def test_render_uses_current_settings_without_output_path(self):
        result = commands.dispatch(
            "render_video",
            {"confirm": "RENDER_VIDEO_WITH_CURRENT_SETTINGS"},
            "127.0.0.1",
            9880,
        )
        self.assertEqual(result["status"], "started")
        self.assertEqual(
            [tuple(item.value for item in call) for call in FakeGlobal.render_calls],
            [(0, 5000)],
        )

    def test_render_forwards_absolute_output_path(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = os.path.join(directory, "render.mp4")
            result = commands.dispatch(
                "render_video",
                {
                    "confirm": "RENDER_VIDEO_WITH_CURRENT_SETTINGS",
                    "output_path": output_path,
                },
                "127.0.0.1",
                9880,
            )
        self.assertEqual(result["output_path"], os.path.normpath(output_path))
        call = FakeGlobal.render_calls[0]
        self.assertEqual(
            (call[0].value, call[1].value, call[2]),
            (0, 5000, os.path.normpath(output_path)),
        )

    def test_render_rejects_invalid_output_path_before_rendering(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = (
                "render.mp4",
                os.path.join(directory, "missing", "render.mp4"),
            )
            for output_path in paths:
                with self.subTest(output_path=output_path):
                    with self.assertRaisesRegex(commands.CommandError, "output_path"):
                        commands.dispatch(
                            "render_video",
                            {
                                "confirm": "RENDER_VIDEO_WITH_CURRENT_SETTINGS",
                                "output_path": output_path,
                            },
                            "127.0.0.1",
                            9880,
                        )
        self.assertEqual(FakeGlobal.render_calls, [])

    def test_selection_prevalidates_and_delete_deduplicates(self):
        with self.assertRaises(commands.CommandError):
            commands.dispatch(
                "select_objects",
                {"object_ids": ["missing"]},
                "127.0.0.1",
                9880,
            )
        self.assertEqual([obj.GetID() for obj in FakeScene.selected], ["one"])

        commands._delete_with_undo = lambda objects: [
            FakeScene.RemoveObject(scene_object) for scene_object in objects
        ]
        try:
            result = commands.dispatch(
                "delete_objects",
                {"object_ids": ["two", "two"]},
                "127.0.0.1",
                9880,
            )
        finally:
            commands._delete_with_undo = REAL_DELETE_WITH_UNDO
        self.assertEqual([item["id"] for item in result["deleted_objects"]], ["two"])
        self.assertEqual([obj.GetID() for obj in FakeScene.objects], ["one"])

    def test_import_detects_new_object_and_renames_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "asset.iprop")
            with open(path, "wb") as asset:
                asset.write(b"test")
            result = commands.dispatch(
                "import_asset",
                {"path": path, "name": "MCP Prop"},
                "127.0.0.1",
                9880,
            )
        self.assertEqual(
            result["imported_objects"],
            [{"id": "imported", "name": "MCP Prop", "type": "Prop"}],
        )

    def test_import_discovers_lens_flare_and_name_based_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "Sunlight.iLflare")
            with open(path, "wb") as asset:
                asset.write(b"test")
            result = commands.dispatch(
                "import_asset",
                {"path": path},
                "127.0.0.1",
                9880,
            )

        self.assertEqual(
            result["imported_objects"],
            [{"id": "imported", "name": "Imported", "type": "LensFlare"}],
        )
        scene = commands.dispatch("get_scene_info", {}, "127.0.0.1", 9880)
        self.assertIn("imported", [item["id"] for item in scene["objects"]])
        typed = commands.dispatch(
            "list_objects", {"type": "lens_flare"}, "127.0.0.1", 9880
        )
        self.assertEqual([item["id"] for item in typed["objects"]], ["imported"])
        all_objects = commands.dispatch(
            "list_objects", {}, "127.0.0.1", 9880
        )
        self.assertIn("imported", [item["id"] for item in all_objects["objects"]])
        commands.dispatch(
            "select_object", {"name": "Imported"}, "127.0.0.1", 9880
        )
        transform = commands.dispatch(
            "get_transform", {"name": "Imported"}, "127.0.0.1", 9880
        )
        self.assertEqual(transform["name"], "Imported")

    def test_validation_and_undo_redo(self):
        with self.assertRaises(commands.CommandError):
            commands.dispatch(
                "get_scene_info", {"limit": 0}, "127.0.0.1", 9880
            )
        with self.assertRaises(commands.CommandError):
            commands.dispatch(
                "set_transform",
                {"object_id": "one", "position_cm": [1, float("nan"), 3]},
                "127.0.0.1",
                9880,
            )
        commands.dispatch("undo", {}, "127.0.0.1", 9880)
        commands.dispatch("redo", {}, "127.0.0.1", 9880)
        self.assertEqual((FakeGlobal.undo_count, FakeGlobal.redo_count), (1, 1))
        commands.dispatch(
            "delete_objects",
            {"object_ids": ["two"]},
            "127.0.0.1",
            9880,
        )
        self.assertEqual(FakeOpenEdit.calls, [(["two"], True, True)])

    def test_initialization_grace_allows_status_only(self):
        commands._ready_at = commands.time.monotonic() + 100.0
        status = commands.dispatch("get_status", {}, "127.0.0.1", 9880)
        self.assertEqual(status["application_pid"], commands.os.getpid())
        self.assertFalse(status["ready"])
        with self.assertRaises(commands.CommandError):
            commands.dispatch(
                "get_scene_info", {"limit": 1}, "127.0.0.1", 9880
            )


if __name__ == "__main__":
    unittest.main()
