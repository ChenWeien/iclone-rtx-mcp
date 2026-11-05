import os
import sys
import types


PLUGIN_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "plugin")
)
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

fake_rlpy = types.ModuleType("RLPy")
fake_rlpy.EObjectType_Prop = object()
fake_rlpy.EObjectType_Avatar = object()
fake_rlpy.EObjectType_Camera = object()
fake_rlpy.EObjectType_Particle = object()
fake_rlpy.EObjectType_Light = object()
fake_rlpy.EObjectType_SpotLight = object()
fake_rlpy.EObjectType_PointLight = object()
fake_rlpy.EObjectType_DirectionalLight = object()
fake_rlpy.RScene = types.SimpleNamespace()
sys.modules["RLPy"] = fake_rlpy

import iclone_mcp_tool_camera as camera


def test_create_camera_has_no_user_arguments():
    assert camera.create_camera.__name__ == "create_camera"


def test_create_camera_uses_native_edit_api_without_selecting_it():
    original_rlpy = camera.RLPy
    original_rpy2 = sys.modules.get("RLPy2")
    preview = types.SimpleNamespace(GetID=lambda: 1, GetName=lambda: "Preview Camera")
    created = types.SimpleNamespace(GetID=lambda: 2, GetName=lambda: "Camera")
    scene = {"cameras": [preview]}

    class _Edit:
        def AddCamera(self, name):
            assert name == "Camera"
            scene["cameras"].append(created)
            return True

    camera.RLPy = types.SimpleNamespace(
        EObjectType_Camera=object(),
        RScene=types.SimpleNamespace(FindObjects=lambda unused_type: list(scene["cameras"])),
    )
    sys.modules["RLPy2"] = types.SimpleNamespace(Edit=types.SimpleNamespace(GetInterface=lambda: _Edit()))
    try:
        result = camera.create_camera({})
        assert result == {"status": "ok", "created_cameras": [{"id": "2", "name": "Camera"}]}
    finally:
        camera.RLPy = original_rlpy
        if original_rpy2 is None:
            del sys.modules["RLPy2"]
        else:
            sys.modules["RLPy2"] = original_rpy2


def test_focus_method_values_are_keyframeable():
    assert camera._focus_method_value("manual") == 0
    assert camera._focus_method_value("tracking") == 1
    assert camera._focus_method_value(0) == 0
    assert camera._focus_method_value(1) == 1


def test_get_camera_reports_camera_dof_pick_mode_when_supported():
    target = _Camera()
    original_rlpy = camera.RLPy
    original_rpy2 = sys.modules.get("RLPy2")
    original_status = getattr(fake_rlpy, "RStatus", None)
    fake_rlpy.RStatus = types.SimpleNamespace(Success="success")
    camera.RLPy = types.SimpleNamespace(
        RStatus=types.SimpleNamespace(Success="success"),
        RGlobal=types.SimpleNamespace(GetTime=lambda: _Time()),
        RScene=types.SimpleNamespace(GetCurrentCamera=lambda: target),
    )
    sys.modules["RLPy2"] = types.SimpleNamespace(
        Query=types.SimpleNamespace(
            GetInterface=lambda: types.SimpleNamespace(IsCameraDofPickMode=lambda: True)
        )
    )
    try:
        assert camera.get_camera({})["camera_dof_pick_mode_active"] is True
    finally:
        camera.RLPy = original_rlpy
        if original_status is None:
            delattr(fake_rlpy, "RStatus")
        else:
            fake_rlpy.RStatus = original_status
        if original_rpy2 is None:
            del sys.modules["RLPy2"]
        else:
            sys.modules["RLPy2"] = original_rpy2


def test_get_camera_reports_unknown_pick_mode_on_older_runtime():
    target = _Camera()
    original_rlpy = camera.RLPy
    original_rpy2 = sys.modules.get("RLPy2")
    original_status = getattr(fake_rlpy, "RStatus", None)
    fake_rlpy.RStatus = types.SimpleNamespace(Success="success")
    camera.RLPy = types.SimpleNamespace(
        RStatus=types.SimpleNamespace(Success="success"),
        RGlobal=types.SimpleNamespace(GetTime=lambda: _Time()),
        RScene=types.SimpleNamespace(GetCurrentCamera=lambda: target),
    )
    sys.modules["RLPy2"] = types.SimpleNamespace(Query=types.SimpleNamespace(GetInterface=lambda: object()))
    try:
        assert camera.get_camera({})["camera_dof_pick_mode_active"] is None
    finally:
        camera.RLPy = original_rlpy
        if original_status is None:
            delattr(fake_rlpy, "RStatus")
        else:
            fake_rlpy.RStatus = original_status
        if original_rpy2 is None:
            del sys.modules["RLPy2"]
        else:
            sys.modules["RLPy2"] = original_rpy2


