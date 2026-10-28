import os

import RLPy

from iclone_mcp_tool_avatar import _avatar


def _face(args):
    avatar = _avatar(args.get("avatar_name"))
    component = avatar.GetFaceComponent()
    if component is None:
        raise RuntimeError("Avatar has no facial component")
    return avatar, component


def _viseme(args):
    avatar = _avatar(args.get("avatar_name"))
    component = avatar.GetVisemeComponent()
    if component is None:
        raise RuntimeError("Avatar has no viseme component")
    return avatar, component


def get_face_info(args):
    avatar, face = _face(args)
    groups = list(face.GetExpressionGroups()) if hasattr(face, "GetExpressionGroups") else []
    expressions = {}
    for group in groups:
        expressions[str(group)] = list(face.GetExpressionNames(group))
    result = {
        "avatar": avatar.GetName(),
        "clip_count": face.GetClipCount() if hasattr(face, "GetClipCount") else None,
        "expression_groups": groups,
        "expressions": expressions,
        "expression_set_uid": face.GetExpressionSetUid() if hasattr(face, "GetExpressionSetUid") else None,
        "auto_blink_name": face.GetAutoBlinkName() if hasattr(face, "GetAutoBlinkName") else None,
        "auto_blink_names": list(face.GetAutoBlinkNames()) if hasattr(face, "GetAutoBlinkNames") else [],
        "strength": face.GetStrength() if hasattr(face, "GetStrength") else None,
    }
    if args.get("include_visemes"):
        result["visemes"] = get_viseme_info(args)
    return result


def set_auto_blink(args):
    avatar, face = _face(args)
    result = face.SetAutoBlinkName(args["name"])
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set the avatar auto-blink mode")
    return {"status": "ok", "avatar": avatar.GetName(), "auto_blink_name": args["name"]}


def set_face_expressiveness(args):
    avatar, face = _face(args)
    weight = float(args["weight"])
    if weight < 0 or weight > 100:
        raise ValueError("weight must be between 0 and 100")
    result = face.AddExpressivenessKey(RLPy.RGlobal.GetTime(), weight)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not add the expressiveness key")
    return {"status": "ok", "avatar": avatar.GetName(), "weight": weight}


def set_face_settings(args):
    if "auto_blink" not in args and "name" not in args and "expressiveness" not in args and "weight" not in args:
        raise ValueError("Provide auto_blink/name and/or expressiveness/weight")
    result = {"status": "ok", "avatar": _avatar(args.get("avatar_name")).GetName()}
    blink_name = args.get("auto_blink", args.get("name"))
    if blink_name is not None:
        blink_args = dict(args)
        blink_args["name"] = blink_name
        result["auto_blink"] = set_auto_blink(blink_args)
    weight = args.get("expressiveness", args.get("weight"))
    if weight is not None:
        weight_args = dict(args)
        weight_args["weight"] = weight
        result["expressiveness"] = set_face_expressiveness(weight_args)
    return result


def add_expression_keys(args):
    avatar, face = _face(args)
    expressions = args["expressions"]
    strengths = [float(value) for value in args["strengths"]]
    if not isinstance(expressions, list) or not expressions:
        raise ValueError("expressions must be a non-empty list")
    if len(strengths) % len(expressions) != 0:
        raise ValueError("strengths length must be a multiple of expressions length")
    if any(value < 0 or value > 100 for value in strengths):
        raise ValueError("expression strengths must be between 0 and 100")
    interval = RLPy.RTime.FromValue(int(args.get("interval_ms", 0)))
    try:
        face.BeginKeyEditing()
        result = face.AddExpressionKeys(RLPy.RGlobal.GetTime(), expressions, strengths, interval)
    finally:
        face.EndKeyEditing()
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not add expression keys")
    return {"status": "ok", "avatar": avatar.GetName(), "expressions": expressions, "strengths": strengths}


def get_viseme_info(args):
    avatar, viseme = _viseme(args)
    return {
        "avatar": avatar.GetName(),
        "clip_count": viseme.GetClipCount() if hasattr(viseme, "GetClipCount") else None,
        "viseme_names": list(viseme.GetVisemeNames()) if hasattr(viseme, "GetVisemeNames") else [],
        "viseme_bones": [bone.GetName() for bone in viseme.GetVisemeBones()] if hasattr(viseme, "GetVisemeBones") else [],
        "viseme_morph_weights": list(viseme.GetVisemeMorphWeights()) if hasattr(viseme, "GetVisemeMorphWeights") else [],
        "strength": viseme.GetStrength() if hasattr(viseme, "GetStrength") else None,
    }


def add_viseme_key(args):
    avatar, viseme = _viseme(args)
    key = RLPy.RVisemeKey(int(args["viseme_id"]), float(args.get("expressiveness", 50)))
    key.SetTime(RLPy.RGlobal.GetTime())
    result = viseme.AddVisemeKey(key)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not add the viseme key")
    return {"status": "ok", "avatar": avatar.GetName(), "viseme_id": int(args["viseme_id"]), "expressiveness": float(args.get("expressiveness", 50))}


