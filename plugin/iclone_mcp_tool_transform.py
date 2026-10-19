import math

import RLPy
from iclone_mcp_tool_objects import find_by_name


def get_transform(args):
    transform = find_by_name(args["name"]).LocalTransform()
    position, scale = transform.T(), transform.S()
    result = {
        "name": args["name"],
        "position": {"x": position.x, "y": position.y, "z": position.z},
        "scale": {"x": scale.x, "y": scale.y, "z": scale.z},
    }
    include = args.get("include") or []
    if isinstance(include, str):
        include = [include]
    include = [str(item).lower() for item in include]
    if "keys" in include:
        result["keys"] = get_transform_keys(args)
    if "bounds" in include:
        result["bounds"] = get_object_bounds(args)
    return result


def get_transform_keys(args):
    obj = find_by_name(args["name"])
    control = obj.GetControl("Transform")
    if control is None:
        raise RuntimeError("Object has no animable Transform control")
    fps = RLPy.RGlobal.GetFps()
    keys = []
    for index in range(int(control.GetKeyCount())):
        time = RLPy.RTime()
        result = control.GetKeyTimeAt(index, time)
        if result != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not read transform key %s" % index)
        milliseconds = int(round(RLPy.RTick.ToMilliSecond(time.ToInt())))
        keys.append({
            "index": index,
            "time_ms": milliseconds,
            "frame": int(fps.GetFrameIndex(time)),
        })
    return {
        "name": obj.GetName(),
        "has_keys": bool(keys),
        "key_count": len(keys),
        "keys": keys,
    }


def get_object_bounds(args):
    """Return the world-space bounding box exposed by RLPy.RIObject."""
    obj = find_by_name(args["name"])
    maximum = RLPy.RVector3()
    center = RLPy.RVector3()
    minimum = RLPy.RVector3()
    result = obj.GetBounds(maximum, center, minimum)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not read bounds for %s" % obj.GetName())
    return {
        "name": obj.GetName(),
        "min": {"x": minimum.x, "y": minimum.y, "z": minimum.z},
        "center": {"x": center.x, "y": center.y, "z": center.z},
        "max": {"x": maximum.x, "y": maximum.y, "z": maximum.z},
    }


def set_transform(args):
    obj = find_by_name(args["name"])
    current = obj.LocalTransform()
    pos, scale, rotation = current.T(), current.S(), current.R()
    if "position" in args:
        value = args["position"]
        pos = RLPy.RVector3(value.get("x", pos.x), value.get("y", pos.y), value.get("z", pos.z))
    if "scale" in args:
        value = args["scale"]
        scale = RLPy.RVector3(value.get("x", scale.x), value.get("y", scale.y), value.get("z", scale.z))
    if "rotation_degrees" in args:
        value = args["rotation_degrees"]
        matrix = RLPy.RMatrix3().FromEulerAngle(
            RLPy.EEulerOrder_XYZ,
            math.radians(value.get("x", 0)),
            math.radians(value.get("y", 0)),
            math.radians(value.get("z", 0)),
        )
        rotation = RLPy.RQuaternion()
        rotation.FromRotationMatrix(matrix)
    obj.GetControl("Transform").SetValue(RLPy.RGlobal.GetTime(), RLPy.RTransform(scale, rotation, pos))
    return get_transform({"name": obj.GetName()})


def delete_transform_key(args):
    obj = find_by_name(args["name"])
    control = obj.GetControl("Transform")
    if control is None:
        raise RuntimeError("Object has no animable Transform control")
    time = RLPy.RGlobal.GetFps().IndexedFrameTime(args["frame"])
    result = control.RemoveKey(time)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not remove transform key at frame %s" % args["frame"])
    return {"status": "ok", "name": obj.GetName(), "removed_frame": args["frame"]}


def _transform_control(name):
    obj = find_by_name(name)
    control = obj.GetControl("Transform")
    if control is None:
        raise RuntimeError("Object has no animable Transform control")
    return obj, control


def move_transform_key(args):
    obj, control = _transform_control(args["name"])
    fps = RLPy.RGlobal.GetFps()
    source = fps.IndexedFrameTime(args["frame"])
    offset = fps.IndexedFrameTime(args["offset_frames"])
    result = control.MoveKey(source, offset)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not move transform key")
    return {"status": "ok", "name": obj.GetName(), "frame": args["frame"], "offset_frames": args["offset_frames"]}