class _Time:
    def ToInt(self):
        return 1000


class _Vector2:
    def __init__(self, x, y):
        self.x, self.y = x, y


class _Vector3:
    def __init__(self, x=0, y=0, z=0):
        self.x, self.y, self.z = x, y, z


class _Dof:
    def __init__(self):
        self.enabled = True
        self.focus = 100.0
        self.range = 25.0
        self.focus_method = 0
        self.near_transition_region = 1.0
        self.far_transition_region = 2.0
        self.near_blur_scale = 0.5
        self.far_blur_scale = 0.75
        self.min_blend_distance = 0.2
        self.center_color_weight = 20.0
        self.edge_decay_power = 1.0
        self.fstop = 2.8
        self.focus_offset = 0.0
        self.focus_target_id = 0
        self.focus_face_index = 0
        self.focus_barycentric = _Vector3(1.0, 0.0, 0.0)

    def GetEnable(self): return self.enabled
    def GetFocus(self): return self.focus
    def GetRange(self): return self.range
    def GetFocusMethod(self): return self.focus_method
    def GetNearTransitionRegion(self): return self.near_transition_region
    def GetFarTransitionRegion(self): return self.far_transition_region
    def GetNearBlurScale(self): return self.near_blur_scale
    def GetFarBlurScale(self): return self.far_blur_scale
    def GetMinBlendDistance(self): return self.min_blend_distance
    def GetCenterColorWeight(self): return self.center_color_weight
    def GetEdgeDecayPower(self): return self.edge_decay_power
    def GetFstop(self): return self.fstop
    def GetFocusOffset(self): return self.focus_offset
    def GetFocusTargetId(self): return self.focus_target_id
    def GetFocusFaceIndex(self): return self.focus_face_index
    def GetFocusBarycentric(self): return self.focus_barycentric


class _Bokeh:
    def __init__(self):
        self.type = 1
        self.blade_count = 6
        self.squeeze_factor = 1.0

    def GetType(self): return self.type
    def GetBladeCount(self): return self.blade_count
    def GetSqueezeFactor(self): return self.squeeze_factor


class _Stereo:
    def __init__(self):
        self.enabled = False
        self.interocular = 6.5
        self.screen_depth = 500

    def GetEnable(self): return self.enabled
    def GetInterocular(self): return self.interocular
    def GetScreenDepth(self): return self.screen_depth


class _Camera:
    def __init__(self):
        self.aperture = _Vector2(36.0, 24.0)
        self.sensor_shift = _Vector2(0.0, 0.0)
        self.focal_length = 50.0
        self.perspective = True
        self.fit_resolution = 0
        self.fov_axis = 0
        self.lock_horizon = True
        self.lock_up_vector = False
        self.freeze = False
        self.dof = _Dof()
        self.bokeh = _Bokeh()
        self.stereo = _Stereo()
        self.keys = []

    def GetID(self): return 1001
    def GetName(self): return "Cube_01"
    def GetAperture(self, unused_width, unused_height):
        return (fake_rlpy.RStatus.Success, self.aperture.x, self.aperture.y)
    def SetAperture(self, value, unused_record=False):
        self.aperture = value
        return fake_rlpy.RStatus.Success
    def GetFocalLength(self, unused_time): return self.focal_length
    def SetFocalLength(self, unused_time, value):
        self.focal_length = value
        return fake_rlpy.RStatus.Success
    def GetAngleOfView(self, unused_time): return 39.6
    def GetNearClippingPlane(self): return 1
    def GetFarClippingPlane(self): return 10000
    def GetNearClippingPlaneF(self): return 1.0
    def GetFarClippingPlaneF(self): return 10000.0
    def GetFitFovType(self): return self.fov_axis
    def GetFitRenderRegionType(self): return self.fit_resolution
    def SetFitFovType(self, value, unused_record=False):
        self.fov_axis = value
        return fake_rlpy.RStatus.Success
    def SetFitRenderRegionType(self, value, unused_record=False):
        self.fit_resolution = value
        return fake_rlpy.RStatus.Success
    def GetProjectMode(self): return self.perspective
    def SetProjectMode(self, value, unused_record=False):
        self.perspective = value
        return fake_rlpy.RStatus.Success
    def GetSensorShift(self): return self.sensor_shift
    def SetSensorShift(self, value, unused_record=False):
        self.sensor_shift = value
        return fake_rlpy.RStatus.Success
    def GetLockHorizon(self): return self.lock_horizon
    def SetLockHorizon(self, value, unused_record=False):
        self.lock_horizon = value
        return fake_rlpy.RStatus.Success
    def GetLockUpVector(self): return self.lock_up_vector
    def SetLockUpVector(self, value, unused_record=False):
        self.lock_up_vector = value
        return fake_rlpy.RStatus.Success
    def GetFreeze(self): return self.freeze
    def SetFreeze(self, value, unused_record=False):
        self.freeze = value
        return fake_rlpy.RStatus.Success
    def GetDOFData(self): return self.dof
    def GetDofBokehData(self): return self.bokeh
    def SetDofBokehData(self, value, unused_record=False):
        self.bokeh = value
        return fake_rlpy.RStatus.Success
    def GetStereoData(self): return self.stereo
    def SetStereoData(self, value, unused_record=False):
        self.stereo = value
        return fake_rlpy.RStatus.Success
    def GetControl(self, unused_name): return object()
    def GetFocalLengthKeyCount(self): return 0
    def GetDofKeyCount(self): return len(self.keys)
    def IsLookAtMode(self, unused_time): return False
    def GetDofKeys(self): return list(self.keys)

    def SetDofKey(self, key, unused_record=False):
        self.keys.append(key)
        return fake_rlpy.RStatus.Success

    def SetDofFocusTarget(self, target_id, unused_record=False):
        self.dof.focus_method = 1
        self.dof.focus_target_id = target_id
        return fake_rlpy.RStatus.Success


