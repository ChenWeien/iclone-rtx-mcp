import RLPy

from iclone_mcp_tool_objects import find_by_name


def create_camera(_args):
    before = {str(camera.GetID()) for camera in RLPy.RScene.FindObjects(RLPy.EObjectType_Camera)}
    from iclone_mcp_tool_diagnostics import trigger_ui_action

    action = trigger_ui_action({"object_name": "qtMenuAddCameraAction"})
    created = [
        {"id": str(camera.GetID()), "name": camera.GetName()}
        for camera in RLPy.RScene.FindObjects(RLPy.EObjectType_Camera)
        if str(camera.GetID()) not in before and camera.GetName() != "Preview Camera"
    ]
    if not created:
        raise RuntimeError("iClone did not report a newly created scene camera")
    return {"action": action, "created_cameras": created}


def _find(name=None):
    current = RLPy.RScene.GetCurrentCamera()
    if name and current is not None and current.GetName() == name:
        return current
    if not name:
        if current is None:
            raise ValueError("Camera not found")
        return current
    for camera in RLPy.RScene.FindObjects(RLPy.EObjectType_Camera):
        if camera.GetName() == name:
            return camera
    raise ValueError("Camera not found")


def _find_camera(args):
    camera_id = args.get("camera_id") or args.get("object_id")
    if camera_id is not None:
        query = getattr(RLPy.RScene, "QueryObjectByID", None)
        if callable(query):
            camera = query(str(camera_id))
            if camera is not None:
                return camera
        find_objects = getattr(RLPy.RScene, "FindObjects", None)
        if callable(find_objects):
            for camera in find_objects(getattr(RLPy, "EObjectType_Camera", None)):
                if str(camera.GetID()) == str(camera_id):
                    return camera
        raise ValueError("Camera not found: {0}".format(camera_id))
    return _find(args.get("name"))


def _vector2(value):
    if value is None:
        return None
    if isinstance(value, (tuple, list)):
        if len(value) >= 3 and value[0] == RLPy.RStatus.Success:
            return {"x": float(value[1]), "y": float(value[2])}
        if len(value) >= 2:
            return {"x": float(value[0]), "y": float(value[1])}
    if hasattr(value, "x") and hasattr(value, "y"):
        return {"x": float(value.x), "y": float(value.y)}
    if hasattr(value, "X") and hasattr(value, "Y"):
        return {"x": float(value.X()), "y": float(value.Y())}
    return None


def _vector3(value):
    if value is None:
        return None
    if isinstance(value, (tuple, list)) and len(value) >= 3:
        return {"x": float(value[0]), "y": float(value[1]), "z": float(value[2])}
    if hasattr(value, "x") and hasattr(value, "y") and hasattr(value, "z"):
        return {"x": float(value.x), "y": float(value.y), "z": float(value.z)}
    if hasattr(value, "X") and hasattr(value, "Y") and hasattr(value, "Z"):
        return {"x": float(value.X()), "y": float(value.Y()), "z": float(value.Z())}
    return None


def _member(value, name, default=None):
    method = getattr(value, name, None)
    if method is not None:
        return method() if callable(method) else method
    return getattr(value, name[3:] if name.startswith("Get") else name, default)


def _camera_id(camera):
    return str(camera.GetID())


def _dof_snapshot(camera):
    data = camera.GetDOFData() if hasattr(camera, "GetDOFData") else None
    if data is None:
        return None
    focus_method = _member(data, "GetFocusMethod")
    focus_method_name = {0: "manual", 1: "tracking"}.get(focus_method, focus_method)
    return {
        "enabled": bool(_member(data, "GetEnable", False)),
        "focus_distance": float(_member(data, "GetFocus", 0.0)),
        "focus_range": float(_member(data, "GetRange", 0.0)),
        "focus_method": focus_method_name,
        "near_transition_region": float(_member(data, "GetNearTransitionRegion", 0.0)),
        "far_transition_region": float(_member(data, "GetFarTransitionRegion", 0.0)),
        "near_blur_scale": float(_member(data, "GetNearBlurScale", 1.0)),
        "far_blur_scale": float(_member(data, "GetFarBlurScale", 1.0)),
        "min_blend_distance": float(_member(data, "GetMinBlendDistance", 0.2)),
        "center_color_weight": float(_member(data, "GetCenterColorWeight", 20.0)),
        "edge_decay_power": float(_member(data, "GetEdgeDecayPower", 1.0)),
        "fstop": float(_member(data, "GetFstop", 2.8)),
        "focus_offset": float(_member(data, "GetFocusOffset", 0.0)),
        "focus_target_id": str(_member(data, "GetFocusTargetId", 0) or "") or None,
        "focus_face_index": int(_member(data, "GetFocusFaceIndex", 0)),
        "focus_barycentric": _vector3(_member(data, "GetFocusBarycentric", None))
        if _member(data, "GetFocusBarycentric", None) is not None
        else None,
    }


def _bokeh_snapshot(camera):
    method = getattr(camera, "GetDofBokehData", None)
    if method is None:
        return None
    data = method()
    if data is None:
        return None
    return {
        "type": int(_member(data, "GetType", 0)),
        "blade_count": int(_member(data, "GetBladeCount", 6)),
        "squeeze_factor": float(_member(data, "GetSqueezeFactor", 1.0)),
    }


