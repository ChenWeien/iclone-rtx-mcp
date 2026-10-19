import RLPy

from iclone_mcp_tool_objects import find_by_name


def _target(args):
    if args.get("name"):
        obj = find_by_name(args["name"])
    else:
        selected = RLPy.RScene.GetSelectedObjects()
        if not selected:
            raise ValueError("name is required when no object is selected")
        obj = selected[0]
    if obj.GetType() not in (RLPy.EObjectType_Prop, RLPy.EObjectType_Avatar):
        raise ValueError("Morphs are only supported on props and avatars")
    component = obj.GetMorphComponent()
    if component is None:
        raise RuntimeError("Object has no morph component")
    return obj, component


def list_morphs(args):
    obj, component = _target(args)
    morphs = []
    for mesh in obj.GetMeshNames():
        for name in component.GetMorphNames(mesh):
            morphs.append({"mesh": mesh, "name": name})
    return {"object": obj.GetName(), "morph_count": len(morphs), "morphs": morphs}


def get_morph_weight(args):
    obj, component = _target(args)
    value = component.GetWeight(args["mesh"], args["morph"], RLPy.RGlobal.GetTime(), 0.0)
    weight = value[1] if isinstance(value, tuple) else value
    return {"object": obj.GetName(), "mesh": args["mesh"], "morph": args["morph"], "weight": weight}


def set_morph_weight(args):
    obj, component = _target(args)
    weight = float(args["weight"])
    result = component.AddKey(args["mesh"], args["morph"], RLPy.RGlobal.GetTime(), weight, False, False)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not add morph key")
    return {"status": "ok", "object": obj.GetName(), "mesh": args["mesh"], "morph": args["morph"], "weight": weight}


def morph_weight(args):
    action = (args.get("action") or "").lower()
    if action == "get":
        return get_morph_weight(args)
    if action == "set":
        return set_morph_weight(args)
    raise ValueError("action must be get or set")


def register(registry):
    target = {"name": {"type": "string", "description": "Prop or avatar (default: first selected object)."}}
    registry["list_morphs"] = {
        "handler": list_morphs,
        "main_thread": True,
        "read_only": True,
        "description": "List morphs available on an object, grouped by mesh.",
        "inputSchema": {"type": "object", "properties": target},
    }
    weight = dict(target)
    weight.update({
        "action": {"type": "string", "enum": ["get", "set"]},
        "mesh": {"type": "string"},
        "morph": {"type": "string"},
        "weight": {"type": "number"},
    })
    registry["morph_weight"] = {
        "handler": morph_weight,
        "main_thread": True,
        "description": "Get or set a morph weight at the current time (action get|set).",
        "inputSchema": {
            "type": "object",
            "properties": weight,
            "required": ["action", "mesh", "morph"],
        },
    }

    _hidden = {"advertise": False, "main_thread": True}
    get_schema = dict(target)
    get_schema.update({"mesh": {"type": "string"}, "morph": {"type": "string"}})
    registry["get_morph_weight"] = dict(
        _hidden,
        handler=get_morph_weight,
        read_only=True,
        description="Read morph weight at the current time.",
        inputSchema={"type": "object", "properties": get_schema, "required": ["mesh", "morph"]},
    )
    set_schema = dict(get_schema)
    set_schema["weight"] = {"type": "number"}
    registry["set_morph_weight"] = dict(
        _hidden,
        handler=set_morph_weight,
        description="Key a morph weight at the current time.",
        inputSchema={"type": "object", "properties": set_schema, "required": ["mesh", "morph", "weight"]},
    )
