import math

import RLPy

from iclone_mcp_tool_objects import find_by_name


def _time(frame):
    return RLPy.RGlobal.GetFps().IndexedFrameTime(frame)


def _path_control(obj, key):
    control = obj.GetControl(key)
    if control is None:
        raise RuntimeError("Object %s has no %s control; attach it to a path first" % (obj.GetName(), key))
    return control


def list_paths(_args):
    if not hasattr(RLPy, "EObjectType_Path"):
        return {"paths": [], "supported": False}
    paths = RLPy.RScene.FindObjects(RLPy.EObjectType_Path)
    return {"supported": True, "paths": [{"id": path.GetID(), "name": path.GetName()} for path in paths]}


def create_path(args):
    raw_points = args.get("points")
    if not isinstance(raw_points, list) or len(raw_points) < 2:
        raise ValueError("points must contain at least two XYZ points")

    points = RLPy.Vector3fVector()
    for index, raw_point in enumerate(raw_points):
        if not isinstance(raw_point, dict) or not all(key in raw_point for key in ("x", "y", "z")):
            raise ValueError("points[%d] must contain x, y, and z" % index)
        values = [float(raw_point["x"]), float(raw_point["y"]), float(raw_point["z"])]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("points[%d] must contain finite coordinates" % index)
        points.push_back(RLPy.RVector3(*values))

    name = args.get("name", "Path")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a non-empty string")
    width = float(args.get("width", 0.0))
    if not math.isfinite(width) or width < 0.0:
        raise ValueError("width must be a finite non-negative number")

    path = RLPy.RScene.CreatePath(points, name, width)
    if path is None:
        raise RuntimeError("iClone could not create a path")

    selected_index = args.get("select_control_point")
    if selected_index is not None:
        if isinstance(selected_index, bool) or int(selected_index) != selected_index or int(selected_index) < 0:
            raise ValueError("select_control_point must be a non-negative integer")
        selected_index = int(selected_index)
        result = RLPy.RScene.SelectPathControlPoint(path, selected_index)
        if result != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not select path control point %d" % selected_index)

    return {
        "status": "ok",
        "id": path.GetID(),
        "name": path.GetName(),
        "point_count": len(raw_points),
        "width": getattr(path, "GetPathWidth", lambda: width)(),
        "selected_control_point": selected_index,
    }


def set_path_width(args):
    obj = find_by_name(args["name"])
    width = float(args["width"])
    if not math.isfinite(width) or width < 0.0:
        raise ValueError("width must be a finite non-negative number")
    setter = getattr(obj, "SetPathWidth", None)
    getter = getattr(obj, "GetPathWidth", None)
    if setter is None or getter is None:
        raise RuntimeError("This iClone build does not expose the path-width API")
    result = setter(width)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set path width")
    return {"status": "ok", "name": obj.GetName(), "width": getter()}


def select_path_control_point(args):
    obj = find_by_name(args["name"])
    selected_index = args["control_point"]
    if isinstance(selected_index, bool) or int(selected_index) != selected_index or int(selected_index) < 0:
        raise ValueError("control_point must be a non-negative integer")
    selected_index = int(selected_index)
    result = RLPy.RScene.SelectPathControlPoint(obj, selected_index)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not select path control point %d" % selected_index)
    return {"status": "ok", "name": obj.GetName(), "selected_control_point": selected_index}


def reproduce_walkway_path_gizmo(args):
    """Create and select the walkway used by Mantis 99804 through the public API."""
    points = args.get(
        "points",
        [
            {"x": -100.0, "y": 0.0, "z": 0.0},
            {"x": 0.0, "y": 100.0, "z": 0.0},
            {"x": 100.0, "y": 0.0, "z": 0.0},
        ],
    )
    name = args.get("name", "MCP Bug 99804 Walkway")
    width = float(args.get("width", 100.0))
    selected_index = args.get("select_control_point", 1)
    created = create_path(
        {
            "points": points,
            "name": name,
            "width": 0.0,
        }
    )
    width_result = set_path_width({"name": created["name"], "width": width})
    selection_result = select_path_control_point(
        {"name": created["name"], "control_point": selected_index}
    )
    info = get_path_info({"name": created["name"]})
    info.update(
        {
            "status": "ok",
            "reproduction": "mantis-99804-walkway-gizmo",
            "width_update": width_result,
            "selection": selection_result,
        }
    )
    return info


