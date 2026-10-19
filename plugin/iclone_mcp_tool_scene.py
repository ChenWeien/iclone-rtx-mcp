import RLPy
from iclone_mcp_tool_objects import find_by_name


_TYPES = {
    "object": RLPy.EObjectType_Object,
    "avatar": RLPy.EObjectType_Avatar,
    "prop": RLPy.EObjectType_Prop,
    "camera": RLPy.EObjectType_Camera,
    "light": RLPy.EObjectType_Light,
    "particle": RLPy.EObjectType_Particle,
}
if hasattr(RLPy, "EObjectType_Path"):
    _TYPES["path"] = RLPy.EObjectType_Path
if hasattr(RLPy, "EObjectType_LensFlare"):
    _TYPES["lens_flare"] = RLPy.EObjectType_LensFlare


def _object_summary(obj):
    transform = obj.LocalTransform()
    position = transform.T()
    return {"id": obj.GetID(), "name": obj.GetName(), "type": obj.GetType(), "position": {"x": position.x, "y": position.y, "z": position.z}}


def list_objects(args):
    if args.get("selected_only"):
        return get_selection(args)
    object_type = args.get("type", "object").lower()
    if object_type not in _TYPES:
        raise ValueError("Unsupported object type: %s" % object_type)
    if object_type == "object":
        from iclone_mcp_commands import _all_objects
        objects = _all_objects()
    else:
        objects = RLPy.RScene.FindObjects(_TYPES[object_type])
    return {"objects": [_object_summary(obj) for obj in objects]}


def get_selection(_args):
    return {"objects": [_object_summary(obj) for obj in RLPy.RScene.GetSelectedObjects()]}


def select_object(args):
    name = args["name"]
    obj = find_by_name(name)
    RLPy.RScene.SelectObject(obj)
    return {"status": "ok", "name": obj.GetName()}


def set_visibility(args):
    obj = find_by_name(args["name"])
    result = obj.SetVisible(RLPy.RGlobal.GetTime(), args["visible"])
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not change visibility")
    return {"status": "ok", "name": obj.GetName(), "visible": args["visible"]}


def delete_object(args):
    from iclone_mcp_commands import _delete_object_by_name

    return _delete_object_by_name(args)


def clone_object(args):
    source = find_by_name(args["name"])
    clone = source.Clone()
    if clone is None:
        raise RuntimeError("iClone could not clone object")
    if args.get("new_name"):
        clone.SetName(args["new_name"])
    return _object_summary(clone)


def link_object(args):
    action = (args.get("action") or "link").lower()
    if action == "unlink":
        return unlink_object(args)
    if action != "link":
        raise ValueError("action must be link or unlink")
    obj = find_by_name(args["name"])
    target = find_by_name(args["target_name"])
    alignments = {
        "none": "ELinkObjectAlignType_None",
        "position": "ELinkObjectAlignType_Position",
        "position_and_rotation": "ELinkObjectAlignType_Position_And_Rotation",
    }
    alignment = args.get("alignment", "position_and_rotation")
    if alignment not in alignments:
        raise ValueError("Unsupported alignment: %s" % alignment)
    result = obj.LinkTo(target, getattr(RLPy, alignments[alignment]), RLPy.RGlobal.GetTime())
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not link object")
    return {"status": "ok", "name": obj.GetName(), "target": target.GetName(), "alignment": alignment, "action": "link"}


def unlink_object(args):
    obj = find_by_name(args["name"])
    result = obj.UnLink(RLPy.RGlobal.GetTime())
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not unlink object")
    return {"status": "ok", "name": obj.GetName(), "action": "unlink"}


def align_object(args):
    obj = find_by_name(args["name"])
    target = find_by_name(args["target_name"])
    axes = {
        "x": "EAlignAxis_X_AXIS",
        "y": "EAlignAxis_Y_AXIS",
        "z": "EAlignAxis_Z_AXIS",
        "rotation": "EAlignAxis_ROTATE_AXIZ",
    }
    axis = args.get("axis", "rotation")
    if axis not in axes:
        raise ValueError("Unsupported alignment axis: %s" % axis)
    result = obj.AlignTo(target, getattr(RLPy, axes[axis]), args.get("to_pivot", True))
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not align object")
    return {"status": "ok", "name": obj.GetName(), "target": target.GetName(), "axis": axis}


def set_static(args):
    obj = find_by_name(args["name"])
    result = obj.SetStatic(args["static"])
    if result is not None and result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not change static state")
    return {"status": "ok", "name": obj.GetName(), "static": args["static"]}


def set_object_state(args):
    if "visible" not in args and "static" not in args:
        raise ValueError("Provide visible and/or static")
    result = {"status": "ok", "name": find_by_name(args["name"]).GetName()}
    if "visible" in args:
        result["visibility"] = set_visibility(args)
    if "static" in args:
        result["static_state"] = set_static(args)
    return result


def register(registry):
    type_enum = list(_TYPES)
    registry["list_objects"] = {
        "handler": list_objects,
        "main_thread": True,
        "read_only": True,
        "description": "List scene objects, or only the current selection when selected_only is true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": type_enum},
                "selected_only": {"type": "boolean"},
            },
        },
    }
    registry["clone_object"] = {
        "handler": clone_object,
        "main_thread": True,
        "description": "Clone a scene object, optionally renaming the clone.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "new_name": {"type": "string"}},
            "required": ["name"],
        },
    }
    registry["align_object"] = {
        "handler": align_object,
        "main_thread": True,
        "description": "Align an object to a target on an axis or rotation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "target_name": {"type": "string"},
                "axis": {"type": "string", "enum": ["x", "y", "z", "rotation"]},
                "to_pivot": {"type": "boolean"},
            },
            "required": ["name", "target_name"],
        },
    }
    registry["link_object"] = {
        "handler": link_object,
        "main_thread": True,
        "description": "Link or unlink an object (action link|unlink).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "action": {"type": "string", "enum": ["link", "unlink"]},
                "target_name": {"type": "string"},
                "alignment": {"type": "string", "enum": ["none", "position", "position_and_rotation"]},
            },
            "required": ["name"],
        },
    }
    registry["set_object_state"] = {
        "handler": set_object_state,
        "main_thread": True,
        "description": "Set object visibility and/or static state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "visible": {"type": "boolean"},
                "static": {"type": "boolean"},
            },
            "required": ["name"],
        },
    }

    _hidden = {"advertise": False, "main_thread": True}
    registry["get_selection"] = dict(
        _hidden,
        handler=get_selection,
        read_only=True,
        description="Return the active selection.",
        inputSchema={"type": "object", "properties": {}},
    )
    registry["select_object"] = dict(
        _hidden,
        handler=select_object,
        description="Select one object by name. Prefer bridge select_objects.",
        inputSchema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    )
    registry["set_visibility"] = dict(
        _hidden,
        handler=set_visibility,
        description="Show or hide an object at the current time.",
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string"}, "visible": {"type": "boolean"}},
            "required": ["name", "visible"],
        },
    )
    registry["unlink_object"] = dict(
        _hidden,
        handler=unlink_object,
        description="Unlink an object from its parent link target.",
        inputSchema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    )
    registry["set_static"] = dict(
        _hidden,
        handler=set_static,
        description="Enable or disable static status on an object.",
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string"}, "static": {"type": "boolean"}},
            "required": ["name", "static"],
        },
    )
    registry["delete_object"] = dict(
        _hidden,
        handler=delete_object,
        destructive=True,
        description="Delete one object by name (bridge prefers delete_objects).",
        inputSchema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    )