def test_camera_settings_use_stable_id_and_return_readback():
    target = _Camera()
    original_rlpy = camera.RLPy
    original_status = getattr(fake_rlpy, "RStatus", None)
    fake_rlpy.RStatus = types.SimpleNamespace(Success="success")
    camera.RLPy = types.SimpleNamespace(
        RStatus=types.SimpleNamespace(Success="success"),
        RGlobal=types.SimpleNamespace(GetTime=lambda: _Time()),
        RTime=types.SimpleNamespace(FromValue=lambda unused_value: _Time()),
        RScene=types.SimpleNamespace(
            GetCurrentCamera=lambda: target,
            FindObject=lambda unused_type, unused_name: target,
            QueryObjectByID=lambda value: target if value == "1001" else None,
        ),
        RVector2=_Vector2,
        RVector3=_Vector3,
        ECameraFitResolution_Horizontal=0,
        ECameraFitResolution_Vertical=1,
        ECameraFitResolution__None=-1,
        RCameraDofKeyData=type("DofKey", (), {})
    )
    try:
        result = camera.set_camera_settings(
            {
                "camera_id": "1001",
                "film_back": {"width": 1.0, "height": 0.75, "unit": "inch"},
                "sensor_shift": {"x": 0.1, "y": -0.2},
                "lens": {"preset_mm": 80},
                "display": {"allow_tilt": True, "freeze": True},
            }
        )
        assert result["status"] == "ok"
        assert result["changed"] is True
        assert result["readback"]["film_back"]["width"] == 25.4
        assert round(result["readback"]["film_back"]["height"], 6) == 19.05
        assert result["readback"]["sensor_shift"] == {"x": 0.1, "y": -0.2}
        assert result["readback"]["lens"]["focal_length_mm"] == 80.0
        assert result["readback"]["display"]["allow_tilt"] is True
        assert result["readback"]["display"]["freeze"] is True

        target_result = camera.pick_camera_focus_target(
            {"camera_id": "1001", "object_id": "9001"}
        )
        assert target_result["target_id"] == "9001"
        assert target_result["readback"]["focus_target_id"] == "9001"

        detach_result = camera.detach_camera_focus_target({"camera_id": "1001"})
        assert detach_result["detached"] is True
        assert detach_result["readback"]["focus_target_id"] is None
    finally:
        camera.RLPy = original_rlpy
        if original_status is None:
            delattr(fake_rlpy, "RStatus")
        else:
            fake_rlpy.RStatus = original_status