def get_path_info(args):
    """Inspect path controls, or list all paths when name is omitted."""
    if not args.get("name"):
        return list_paths(args)
    obj = find_by_name(args["name"])
    time = _time(int(args.get("frame", RLPy.RGlobal.GetFps().GetFrameIndex(RLPy.RGlobal.GetTime()))))
    linked = obj.GetLinkedObject(time)
    maximum = RLPy.RVector3()
    center = RLPy.RVector3()
    minimum = RLPy.RVector3()
    bounds_status = obj.GetBounds(maximum, center, minimum)
    get_width = getattr(obj, "GetPathWidth", None)
    return {
        "name": obj.GetName(),
        "type": obj.GetType(),
        "frame": int(args.get("frame", RLPy.RGlobal.GetFps().GetFrameIndex(RLPy.RGlobal.GetTime()))),
        "width": get_width() if get_width is not None else None,
        "linked_path": linked.GetName() if linked is not None else None,
        "controls": {
            "PathPosition": obj.GetControl("PathPosition") is not None,
            "PathOffset": obj.GetControl("PathOffset") is not None,
        },
        "bounds": {
            "status": "ok" if bounds_status == RLPy.RStatus.Success else "failed",
            "min": {"x": minimum.x, "y": minimum.y, "z": minimum.z},
            "center": {"x": center.x, "y": center.y, "z": center.z},
            "max": {"x": maximum.x, "y": maximum.y, "z": maximum.z},
        },
    }


def follow_path(args):
    action = (args.get("action") or "attach").lower()
    if action == "release":
        return release_path(args)
    if action != "attach":
        raise ValueError("action must be attach or release")
    obj = find_by_name(args["name"])
    path = find_by_name(args["path_name"])
    frame = int(args.get("frame", RLPy.RGlobal.GetFps().GetFrameIndex(RLPy.RGlobal.GetTime())))
    result = obj.FollowPath(path, _time(frame))
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not attach %s to path %s" % (obj.GetName(), path.GetName()))
    return {"status": "ok", "name": obj.GetName(), "path_name": path.GetName(), "frame": frame, "action": "attach"}


def release_path(args):
    obj = find_by_name(args["name"])
    frame = int(args.get("frame", RLPy.RGlobal.GetFps().GetFrameIndex(RLPy.RGlobal.GetTime())))
    result = obj.ReleasePath(_time(frame))
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not release the path from %s" % obj.GetName())
    return {"status": "ok", "name": obj.GetName(), "frame": frame, "action": "release"}


def set_path_position(args):
    obj = find_by_name(args["name"])
    frame = int(args.get("frame", RLPy.RGlobal.GetFps().GetFrameIndex(RLPy.RGlobal.GetTime())))
    position = float(args["position"])
    if position < 0 or position > 1:
        raise ValueError("position must be between 0 and 1")
    control = _path_control(obj, "PathPosition")
    result = control.SetValue(_time(frame), position)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set PathPosition")
    return {"status": "ok", "name": obj.GetName(), "position": position, "frame": frame}


def set_path_offset(args):
    obj = find_by_name(args["name"])
    frame = int(args.get("frame", RLPy.RGlobal.GetFps().GetFrameIndex(RLPy.RGlobal.GetTime())))
    value = args.get("position", {})
    rotation = args.get("rotation_degrees", {})
    matrix = RLPy.RMatrix3().FromEulerAngle(
        RLPy.EEulerOrder_XYZ,
        math.radians(rotation.get("x", 0)),
        math.radians(rotation.get("y", 0)),
        math.radians(rotation.get("z", 0)),
    )
    quaternion = RLPy.RQuaternion()
    quaternion.FromRotationMatrix(matrix)
    transform = RLPy.RTransform(
        RLPy.RVector3(1, 1, 1),
        quaternion,
        RLPy.RVector3(value.get("x", 0), value.get("y", 0), value.get("z", 0)),
    )
    control = _path_control(obj, "PathOffset")
    result = control.SetValue(_time(frame), transform)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set PathOffset")
    return {"status": "ok", "name": obj.GetName(), "position": value, "rotation_degrees": rotation, "frame": frame}


def set_path_state(args):
    has_position = "position" in args and isinstance(args.get("position"), (int, float)) and not isinstance(args.get("position"), bool)
    has_offset = "offset" in args or "rotation_degrees" in args or (
        "position" in args and isinstance(args.get("position"), dict)
    )
    if not has_position and not has_offset:
        raise ValueError("Provide position (0-1) and/or offset / rotation_degrees")
    result = {"status": "ok", "name": find_by_name(args["name"]).GetName()}
    if has_position:
        result["path_position"] = set_path_position(args)
    if has_offset:
        offset_args = dict(args)
        if "offset" in args:
            offset_args["position"] = args["offset"]
        elif isinstance(args.get("position"), (int, float)):
            offset_args.pop("position", None)
        result["path_offset"] = set_path_offset(offset_args)
    return result