def add_face_keys(args):
    kind = (args.get("kind") or "").lower()
    if kind == "expression":
        return add_expression_keys(args)
    if kind == "viseme":
        return add_viseme_key(args)
    raise ValueError("kind must be expression or viseme")


def load_vocal(args):
    avatar, viseme = _viseme(args)
    path = os.path.abspath(args["audio_path"])
    if not os.path.isfile(path):
        raise FileNotFoundError("Audio file not found: %s" % path)
    audio = RLPy.RAudio.CreateAudioObject()
    if audio.Load(path) != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not load the audio file")
    frame = int(args.get("start_frame", 0))
    time = RLPy.RGlobal.GetFps().IndexedFrameTime(frame)
    clip_name = args.get("clip_name", "MCP_Vocal")
    result = viseme.LoadVocal(audio, time, clip_name)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not create visemes from the audio")
    return {"status": "ok", "avatar": avatar.GetName(), "audio_path": path, "clip_name": clip_name, "start_frame": frame}


def register(registry):
    registry["get_face_info"] = {
        "handler": get_face_info,
        "main_thread": True,
        "read_only": True,
        "description": "Inspect facial expressions; optionally include viseme info.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "avatar_name": {"type": "string"},
                "include_visemes": {"type": "boolean"},
            },
        },
    }
    registry["set_face_settings"] = {
        "handler": set_face_settings,
        "main_thread": True,
        "description": "Set auto-blink and/or facial expressiveness.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "avatar_name": {"type": "string"},
                "auto_blink": {"type": "string"},
                "name": {"type": "string"},
                "expressiveness": {"type": "number", "minimum": 0, "maximum": 100},
                "weight": {"type": "number", "minimum": 0, "maximum": 100},
            },
        },
    }
    registry["add_face_keys"] = {
        "handler": add_face_keys,
        "main_thread": True,
        "description": "Add expression keys or a viseme key (kind expression|viseme).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "avatar_name": {"type": "string"},
                "kind": {"type": "string", "enum": ["expression", "viseme"]},
                "expressions": {"type": "array", "items": {"type": "string"}},
                "strengths": {"type": "array", "items": {"type": "number"}},
                "interval_ms": {"type": "integer", "minimum": 0},
                "viseme_id": {"type": "integer"},
                "expressiveness": {"type": "number", "minimum": 0, "maximum": 100},
            },
            "required": ["kind"],
        },
    }
    registry["load_vocal"] = {
        "handler": load_vocal,
        "main_thread": True,
        "description": "Load an audio file and create a viseme clip on an avatar.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "avatar_name": {"type": "string"},
                "audio_path": {"type": "string"},
                "clip_name": {"type": "string"},
                "start_frame": {"type": "integer", "minimum": 0},
            },
            "required": ["audio_path"],
        },
    }

    _hidden = {"advertise": False, "main_thread": True}
    registry["set_auto_blink"] = dict(
        _hidden,
        handler=set_auto_blink,
        description="Set avatar auto-blink mode.",
        inputSchema={
            "type": "object",
            "properties": {"avatar_name": {"type": "string"}, "name": {"type": "string"}},
            "required": ["name"],
        },
    )
    registry["set_face_expressiveness"] = dict(
        _hidden,
        handler=set_face_expressiveness,
        description="Add a facial expressiveness key.",
        inputSchema={
            "type": "object",
            "properties": {
                "avatar_name": {"type": "string"},
                "weight": {"type": "number", "minimum": 0, "maximum": 100},
            },
            "required": ["weight"],
        },
    )
    registry["add_expression_keys"] = dict(
        _hidden,
        handler=add_expression_keys,
        description="Add facial expression keys.",
        inputSchema={
            "type": "object",
            "properties": {
                "avatar_name": {"type": "string"},
                "expressions": {"type": "array", "items": {"type": "string"}},
                "strengths": {"type": "array", "items": {"type": "number"}},
                "interval_ms": {"type": "integer", "minimum": 0},
            },
            "required": ["expressions", "strengths"],
        },
    )
    registry["get_viseme_info"] = dict(
        _hidden,
        handler=get_viseme_info,
        read_only=True,
        description="Inspect viseme availability on an avatar.",
        inputSchema={"type": "object", "properties": {"avatar_name": {"type": "string"}}},
    )
    registry["add_viseme_key"] = dict(
        _hidden,
        handler=add_viseme_key,
        description="Add a viseme key at the current frame.",
        inputSchema={
            "type": "object",
            "properties": {
                "avatar_name": {"type": "string"},
                "viseme_id": {"type": "integer"},
                "expressiveness": {"type": "number", "minimum": 0, "maximum": 100},
            },
            "required": ["viseme_id"],
        },
    )