def _stereo_snapshot(camera):
    method = getattr(camera, "GetStereoData", None)
    if method is None:
        return None
    data = method()
    if data is None:
        return None
    return {
        "enabled": bool(_member(data, "GetEnable", getattr(data, "bEnable", False))),
        "interocular": float(_member(data, "GetInterocular", getattr(data, "fInterocular", 0.0))),
        "screen_depth": int(_member(data, "GetScreenDepth", getattr(data, "nScreenDepth", 500))),
        "convergence_distance": int(_member(data, "GetScreenDepth", getattr(data, "nScreenDepth", 500))),
    }


def _fit_name(value):
    values = {
        getattr(RLPy, "ECameraFitResolution_Horizontal", object()): "horizontal",
        getattr(RLPy, "ECameraFitResolution_Vertical", object()): "vertical",
        getattr(RLPy, "ECameraFitResolution__None", object()): "none",
    }
    return values.get(value, value)


def _fit_value(name):
    values = {
        "horizontal": getattr(RLPy, "ECameraFitResolution_Horizontal", None),
        "vertical": getattr(RLPy, "ECameraFitResolution_Vertical", None),
        "none": getattr(RLPy, "ECameraFitResolution__None", None),
    }
    if name not in values or values[name] is None:
        raise ValueError("fit type must be horizontal, vertical, or none")
    return values[name]


def _make_vector2(value, name):
    if not isinstance(value, dict):
        raise ValueError("{0} must be an object with x and y".format(name))
    x = value.get("x")
    y = value.get("y")
    if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        raise ValueError("{0} must contain numeric x and y".format(name))
    vector_type = getattr(RLPy, "RVector2", None)
    if vector_type is None:
        raise RuntimeError("This iClone build does not expose RVector2")
    return vector_type(float(x), float(y))