def clear_path_keys(args):
    if args.get("confirm") != "DELETE_PATH_KEYS":
        raise ValueError("confirm must be DELETE_PATH_KEYS")
    obj = find_by_name(args["name"])
    cleared = []
    for key in ("PathPosition", "PathOffset"):
        control = obj.GetControl(key)
        if control is not None:
            result = control.ClearKeys()
            if result != RLPy.RStatus.Success:
                raise RuntimeError("iClone could not clear %s keys" % key)
            cleared.append(key)
    return {"status": "ok", "name": obj.GetName(), "cleared_controls": cleared}


def register(registry):
    registry["create_path"] = {
        "handler": create_path,
        "main_thread": True,
        "description": "Create a path from world-space XYZ control points, optionally set walkway width, and select a control point.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "points": {
                    "type": "array",
                    "minItems": 2,
                    "items": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "z": {"type": "number"},
                        },
                        "required": ["x", "y", "z"],
                    },
                },
                "name": {"type": "string"},
                "width": {"type": "number", "minimum": 0},
                "select_control_point": {"type": "integer", "minimum": 0},
            },
            "required": ["points"],
        },
    }
    registry["get_path_info"] = {
        "handler": get_path_info,
        "main_thread": True,
        "read_only": True,
        "description": "Inspect a path width, linked path, controls, and bounds, or list all paths when name is omitted.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "frame": {"type": "integer", "minimum": 0}},
        },
    }
    registry["set_path_width"] = {
        "advertise": False,
        "handler": set_path_width,
        "main_thread": True,
        "description": "Set the walkway width through the RIPath Python API.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "width": {"type": "number", "minimum": 0},
            },
            "required": ["name", "width"],
        },
    }
    registry["select_path_control_point"] = {
        "advertise": False,
        "handler": select_path_control_point,
        "main_thread": True,
        "description": "Enter walkway edit mode and select one path control point.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "control_point": {"type": "integer", "minimum": 0},
            },
            "required": ["name", "control_point"],
        },
    }
    registry["reproduce_walkway_path_gizmo"] = {
        "handler": reproduce_walkway_path_gizmo,
        "main_thread": True,
        "description": "Reproduce Mantis 99804: create a walkway, set width, enter walkway edit mode, and select a control point.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "points": {"type": "array", "minItems": 2},
                "name": {"type": "string"},
                "width": {"type": "number", "minimum": 0},
                "select_control_point": {"type": "integer", "minimum": 0},
            },
        },
    }
    registry["follow_path"] = {
        "handler": follow_path,
        "main_thread": True,
        "description": "Attach or release an object on a path (action attach|release).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "action": {"type": "string", "enum": ["attach", "release"]},
                "path_name": {"type": "string"},
                "frame": {"type": "integer", "minimum": 0},
            },
            "required": ["name"],
        },
    }
    registry["set_path_state"] = {
        "handler": set_path_state,
        "main_thread": True,
        "description": "Set path position (0-1) and/or offset/rotation on an attached object.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "position": {},
                "offset": {"type": "object"},
                "rotation_degrees": {"type": "object"},
                "frame": {"type": "integer", "minimum": 0},
            },
            "required": ["name"],
        },
    }
    registry["clear_path_keys"] = {
        "handler": clear_path_keys,
        "main_thread": True,
        "destructive": True,
        "description": "Clear PathPosition and PathOffset keys. Requires confirm DELETE_PATH_KEYS.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "confirm": {"type": "string", "enum": ["DELETE_PATH_KEYS"]},
            },
            "required": ["name", "confirm"],
        },
    }

    _hidden = {"advertise": False, "main_thread": True}
    registry["list_paths"] = dict(
        _hidden,
        handler=list_paths,
        read_only=True,
        description="List path objects in the scene.",
        inputSchema={"type": "object", "properties": {}},
    )
    registry["release_path"] = dict(
        _hidden,
        handler=release_path,
        description="Release an object from its path.",
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string"}, "frame": {"type": "integer", "minimum": 0}},
            "required": ["name"],
        },
    )
    registry["set_path_position"] = dict(
        _hidden,
        handler=set_path_position,
        description="Set normalized path position between 0 and 1.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "position": {"type": "number", "minimum": 0, "maximum": 1},
                "frame": {"type": "integer", "minimum": 0},
            },
            "required": ["name", "position"],
        },
    )
    registry["set_path_offset"] = dict(
        _hidden,
        handler=set_path_offset,
        description="Set path offset position/rotation.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "position": {"type": "object"},
                "rotation_degrees": {"type": "object"},
                "frame": {"type": "integer", "minimum": 0},
            },
            "required": ["name"],
        },
    )