def set_transform_key_transition(args):
    obj, control = _transform_control(args["name"])
    transitions = {
        "linear": RLPy.ETransitionType_Linear,
        "step": RLPy.ETransitionType_Step,
        "ease_in": RLPy.ETransitionType_Ease_In,
        "ease_out": RLPy.ETransitionType_Ease_Out,
        "ease_in_out": RLPy.ETransitionType_Ease_In_Out,
    }
    transition = args.get("transition", "ease_in_out")
    if transition not in transitions:
        raise ValueError("Unsupported transition: %s" % transition)
    strength = float(args.get("strength", 50.0))
    if strength < 0 or strength > 100:
        raise ValueError("strength must be between 0 and 100")
    time = RLPy.RGlobal.GetFps().IndexedFrameTime(args["frame"])
    result = control.SetKeyTransition(time, transitions[transition], strength)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set transform key transition")
    return {"status": "ok", "name": obj.GetName(), "frame": args["frame"], "transition": transition, "strength": strength}


def clear_transform_keys(args):
    if args.get("confirm") != "DELETE_TRANSFORM_KEYS":
        raise ValueError("confirm must be DELETE_TRANSFORM_KEYS")
    obj, control = _transform_control(args["name"])
    result = control.ClearKeys()
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not clear transform keys")
    return {"status": "ok", "name": obj.GetName()}


def transform_key(args):
    action = (args.get("action") or "").lower()
    if action == "delete":
        return delete_transform_key(args)
    if action == "move":
        return move_transform_key(args)
    if action == "set_transition":
        return set_transform_key_transition(args)
    if action == "clear_all":
        return clear_transform_keys(args)
    raise ValueError("action must be one of: delete, move, set_transition, clear_all")


def register(registry):
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
    registry["get_transform"] = {
        "handler": get_transform,
        "main_thread": True,
        "read_only": True,
        "description": "Return position and scale; optionally include keys and/or bounds.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "include": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["keys", "bounds"]},
                },
            },
            "required": ["name"],
        },
    }
    registry["transform_key"] = {
        "handler": transform_key,
        "main_thread": True,
        "description": "Delete, move, set transition, or clear all transform keys (clear_all requires confirm).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "action": {"type": "string", "enum": ["delete", "move", "set_transition", "clear_all"]},
                "frame": {"type": "integer", "minimum": 0},
                "offset_frames": {"type": "integer"},
                "transition": {"type": "string", "enum": ["linear", "step", "ease_in", "ease_out", "ease_in_out"]},
                "strength": {"type": "number", "minimum": 0, "maximum": 100},
                "confirm": {"type": "string", "enum": ["DELETE_TRANSFORM_KEYS"]},
            },
            "required": ["name", "action"],
        },
    }

    # Popped by iclone_mcp_commands in favor of bridge-native set_transform; keep for local use.
    _hidden = {"advertise": False, "main_thread": True}
    registry["set_transform"] = dict(
        _hidden,
        handler=set_transform,
        description="Move, scale, and orient an object (bridge-native preferred).",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "position": {"type": "object"},
                "scale": {"type": "object"},
                "rotation_degrees": {"type": "object"},
            },
            "required": ["name"],
        },
    )
    registry["get_transform_keys"] = dict(
        _hidden,
        handler=get_transform_keys,
        read_only=True,
        description="List transform keys and frames.",
        inputSchema=schema,
    )
    registry["get_object_bounds"] = dict(
        _hidden,
        handler=get_object_bounds,
        read_only=True,
        description="Return world-space bounds for an object.",
        inputSchema=schema,
    )
    registry["delete_transform_key"] = dict(
        _hidden,
        handler=delete_transform_key,
        description="Remove a transform key at a frame.",
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string"}, "frame": {"type": "integer", "minimum": 0}},
            "required": ["name", "frame"],
        },
    )
    registry["move_transform_key"] = dict(
        _hidden,
        handler=move_transform_key,
        description="Move a transform key by a frame offset.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "frame": {"type": "integer", "minimum": 0},
                "offset_frames": {"type": "integer"},
            },
            "required": ["name", "frame", "offset_frames"],
        },
    )
    registry["set_transform_key_transition"] = dict(
        _hidden,
        handler=set_transform_key_transition,
        description="Set interpolation on a transform key.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "frame": {"type": "integer", "minimum": 0},
                "transition": {"type": "string", "enum": ["linear", "step", "ease_in", "ease_out", "ease_in_out"]},
                "strength": {"type": "number", "minimum": 0, "maximum": 100},
            },
            "required": ["name", "frame"],
        },
    )
    registry["clear_transform_keys"] = dict(
        _hidden,
        handler=clear_transform_keys,
        destructive=True,
        description="Clear all transform keys. Requires confirm DELETE_TRANSFORM_KEYS.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "confirm": {"type": "string", "enum": ["DELETE_TRANSFORM_KEYS"]},
            },
            "required": ["name", "confirm"],
        },
    )