def _time_value(args):
    has_time_ms = "time_ms" in args and args["time_ms"] is not None
    has_frame = "frame" in args and args["frame"] is not None
    if has_time_ms and has_frame:
        raise ValueError("Pass either time_ms or frame, not both")
    if has_time_ms:
        value = args["time_ms"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("time_ms must be a non-negative integer")
        return RLPy.RTime.FromValue(value)
    if has_frame:
        value = args["frame"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("frame must be a non-negative integer")
        fps = RLPy.RGlobal.GetFps()
        if not hasattr(fps, "IndexedFrameTime"):
            raise RuntimeError("This iClone build cannot convert frames to time")
        return fps.IndexedFrameTime(value)
    return RLPy.RGlobal.GetTime()


def _transform_control(camera):
    control = camera.GetControl("Transform")
    if control is None:
        raise RuntimeError(
            "Camera '%s' has no animable Transform control. "
            "The iClone Preview Camera cannot be animated; use a real scene camera." % camera.GetName()
        )
    return control


def _focus_method_value(value):
    if isinstance(value, bool):
        raise ValueError("focus_method must be 'manual' or 'tracking'")
    if isinstance(value, int):
        if value in (0, 1):
            return value
        raise ValueError("focus_method must be 'manual' or 'tracking'")
    normalized = str(value).lower()
    if normalized == "manual":
        return 0
    if normalized == "tracking":
        return 1
    raise ValueError("focus_method must be 'manual' or 'tracking'")


def get_camera(args):
    camera = _find(args.get("name"))
    time = RLPy.RGlobal.GetTime()
    aperture = camera.GetAperture(0, 0) if hasattr(camera, "GetAperture") else None
    aperture_data = None
    if isinstance(aperture, (tuple, list)) and len(aperture) >= 3 and aperture[0] == RLPy.RStatus.Success:
        aperture_data = {"width": aperture[1], "height": aperture[2]}
    result = {
        "id": _camera_id(camera),
        "name": camera.GetName(),
        "focal_length": camera.GetFocalLength(time),
        "angle_of_view": camera.GetAngleOfView(time),
        "near_clipping_plane": camera.GetNearClippingPlane(),
        "far_clipping_plane": camera.GetFarClippingPlane(),
        "aperture": aperture_data,
        "fit_fov_type": camera.GetFitFovType() if hasattr(camera, "GetFitFovType") else None,
        "fit_render_region_type": camera.GetFitRenderRegionType() if hasattr(camera, "GetFitRenderRegionType") else None,
    }
    include = args.get("include") or []
    if isinstance(include, str):
        include = [include]
    if not include:
        return result
    camera_ref = {"camera_id": _camera_id(camera), "name": camera.GetName()}
    for key in ("time_ms", "frame"):
        if key in args:
            camera_ref[key] = args[key]
    if "settings" in include:
        result["settings"] = get_camera_settings(camera_ref)
    if "capabilities" in include:
        result["capabilities"] = get_camera_capabilities(camera_ref)
    if "presets" in include:
        result["presets"] = get_camera_presets({})
    return result


def _optional_camera_value(camera, method_name, default=None, *arguments):
    method = getattr(camera, method_name, None)
    if method is None:
        return default
    try:
        return method(*arguments)
    except Exception:
        return default


def get_camera_settings(args):
    camera = _find_camera(args)
    time = _time_value(args)
    basic = get_camera({"name": camera.GetName()})
    aperture = basic.get("aperture")
    sensor_shift = _vector2(_optional_camera_value(camera, "GetSensorShift"))
    bokeh = _bokeh_snapshot(camera)
    stereo = _stereo_snapshot(camera)
    focus_method = _optional_camera_value(camera, "GetFitFovType")
    projection = _optional_camera_value(camera, "GetProjectMode")
    lock_horizon = _optional_camera_value(camera, "GetLockHorizon")
    lock_up_vector = _optional_camera_value(camera, "GetLockUpVector")
    freeze = _optional_camera_value(camera, "GetFreeze")
    dof = _dof_snapshot(camera)
    focal_length = float(camera.GetFocalLength(time))
    preset_values = (20.0, 35.0, 50.0, 80.0, 105.0, 200.0)
    lens_preset = next((value for value in preset_values if abs(value - focal_length) < 1e-4), None)
    result = {
        "camera_id": _camera_id(camera),
        "name": camera.GetName(),
        "preview": camera.GetName() == "Preview Camera",
        "projection": {
            "perspective": projection,
            "fit_resolution": _fit_name(_optional_camera_value(camera, "GetFitRenderRegionType")),
            "fov_axis": _fit_name(focus_method),
        },
        "film_back": {
            "width": aperture.get("width") if aperture else None,
            "height": aperture.get("height") if aperture else None,
            "unit": "mm",
        },
        "sensor_shift": sensor_shift,
        "lens": {
            "preset_mm": lens_preset,
            "focal_length_mm": focal_length,
            "angle_of_view_degrees": float(camera.GetAngleOfView(time)),
            "universal_zoom": _optional_camera_value(camera, "GetUniversalZoom"),
        },
        "bokeh": bokeh,
        "dof": dof,
        "clipping": {
            "near": float(_optional_camera_value(camera, "GetNearClippingPlaneF", basic["near_clipping_plane"])),
            "far": float(_optional_camera_value(camera, "GetFarClippingPlaneF", basic["far_clipping_plane"])),
        },
        "stereo": stereo,
        "display": {
            "allow_tilt": None if lock_horizon is None else not bool(lock_horizon),
            "allow_flip": None if lock_up_vector is None else not bool(lock_up_vector),
            "freeze": freeze,
        },
        "capabilities": get_camera_capabilities({"camera_id": _camera_id(camera)})["fields"],
    }
    if dof is not None:
        result["dof"]["time_ms"] = int(time.ToInt64()) if hasattr(time, "ToInt64") else int(time.ToInt())
    return result


def _set_status(camera, method_name, value, *arguments):
    method = getattr(camera, method_name, None)
    if method is None:
        raise RuntimeError("Camera API is not exposed: {0}".format(method_name))
    result = method(value, *arguments)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set camera field: {0}".format(method_name))


def _set_camera_dof_key(camera, values, time_value):
    key_data_type = getattr(RLPy, "RCameraDofKeyData", None)
    if key_data_type is not None and hasattr(camera, "SetDofKey"):
        key_data = key_data_type()
        key_data.time_ms = int(time_value.ToInt64()) if hasattr(time_value, "ToInt64") else int(time_value.ToInt())
        fields = {
            "enabled": values.get("enabled"),
            "focus": values.get("focus_distance"),
            "range": values.get("focus_range"),
            "near_transition_region": values.get("near_transition_region"),
            "far_transition_region": values.get("far_transition_region"),
            "near_blur_scale": values.get("near_blur_scale"),
            "far_blur_scale": values.get("far_blur_scale"),
            "min_blend_distance": values.get("min_blend_distance"),
            "center_color_weight": values.get("center_color_weight"),
            "edge_decay_power": values.get("edge_decay_power"),
            "fstop": values.get("fstop"),
            "focus_offset": values.get("focus_offset"),
            "focus_method": _focus_method_value(values.get("focus_method", "manual")),
            "focus_face_index": values.get("focus_face_index", 0),
            "transition_type": values.get("transition_type", 0),
            "transition_strength": values.get("transition_strength", 50.0),
        }
        for name, value in fields.items():
            if value is not None and hasattr(key_data, name):
                setattr(key_data, name, value)
        if values.get("focus_barycentric") is not None and hasattr(key_data, "focus_barycentric"):
            key_data.focus_barycentric = _make_vector3(values["focus_barycentric"], "focus_barycentric")
        if values.get("focus_target_id") is not None and hasattr(key_data, "focus_target_id"):
            key_data.focus_target_id = int(values["focus_target_id"])
        result = camera.SetDofKey(key_data, True)
        if result != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not set camera focus key")
        return

    data = RLPy.RCameraDofData()
    for setter, key, default in (
        ("SetEnable", "enabled", True),
        ("SetFocus", "focus_distance", 100.0),
        ("SetRange", "focus_range", 100.0),
        ("SetNearTransitionRegion", "near_transition_region", 0.0),
        ("SetFarTransitionRegion", "far_transition_region", 0.0),
        ("SetNearBlurScale", "near_blur_scale", 1.0),
        ("SetFarBlurScale", "far_blur_scale", 1.0),
        ("SetMinBlendDistance", "min_blend_distance", 0.2),
        ("SetCenterColorWeight", "center_color_weight", 20.0),
        ("SetEdgeDecayPower", "edge_decay_power", 1.0),
        ("SetFstop", "fstop", 2.8),
    ):
        method = getattr(data, setter, None)
        if method is not None:
            value = values.get(key, default)
            method(value)
    if hasattr(data, "SetFocusMethod"):
        data.SetFocusMethod(_focus_method_value(values.get("focus_method", "manual")))
    key = RLPy.RKey()
    key.SetTime(time_value)
    key.SetTransitionType(getattr(RLPy, "ETransitionType_Linear", 0))
    key.SetTransitionStrength(float(values.get("transition_strength", 50.0)))
    result = camera.AddDofKey(key, data)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set camera focus key")


def _make_vector3(value, name):
    if not isinstance(value, dict):
        raise ValueError("{0} must be an object with x, y, and z".format(name))
    values = [value.get(axis) for axis in ("x", "y", "z")]
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in values):
        raise ValueError("{0} must contain numeric x, y, and z".format(name))
    return RLPy.RVector3(*[float(item) for item in values])


def _merge_mapping(current, updates):
    merged = dict(current or {})
    if updates:
        merged.update(updates)
    return merged


def _bokeh_type_value(value):
    if isinstance(value, bool):
        raise ValueError("bokeh.type must be a string or integer")
    if isinstance(value, int):
        if 0 <= value <= 4:
            return value
        raise ValueError("bokeh.type must be between 0 and 4")
    values = {
        "none": 0,
        "gaussian": 0,
        "gaussian_blur": 0,
        "blade": 1,
        "hex": 1,
        "circle": 2,
        "star": 3,
        "heart": 4,
    }
    normalized = str(value).lower().replace(" ", "_")
    if normalized not in values:
        raise ValueError("Unsupported bokeh.type")
    return values[normalized]


def _set_camera_method(camera, method_name, value, *extra):
    method = getattr(camera, method_name, None)
    if method is None:
        raise RuntimeError("Camera API is not exposed: {0}".format(method_name))
    result = method(value, *extra)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set camera field: {0}".format(method_name))


def _set_camera_settings(args):
    camera = _find_camera(args)
    camera_id = _camera_id(camera)
    before = get_camera_settings({"camera_id": camera_id})
    requested = {key: value for key, value in args.items() if key not in {"camera_id", "object_id", "name", "time_ms", "frame"}}
    time_value = _time_value(args)

    projection = requested.get("projection")
    if projection:
        if "perspective" in projection:
            _set_camera_method(camera, "SetProjectMode", bool(projection["perspective"]), True)
        if "fit_resolution" in projection:
            _set_camera_method(camera, "SetFitRenderRegionType", _fit_value(projection["fit_resolution"]), True)
        if "fov_axis" in projection:
            _set_camera_method(camera, "SetFitFovType", _fit_value(projection["fov_axis"]), True)

    film_back = requested.get("film_back")
    if film_back:
        current = before["film_back"]
        unit = str(film_back.get("unit", current.get("unit", "mm"))).lower()
        if unit not in {"mm", "inch"}:
            raise ValueError("film_back.unit must be mm or inch")
        width = film_back.get("width", current.get("width"))
        height = film_back.get("height", current.get("height"))
        if width is None or height is None or width <= 0 or height <= 0:
            raise ValueError("film_back width and height must be positive")
        if unit == "inch":
            width, height = width * 25.4, height * 25.4
        _set_camera_method(camera, "SetAperture", _make_vector2({"x": width, "y": height}, "film_back"), True)

    sensor_shift = requested.get("sensor_shift")
    if sensor_shift is not None:
        _set_camera_method(camera, "SetSensorShift", _make_vector2(sensor_shift, "sensor_shift"), True)

    lens = requested.get("lens")
    if lens:
        focal_length = lens.get("focal_length_mm", lens.get("preset_mm"))
        if focal_length is not None:
            if isinstance(focal_length, bool) or not isinstance(focal_length, (int, float)) or focal_length <= 0:
                raise ValueError("lens focal length must be positive")
            result = camera.SetFocalLength(time_value, float(focal_length))
            if result != RLPy.RStatus.Success:
                raise RuntimeError("iClone could not set focal length")
        if "universal_zoom" in lens:
            _set_camera_method(camera, "SetUniversalZoom", float(lens["universal_zoom"]), True)

    bokeh = requested.get("bokeh")
    if bokeh:
        method = getattr(camera, "GetDofBokehData", None)
        if method is None or getattr(camera, "SetDofBokehData", None) is None:
            raise RuntimeError("This iClone build does not expose camera bokeh settings")
        data = method()
        if "type" in bokeh:
            value = _bokeh_type_value(bokeh["type"])
            if hasattr(data, "SetType"):
                data.SetType(value)
            else:
                data.type = value
        if "blade_count" in bokeh:
            value = int(bokeh["blade_count"])
            if not 3 <= value <= 12:
                raise ValueError("bokeh.blade_count must be between 3 and 12")
            if hasattr(data, "SetBladeCount"):
                data.SetBladeCount(value)
            else:
                data.nBladeCount = value
        if "squeeze_factor" in bokeh:
            value = float(bokeh["squeeze_factor"])
            if not 0.01 <= value <= 100.0:
                raise ValueError("bokeh.squeeze_factor must be between 0.01 and 100")
            if hasattr(data, "SetSqueezeFactor"):
                data.SetSqueezeFactor(value)
            else:
                data.fSqueezeFactor = value
        _set_camera_method(camera, "SetDofBokehData", data, True)

    dof = requested.get("dof")
    clear_focus_target = False
    if dof:
        current_dof = before.get("dof") or {}
        _set_camera_dof_key(camera, _merge_mapping(current_dof, dof), time_value)
        if dof.get("focus_target_id") is not None and hasattr(camera, "SetDofFocusTarget"):
            target_id = int(dof["focus_target_id"])
            clear_focus_target = target_id == 0
            result = camera.SetDofFocusTarget(target_id, True)
            if result != RLPy.RStatus.Success and not clear_focus_target:
                raise RuntimeError("iClone could not set camera field: SetDofFocusTarget")

    clipping = requested.get("clipping")
    if clipping:
        if "near" in clipping:
            method_name = "SetNearClippingPlaneF" if hasattr(camera, "SetNearClippingPlaneF") else "SetNearClippingPlane"
            _set_camera_method(camera, method_name, float(clipping["near"]))
        if "far" in clipping:
            method_name = "SetFarClippingPlaneF" if hasattr(camera, "SetFarClippingPlaneF") else "SetFarClippingPlane"
            _set_camera_method(camera, method_name, float(clipping["far"]))

    stereo = requested.get("stereo")
    if stereo:
        method = getattr(camera, "GetStereoData", None)
        setter = getattr(camera, "SetStereoData", None)
        if method is None or setter is None:
            raise RuntimeError("This iClone build does not expose camera stereo settings")
        data = method()
        for attr, key, converter in (("bEnable", "enabled", bool), ("fInterocular", "interocular", float), ("nScreenDepth", "screen_depth", int), ("nScreenDepth", "convergence_distance", int)):
            if key not in stereo:
                continue
            value = converter(stereo[key])
            setter_method = getattr(data, {"bEnable": "SetEnable", "fInterocular": "SetInterocular", "nScreenDepth": "SetScreenDepth"}[attr], None)
            if setter_method is not None:
                setter_method(value)
            else:
                setattr(data, attr, value)
        _set_camera_method(camera, "SetStereoData", data, True)

    display = requested.get("display")
    if display:
        if "allow_tilt" in display:
            _set_camera_method(camera, "SetLockHorizon", not bool(display["allow_tilt"]), True)
        if "allow_flip" in display:
            _set_camera_method(camera, "SetLockUpVector", not bool(display["allow_flip"]), True)
        if "freeze" in display:
            _set_camera_method(camera, "SetFreeze", bool(display["freeze"]), True)

    readback = get_camera_settings({"camera_id": camera_id, "time_ms": int(time_value.ToInt64()) if hasattr(time_value, "ToInt64") else int(time_value.ToInt())})
    if clear_focus_target and (readback.get("dof") or {}).get("focus_target_id") is not None:
        raise RuntimeError("Camera focus target clear was not observable")
    return {
        "status": "ok",
        "camera_id": camera_id,
        "name": camera.GetName(),
        "requested": requested,
        "effective": readback,
        "readback": readback,
        "changed": before != readback,
    }


def set_camera_settings(args):
    # Convenience: top-level focal_length routes into lens.focal_length_mm.
    if "focal_length" in args and "lens" not in args:
        args = dict(args)
        args["lens"] = {"focal_length_mm": args.pop("focal_length")}
    elif "focal_length" in args and isinstance(args.get("lens"), dict) and "focal_length_mm" not in args["lens"]:
        args = dict(args)
        lens = dict(args["lens"])
        lens["focal_length_mm"] = args.pop("focal_length")
        args["lens"] = lens
    begin_action = getattr(RLPy.RGlobal, "BeginAction", None)
    end_action = getattr(RLPy.RGlobal, "EndAction", None)
    if begin_action is None or end_action is None:
        return _set_camera_settings(args)
    begin_action("MCP Set Camera Settings", True)
    try:
        return _set_camera_settings(args)
    finally:
        end_action()


def camera_key(args):
    action = (args.get("action") or "").lower()
    channel = (args.get("channel") or "dof").lower()
    if action == "get":
        if channel != "dof":
            raise ValueError("channel must be dof for action get")
        return get_camera_keys(args)
    if action == "set":
        if channel != "dof":
            raise ValueError("channel must be dof for action set")
        return set_camera_focus_key(args)
    if action == "remove":
        if channel == "dof":
            return remove_camera_dof_keys(args)
        if channel == "focal":
            return remove_camera_focal_keys(args)
        raise ValueError("channel must be dof or focal for action remove")
    raise ValueError("action must be one of: get, set, remove")


def set_camera(args):
    camera = _find(args.get("name"))
    time = RLPy.RGlobal.GetTime()
    if "focal_length" in args and camera.SetFocalLength(time, args["focal_length"]) != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set focal length")
    if "near_clipping_plane" in args and camera.SetNearClippingPlane(args["near_clipping_plane"]) != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set near clipping plane")
    if "far_clipping_plane" in args and camera.SetFarClippingPlane(args["far_clipping_plane"]) != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set far clipping plane")
    return get_camera({"name": camera.GetName()})


def get_camera_capabilities(args):
    camera = _find_camera(args)
    control = camera.GetControl("Transform")
    dof = camera.GetDOFData()
    focal_count = camera.GetFocalLengthKeyCount() if hasattr(camera, "GetFocalLengthKeyCount") else None
    dof_count = camera.GetDofKeyCount() if hasattr(camera, "GetDofKeyCount") else None
    look_at = camera.IsLookAtMode(RLPy.RGlobal.GetTime()) if hasattr(camera, "IsLookAtMode") else None
    preview = camera.GetName() == "Preview Camera"
    fields = []
    for name, getter, setter, widget_name in (
        ("projection", "GetProjectMode", "SetProjectMode", "qtProjectionComboBoxEx"),
        ("film_back", "GetAperture", "SetAperture", "qtCameraApertureWidthDoubleSpinBoxEx"),
        ("sensor_shift", "GetSensorShift", "SetSensorShift", "qtSensorShiftXCombodoublespinbox"),
        ("lens", "GetFocalLength", "SetFocalLength", "qtFocalLengthComboDoubleSpinbox"),
        ("universal_zoom", "GetUniversalZoom", "SetUniversalZoom", None),
        ("bokeh", "GetDofBokehData", "SetDofBokehData", "qtBokehTypeComboBox"),
        ("dof", "GetDOFData", "SetDofKey", "qtEnableDepthOfFieldCheckBox"),
        ("stereo", "GetStereoData", "SetStereoData", "qtEnableCameraStereocheckBox"),
        ("display", "GetLockHorizon", "SetLockHorizon", "qtAllowTiltCheckBox"),
        ("focus_target", "GetDOFData", "SetDofFocusTarget", "qtPickObjectMode"),
        ("focus_keys", "GetDofKeys", "SetDofKey", None),
        ("clipping", "GetNearClippingPlaneF", "SetNearClippingPlaneF", "qtClipPlaneNear"),
    ):
        readable = hasattr(camera, getter)
        writable = hasattr(camera, setter) and not preview
        fields.append(
            {
                "name": name,
                "visible": widget_name is not None,
                "enabled": writable or readable,
                "readable": readable,
                "writable": writable,
                "supported": readable or writable,
                "read_only": readable and not writable,
                "widget_name": widget_name,
                "reason": None if readable or writable else "The running RLPy camera wrapper does not expose this field.",
            }
        )
    return {
        "camera_id": _camera_id(camera),
        "name": camera.GetName(),
        "preview": preview,
        "transform_animable": control is not None,
        "dof_available": dof is not None,
        "focal_length_keys": focal_count,
        "dof_keys": dof_count,
        "focus_method": dof.GetFocusMethod() if dof is not None and hasattr(dof, "GetFocusMethod") else None,
        "focus_method_keyframeable": not preview and dof is not None and hasattr(dof, "SetFocusMethod") and hasattr(camera, "AddDofKey"),
        "is_look_at_mode": bool(look_at) if look_at is not None else None,
        "preview_camera_note": "A real scene camera is required for transform animation.",
        "fields": fields,
    }


def get_camera_presets(_args):
    return {
        "presets": [
            {"name": "20mm", "focal_length_mm": 20.0},
            {"name": "35mm", "focal_length_mm": 35.0},
            {"name": "50mm", "focal_length_mm": 50.0},
            {"name": "80mm", "focal_length_mm": 80.0},
            {"name": "105mm", "focal_length_mm": 105.0},
            {"name": "200mm", "focal_length_mm": 200.0},
        ],
        "source": "iClone Camera Lens Settings UI",
    }


def get_camera_keys(args):
    camera = _find_camera(args)
    method = getattr(camera, "GetDofKeys", None)
    if method is None:
        raise RuntimeError("This iClone build does not expose camera DOF key inspection")
    keys = []
    for key in method() or []:
        item = {}
        for field in (
            "time_ms", "enabled", "focus", "range", "near_transition_region",
            "far_transition_region", "near_blur_scale", "far_blur_scale",
            "min_blend_distance", "center_color_weight", "edge_decay_power",
            "fstop", "focus_method", "focus_target_id", "focus_face_index",
            "focus_offset", "transition_type", "transition_strength",
        ):
            item[field] = getattr(key, field)
        item["focus_barycentric"] = _vector3(getattr(key, "focus_barycentric", None))
        item["focus_method"] = {0: "manual", 1: "tracking"}.get(item["focus_method"], item["focus_method"])
        if item.get("focus_target_id"):
            item["focus_target_id"] = str(item["focus_target_id"])
        keys.append(item)
    return {"camera_id": _camera_id(camera), "name": camera.GetName(), "keys": keys, "count": len(keys)}


def set_camera_focus_key(args):
    camera = _find_camera(args)
    time_value = _time_value(args)
    values = dict(args.get("key") or {})
    for field in (
        "enabled", "focus_distance", "focus_range", "near_transition_region",
        "far_transition_region", "near_blur_scale", "far_blur_scale",
        "min_blend_distance", "center_color_weight", "edge_decay_power",
        "fstop", "focus_method", "focus_target_id", "focus_face_index",
        "focus_barycentric", "focus_offset", "transition_type", "transition_strength",
    ):
        if field in args:
            values[field] = args[field]
    _set_camera_dof_key(camera, values, time_value)
    readback = get_camera_keys({"camera_id": _camera_id(camera)})
    return {
        "status": "ok",
        "camera_id": _camera_id(camera),
        "name": camera.GetName(),
        "requested": values,
        "readback": readback,
    }


def pick_camera_focus_target(args):
    camera = _find_camera({key: args[key] for key in ("camera_id", "name") if key in args})
    target_id = args.get("object_id") or args.get("target_id")
    if not isinstance(target_id, (str, int)) or not str(target_id):
        raise ValueError("object_id must be a stable scene object ID")
    target_id = int(target_id)
    method = getattr(camera, "SetDofFocusTarget", None)
    if method is None:
        raise RuntimeError("This iClone build does not expose camera focus targets")
    result = method(target_id, True)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set the camera focus target")
    settings = get_camera_settings({"camera_id": _camera_id(camera)})
    if not settings.get("dof") or str(settings["dof"].get("focus_target_id")) != str(target_id):
        raise RuntimeError("Camera focus target write was not observable")
    return {"status": "ok", "camera_id": _camera_id(camera), "target_id": str(target_id), "readback": settings["dof"]}


def detach_camera_focus_target(args):
    camera_ref = {key: args[key] for key in ("camera_id", "object_id", "name") if key in args}
    result = set_camera_settings(dict(camera_ref, dof={"focus_target_id": 0}))
    readback = (result.get("readback") or {}).get("dof") or {}
    if readback.get("focus_target_id") is not None:
        raise RuntimeError("Camera focus target detach was not observable")
    return {
        "status": "ok",
        "camera_id": result["camera_id"],
        "name": result["name"],
        "detached": True,
        "readback": readback,
    }


def set_camera_transform(args):
    camera = _find(args.get("name"))
    control = _transform_control(camera)
    current = camera.LocalTransform()
    position, scale, rotation = current.T(), current.S(), current.R()
    if "position" in args:
        value = args["position"]
        position = RLPy.RVector3(value.get("x", position.x), value.get("y", position.y), value.get("z", position.z))
    if "rotation_degrees" in args:
        import math
        value = args["rotation_degrees"]
        matrix = RLPy.RMatrix3.FromEulerAngle(
            RLPy.EEulerOrder_XYZ,
            math.radians(value.get("x", 0)),
            math.radians(value.get("y", 0)),
            math.radians(value.get("z", 0)),
        )[0]
        rotation = RLPy.RQuaternion()
        rotation.FromRotationMatrix(matrix)
    result = control.SetValue(RLPy.RGlobal.GetTime(), RLPy.RTransform(scale, rotation, position))
    camera.Update()
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set the camera transform")
    return {"status": "ok", "name": camera.GetName(), "position": {"x": position.x, "y": position.y, "z": position.z}}


def set_camera_focal_key(args):
    camera = _find(args.get("name"))
    result = camera.SetFocalLength(RLPy.RGlobal.GetTime(), float(args["focal_length"]))
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set camera focal length")
    return get_camera({"name": camera.GetName()})


def set_camera_dof(args):
    camera = _find(args.get("name"))
    data = RLPy.RCameraDofData()
    data.SetEnable(bool(args.get("enabled", True)))
    data.SetFocus(float(args.get("focus", 200)))
    data.SetRange(float(args.get("range", 100)))
    if hasattr(data, "SetFocusMethod"):
        if "focus_method" in args:
            data.SetFocusMethod(_focus_method_value(args["focus_method"]))
        else:
            current = camera.GetDOFData()
            if current is not None and hasattr(current, "GetFocusMethod"):
                data.SetFocusMethod(current.GetFocusMethod())
    key = RLPy.RKey()
    key.SetTime(RLPy.RGlobal.GetTime())
    key.SetTransitionType(RLPy.ETransitionType_Linear)
    key.SetTransitionStrength(float(args.get("strength", 50)))
    result = camera.AddDofKey(key, data)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not add camera DOF key")
    focus_method = data.GetFocusMethod() if hasattr(data, "GetFocusMethod") else None
    return {"status": "ok", "name": camera.GetName(), "enabled": bool(args.get("enabled", True)), "focus": float(args.get("focus", 200)), "range": float(args.get("range", 100)), "focus_method": focus_method}


def remove_camera_dof_keys(args):
    camera = _find(args.get("name"))
    result = camera.RemoveDofKeys()
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not remove camera DOF keys")
    return {"status": "ok", "name": camera.GetName(), "dof_keys": camera.GetDofKeyCount()}


def remove_camera_focal_keys(args):
    camera = _find(args.get("name"))
    result = camera.RemoveFocalLengthKeys()
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not remove camera focal length keys")
    return {"status": "ok", "name": camera.GetName(), "focal_length_keys": camera.GetFocalLengthKeyCount()}


def set_current_camera(args):
    camera = _find(args["name"])
    result = RLPy.RScene.SetCurrentCamera(camera)
    if result is not None and result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not activate camera")
    return {"status": "ok", "name": camera.GetName()}


def set_camera_look_at(args):
    camera = _find(args.get("name"))
    target = find_by_name(args["target_name"])
    view_position = camera.WorldTransform().T()
    view_target = target.WorldTransform().T()
    forward = view_position - view_target
    forward.Normalize()
    up_axis = RLPy.RVector3(RLPy.RVector3.UNIT_Z)
    right = up_axis.Cross(forward)
    right.Normalize()
    up = forward.Cross(right)
    orientation = RLPy.RMatrix3(
        right.x, right.y, right.z,
        up.x, up.y, up.z,
        forward.x, forward.y, forward.z,
    )
    rotation = orientation.ToEulerAngle(RLPy.EEulerOrder_XYZ, 0, 0, 0)
    control = _transform_control(camera)
    block = control.GetDataBlock()
    time = RLPy.RGlobal.GetTime()
    for axis, value in zip(("X", "Y", "Z"), rotation):
        block.SetData("Rotation/Rotation" + axis, time, RLPy.RVariant(value))
    camera.Update()
    return {"status": "ok", "camera": camera.GetName(), "target": target.GetName()}


def register(registry):
    camera_ref = {"camera_id": {"type": "string"}, "object_id": {"type": "string"}, "name": {"type": "string"}}
    registry["create_camera"] = {
        "handler": create_camera,
        "main_thread": True,
        "description": "Ajoute une caméra de scène via l'action native iClone.",
        "inputSchema": {"type": "object", "properties": {}},
    }
    registry["get_camera"] = {
        "handler": get_camera,
        "main_thread": True,
        "read_only": True,
        "description": "Lit les paramètres de la caméra active ou nommée. Use include for settings, capabilities, or presets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "include": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["settings", "capabilities", "presets"]},
                },
                "time_ms": {"type": "integer", "minimum": 0},
                "frame": {"type": "integer", "minimum": 0},
            },
        },
    }
    registry["set_camera_settings"] = {
        "handler": set_camera_settings,
        "main_thread": True,
        "description": "Modifie un sous-ensemble des réglages caméra et renvoie le readback complet. Prefer this over hidden set_camera* siblings.",
        "inputSchema": {
            "type": "object",
            "properties": dict(
                camera_ref,
                projection={"type": "object"},
                film_back={"type": "object"},
                sensor_shift={"type": "object"},
                lens={"type": "object"},
                focal_length={"type": "number"},
                bokeh={"type": "object"},
                dof={"type": "object"},
                clipping={"type": "object"},
                stereo={"type": "object"},
                display={"type": "object"},
                time_ms={"type": "integer", "minimum": 0},
                frame={"type": "integer", "minimum": 0},
            ),
        },
    }
    registry["camera_key"] = {
        "handler": camera_key,
        "main_thread": True,
        "description": "Get, set, or remove camera DOF/focal keys. action get|set|remove; channel dof|focal.",
        "inputSchema": {
            "type": "object",
            "properties": dict(
                camera_ref,
                action={"type": "string", "enum": ["get", "set", "remove"]},
                channel={"type": "string", "enum": ["dof", "focal"]},
                key={"type": "object"},
                time_ms={"type": "integer", "minimum": 0},
                frame={"type": "integer", "minimum": 0},
            ),
            "required": ["action"],
        },
    }
    registry["set_current_camera"] = {
        "handler": set_current_camera,
        "main_thread": True,
        "description": "Active une caméra de scène pour le viewport et le rendu.",
        "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    }
    registry["set_camera_look_at"] = {
        "handler": set_camera_look_at,
        "main_thread": True,
        "description": "Oriente une caméra vers un objet à la frame courante en créant des clés de rotation.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "target_name": {"type": "string"}},
            "required": ["target_name"],
        },
    }
    registry["pick_camera_focus_target"] = {
        "handler": pick_camera_focus_target,
        "main_thread": True,
        "description": "Définit une cible DOF par identifiant d'objet stable, sans clic écran.",
        "inputSchema": {
            "type": "object",
            "properties": dict(camera_ref, object_id={"type": "string"}, target_id={"type": "string"}),
            "required": ["object_id"],
        },
    }
    registry["detach_camera_focus_target"] = {
        "handler": detach_camera_focus_target,
        "main_thread": True,
        "description": "Detach the camera DOF focus target and verify it is cleared.",
        "inputSchema": {
            "type": "object",
            "properties": camera_ref,
        },
    }

    # Legacy wrappers kept for bridge dispatch; not advertised to MCP clients.
    _hidden = {"advertise": False, "main_thread": True}
    registry["get_camera_capabilities"] = dict(
        _hidden,
        handler=get_camera_capabilities,
        read_only=True,
        description="Diagnostique les capacités d’une caméra iClone 8 avant de l’animer.",
        inputSchema={"type": "object", "properties": camera_ref},
    )
    registry["get_camera_settings"] = dict(
        _hidden,
        handler=get_camera_settings,
        read_only=True,
        description="Lit la surface cohérente des réglages caméra, objectif, filmback, bokeh, DOF et stéréo.",
        inputSchema={
            "type": "object",
            "properties": dict(camera_ref, time_ms={"type": "integer", "minimum": 0}, frame={"type": "integer", "minimum": 0}),
        },
    )
    registry["get_camera_presets"] = dict(
        _hidden,
        handler=get_camera_presets,
        read_only=True,
        description="Liste les préréglages focale de l'interface Camera Lens Settings.",
        inputSchema={"type": "object", "properties": {}},
    )
    registry["get_camera_keys"] = dict(
        _hidden,
        handler=get_camera_keys,
        read_only=True,
        description="Liste les clés DOF caméra avec méthode et cible de focus.",
        inputSchema={"type": "object", "properties": dict(camera_ref), "required": []},
    )
    registry["set_camera_focus_key"] = dict(
        _hidden,
        handler=set_camera_focus_key,
        description="Pose ou remplace une clé DOF caméra avec readback des clés.",
        inputSchema={
            "type": "object",
            "properties": dict(
                camera_ref,
                key={"type": "object"},
                time_ms={"type": "integer", "minimum": 0},
                frame={"type": "integer", "minimum": 0},
            ),
            "required": ["key"],
        },
    )
    registry["set_camera"] = dict(
        _hidden,
        handler=set_camera,
        description="Modifie focale et plans de clipping d'une caméra.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "focal_length": {"type": "number"},
                "near_clipping_plane": {"type": "number"},
                "far_clipping_plane": {"type": "number"},
            },
        },
    )
    registry["set_camera_transform"] = dict(
        _hidden,
        handler=set_camera_transform,
        description="Anime la position et la rotation d’une vraie caméra de scène.",
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string"}, "position": {"type": "object"}, "rotation_degrees": {"type": "object"}},
            "required": ["name"],
        },
    )
    registry["set_camera_focal_key"] = dict(
        _hidden,
        handler=set_camera_focal_key,
        description="Pose une clé de focale à la frame courante.",
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string"}, "focal_length": {"type": "number"}},
            "required": ["focal_length"],
        },
    )
    registry["set_camera_dof"] = dict(
        _hidden,
        handler=set_camera_dof,
        description="Pose une clé de profondeur de champ avec méthode de focus, focus et portée.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "enabled": {"type": "boolean"},
                "focus": {"type": "number"},
                "range": {"type": "number"},
                "strength": {"type": "number"},
                "focus_method": {"type": "string", "enum": ["manual", "tracking"]},
            },
            "required": [],
        },
    )
    registry["remove_camera_dof_keys"] = dict(
        _hidden,
        handler=remove_camera_dof_keys,
        destructive=True,
        description="Supprime toutes les clés de profondeur de champ de la caméra.",
        inputSchema={"type": "object", "properties": {"name": {"type": "string"}}},
    )
    registry["remove_camera_focal_keys"] = dict(
        _hidden,
        handler=remove_camera_focal_keys,
        destructive=True,
        description="Supprime toutes les clés de focale de la caméra.",
        inputSchema={"type": "object", "properties": {"name": {"type": "string"}}},
    )