def test_camera_focus_picker_snaps_to_requested_surface_point():
    target = _Camera()
    original_rlpy = camera.RLPy
    original_rpy2 = sys.modules.get("RLPy2")
    original_status = getattr(fake_rlpy, "RStatus", None)
    original_get_camera_settings = camera.get_camera_settings
    fake_rlpy.RStatus = types.SimpleNamespace(Success="success")
    calls = []

    class _System:
        def ToHandle(self, object_id): return "handle:{0}".format(object_id)

    class _Result:
        def IsError(self): return False

    class _Edit:
        def SetCameraDOFFocusPickData(self, *args):
            calls.append(args)
            return _Result()

    fake_rpy2 = types.SimpleNamespace(
        System=types.SimpleNamespace(GetInterface=lambda: _System()),
        Edit=types.SimpleNamespace(GetInterface=lambda: _Edit()),
        RTime=types.SimpleNamespace(FromValue=lambda value: _Time()),
    )
    camera.RLPy = types.SimpleNamespace(
        RStatus=types.SimpleNamespace(Success="success"),
        RGlobal=types.SimpleNamespace(GetTime=lambda: _Time()),
        RScene=types.SimpleNamespace(QueryObjectByID=lambda value: target if value == "1001" else None),
    )
    camera.get_camera_settings = lambda _args: {"dof": {"focus_target_id": "9001"}}
    sys.modules["RLPy2"] = fake_rpy2
    try:
        result = camera.pick_camera_focus_target(
            {
                "camera_id": "1001",
                "object_id": "9001",
                "focus_position": {"x": 1.0, "y": 2.0, "z": 3.0},
                "focus_offset": 0.25,
            }
        )
        assert result["target_id"] == "9001"
        assert result["focus_position"] == {"x": 1.0, "y": 2.0, "z": 3.0}
        assert calls[0][0] == "handle:1001"
        assert calls[0][1].ToInt() == 1000
        assert calls[0][2:] == ("handle:9001", 1.0, 2.0, 3.0, 0.25, True)

        try:
            camera.pick_camera_focus_target(
                {"camera_id": "1001", "object_id": "9001", "focus_position": {"x": float("nan"), "y": 0, "z": 0}}
            )
        except ValueError as error:
            assert "finite" in str(error)
        else:
            raise AssertionError("non-finite focus positions must be rejected")
    finally:
        camera.RLPy = original_rlpy
        camera.get_camera_settings = original_get_camera_settings
        if original_rpy2 is None:
            del sys.modules["RLPy2"]
        else:
            sys.modules["RLPy2"] = original_rpy2
        if original_status is None:
            delattr(fake_rlpy, "RStatus")
        else:
            fake_rlpy.RStatus = original_status


def test_camera_presets_are_exposed_from_the_native_lens_panel():
    result = camera.get_camera_presets({})
    assert [item["focal_length_mm"] for item in result["presets"]] == [20.0, 35.0, 50.0, 80.0, 105.0, 200.0]


def test_camera_key_supports_sensor_shift_key_write_and_sampled_readback():
    class _TimeValue:
        def __init__(self, value): self.value = value
        def ToInt(self): return self.value

    original_rlpy = camera.RLPy
    original_rpy2 = sys.modules.get("RLPy2")
    target = _Camera()
    state = {"time": _TimeValue(0)}
    target.sensor_shift_keys = {0: _Vector2(0.0, 0.0)}

    class _Fps:
        def IndexedFrameTime(self, frame): return _TimeValue(frame * 1000)

    class _Edit:
        def SetCameraSensorShiftKeyableData(self, handle, time, x, y, record_undo):
            assert handle == "handle:1001"
            assert record_undo is True
            target.sensor_shift_keys[time.ToInt()] = _Vector2(x, y)
            return "success"

    class _System:
        def ToHandle(self, object_id): return "handle:{0}".format(object_id)

    edit = _Edit()
    system = _System()
    fake_rpy2 = types.SimpleNamespace(
        Edit=types.SimpleNamespace(GetInterface=lambda: edit),
        System=types.SimpleNamespace(GetInterface=lambda: system),
        RTime=types.SimpleNamespace(FromValue=lambda value: _TimeValue(value)),
    )
    fake_rlpy = types.SimpleNamespace(
        RStatus=types.SimpleNamespace(Success="success"),
        RGlobal=types.SimpleNamespace(
            GetTime=lambda: state["time"],
            SetTime=lambda value: state.update(time=value) or "success",
            GetFps=lambda: _Fps(),
        ),
        RTime=types.SimpleNamespace(FromValue=lambda value: _TimeValue(value)),
        RScene=types.SimpleNamespace(QueryObjectByID=lambda value: target if value == "1001" else None),
        RVector2=_Vector2,
    )
    target.GetSensorShift = lambda: target.sensor_shift_keys.get(
        state["time"].ToInt(), _Vector2(0.0, 0.0)
    )
    camera.RLPy = fake_rlpy
    sys.modules["RLPy2"] = fake_rpy2
    try:
        result = camera.camera_key(
            {
                "action": "set",
                "channel": "sensor_shift",
                "camera_id": "1001",
                "frame": 100,
                "key": {"x": 36.0, "y": 0.0},
            }
        )
        assert result["status"] == "queued"
        assert result["time_ms"] == 100000
        assert result["value"] == {"x": 36.0, "y": 0.0}

        readback = camera.camera_key(
            {"action": "get", "channel": "sensor_shift", "camera_id": "1001", "frame": 100}
        )
        assert readback["value"] == {"x": 36.0, "y": 0.0}
        assert state["time"].ToInt() == 0
    finally:
        camera.RLPy = original_rlpy
        if original_rpy2 is None:
            del sys.modules["RLPy2"]
        else:
            sys.modules["RLPy2"] = original_rpy2
