import os

import RLPy

from iclone_mcp_tool_objects import find_by_name


def _require_path(value, name, exists=False, directory=False):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a non-empty string" % name)
    value = os.path.normpath(value)
    if not os.path.isabs(value):
        raise ValueError("%s must be an absolute path" % name)
    if exists:
        valid = os.path.isdir(value) if directory else os.path.isfile(value)
        if not valid:
            raise FileNotFoundError("%s not found: %s" % (name, value))
    return value


def _require_parent(value, name):
    value = _require_path(value, name)
    parent = os.path.dirname(value)
    if not os.path.isdir(parent):
        raise FileNotFoundError("Output folder not found: %s" % parent)
    return value


def _enum(prefix, value, aliases=None, default=None):
    value = default if value is None else value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    text = str(value)
    direct = getattr(RLPy, text, None)
    if direct is not None:
        return direct
    aliases = aliases or {}
    key = text.lower().replace("-", "_").replace(" ", "_")
    member = aliases.get(key, text)
    candidates = [prefix + "_" + member, prefix + "__" + member]
    for candidate in candidates:
        result = getattr(RLPy, candidate, None)
        if result is not None:
            return result
    for name in dir(RLPy):
        if not name.startswith(prefix + "_"):
            continue
        suffix = name[len(prefix) + 1:].lower().replace("__", "_")
        if suffix == key or suffix == str(member).lower().replace(" ", "_"):
            return getattr(RLPy, name)
    raise ValueError("Unknown %s: %s" % (prefix, value))


def _flags(prefix, value):
    if value is None:
        value = []
    if not isinstance(value, list):
        value = [value]
    result = _enum(prefix, "None")
    for item in value:
        result |= _enum(prefix, item)
    return result


def _target(args, required=True):
    object_id = args.get("object_id")
    if object_id:
        object_id = str(object_id)
        target = RLPy.RScene.QueryObjectByID(object_id)
        if target is None:
            raise ValueError("Object not found: %s" % object_id)
        return target
    if args.get("name"):
        return find_by_name(args["name"])
    selected = RLPy.RScene.GetSelectedObjects()
    if len(selected) == 1:
        return selected[0]
    if required:
        raise ValueError("object_id or name is required unless exactly one object is selected")
    return None


def _targets(args):
    object_ids = args.get("object_ids")
    if object_ids is None:
        selected = list(RLPy.RScene.GetSelectedObjects())
        if not selected:
            raise ValueError("object_ids is required unless objects are selected")
        return selected
    if not isinstance(object_ids, list) or not object_ids:
        raise ValueError("object_ids must contain at least one object ID")
    result = []
    for object_id in object_ids:
        target = RLPy.RScene.QueryObjectByID(str(object_id))
        if target is None:
            raise ValueError("Object not found: %s" % object_id)
        result.append(target)
    return result


def _status(result, operation):
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not %s" % operation)
    return {"status": "ok"}


def _time(value, default_zero=False):
    if value is None:
        return RLPy.RTime.ZERO if default_zero else RLPy.RTime.NEGATIVE_ONE
    return RLPy.RTime.FromValue(int(value))


def load_fbx_file(args):
    path = _require_path(args["path"], "path", exists=True)
    option = _enum(
        "EImportFbxOption",
        args.get("import_option", "none"),
        {"none": "None", "standard_human_character": "StandardHumanCharacter", "humanoid": "Humanoid", "creature": "Creature", "prop": "Prop"},
    )
    key_path = args.get("fbx_key_path", "")
    nude_path = args.get("nude_template_path", "")
    if key_path:
        key_path = _require_path(key_path, "fbx_key_path", exists=True)
    if nude_path:
        nude_path = _require_path(nude_path, "nude_template_path", exists=True)
    result = RLPy.RFileIO.LoadFbxFile(path, option, key_path, nude_path, bool(args.get("record_step", True)))
    response = _status(result, "load FBX")
    response.update({"path": path})
    return response


def load_clothing_from_fbx(args):
    avatar = _target(args)
    path = _require_path(args["path"], "path", exists=True)
    failed = RLPy.WStringVector()
    result = RLPy.RFileIO.LoadClotheFromFbx(avatar, path, failed)
    response = _status(result, "load clothing from FBX")
    response.update({"object_id": str(avatar.GetID()), "path": path, "failed_meshes": [str(value) for value in failed]})
    return response


def load_facial_profile(args):
    path = _require_path(args["path"], "path", exists=True)
    target = _target(args, required=False)
    result = RLPy.RFileIO.LoadFacialProfile(
        path,
        target,
        bool(args.get("record_step", True)),
        bool(args.get("keep_eye_blink_jaw_open", False)),
    )
    response = _status(result, "load facial profile")
    response.update({"path": path, "object_id": str(target.GetID()) if target is not None else None})
    return response


def _fbx_setting(args, setting=None):
    setting = setting or RLPy.RExportFbxSetting()
    fields = (
        ("export_motion", "EnableExportMotion", bool),
        ("bake_diffuse_specular_from_shader", "EnableBakeDiffuseSpecularFromShader", bool),
        ("bake_diffuse_from_skin_color", "EnableBakeDiffuseFromSkinColor", bool),
        ("basic_bind_pose", "EnableBasicBindPose", bool),
        ("bake_subdivision", "EnableBakeSubdivision", bool),
        ("embed_timecode", "SetEmbedTimecode", bool),
        ("export_level", "SetExportLevel", int),
        ("include_motion_path", "SetIncludeMotionPath", str),
    )
    for name, setter, converter in fields:
        if name in args:
            getattr(setting, setter)(converter(args[name]))
    if "export_motion_fps" in args:
        fps = RLPy.RFps.FromFloat(float(args["export_motion_fps"])) if hasattr(RLPy.RFps, "FromFloat") else RLPy.RFps(float(args["export_motion_fps"]))
        setting.SetExportMotionFps(fps)
    if "export_motion_range" in args:
        value = args["export_motion_range"]
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError("export_motion_range must contain [start_frame, end_frame]")
        setting.SetExportMotionRange((int(value[0]), int(value[1])))
    if "option" in args:
        setting.SetOption(_flags("EExportFbxOptions", args["option"]))
    if "option2" in args:
        setting.SetOption2(_flags("EExportFbxOptions2", args["option2"]))
    if "option3" in args:
        setting.SetOption3(_flags("EExportFbxOptions3", args["option3"]))
    if "texture_size" in args:
        setting.SetTextureSize(_enum("EExportTextureSize", args["texture_size"], {"original": "Original"}))
    if "texture_format" in args:
        setting.SetTextureFormat(_enum("EExportTextureFormat", args["texture_format"]))
    if "unreal_bone_structure" in args:
        setting.SetUnrealBoneStructure(_enum("EUnrealBoneStructure", args["unreal_bone_structure"]))
    return setting


def export_fbx(args):
    target = _target(args)
    path = _require_parent(args["path"], "path")
    method = getattr(RLPy.RFileIO, "ExportFbxFile", None)
    if method is None:
        raise RuntimeError("ExportFbxFile is not exposed by this iClone 8 build")
    if isinstance(args.get("settings"), dict):
        settings = dict(args["settings"])
        result = method(target, path, _fbx_setting(settings))
    else:
        result = method(
            target,
            path,
            _flags("EExportFbxOptions", args.get("option")),
            _flags("EExportFbxOptions2", args.get("option2")),
            _flags("EExportFbxOptions3", args.get("option3")),
            _enum("EExportTextureSize", args.get("texture_size", "original"), {"original": "Original"}),
            _enum("EExportTextureFormat", args.get("texture_format", "default")),
            args.get("include_motion_path", ""),
        )
    response = _status(result, "export FBX")
    response.update({"object_id": str(target.GetID()), "path": path})
    return response


def is_compatible_with_export_option(args):
    target = _target(args)
    method = getattr(RLPy.RFileIO, "IsCompatibleWithExportOption", None)
    if method is None:
        raise RuntimeError("IsCompatibleWithExportOption is not exposed by this iClone 8 build")
    result = method(target, _fbx_setting(args.get("settings", args)))
    return {"object_id": str(target.GetID()), "compatible": bool(result)}


def check_export_fbx_license(args):
    target = _target(args)
    method = getattr(RLPy.RFileIO, "CheckExportFbxHasLicense", None)
    if method is None:
        raise RuntimeError("CheckExportFbxHasLicense is not exposed by this iClone 8 build")
    return {"object_id": str(target.GetID()), "licensed": bool(method(target))}


def export_obj(args):
    target = _target(args)
    path = _require_parent(args["path"], "path")
    method = getattr(RLPy.RFileIO, "ExportObjFile", None)
    if method is None:
        raise RuntimeError("ExportObjFile is not exposed by this iClone 8 build")
    option = _flags("EExport3DFileOption", args.get("option"))
    pose_path = args.get("pose_path", "")
    if pose_path:
        pose_path = _require_path(pose_path, "pose_path", exists=True)
    result = method(target, path, option, pose_path)
    response = _status(result, "export OBJ")
    response.update({"object_id": str(target.GetID()), "path": path})
    return response


def export_glb(args):
    target = _target(args)
    path = _require_parent(args["path"], "path")
    method = getattr(RLPy.RFileIO, "ExportGlbFile", None)
    if method is None:
        raise RuntimeError("ExportGlbFile is not exposed by this iClone 8 build")
    setting = _fbx_setting(args.get("settings", args), RLPy.RExportGlbSetting())
    if "mesh_motion_mode" in args:
        setting.SetMeshMotionMode(_enum("EExportMeshMotionMode", args["mesh_motion_mode"]))
    result = method(target, path, setting)
    response = _status(result, "export GLB")
    response.update({"object_id": str(target.GetID()), "path": path})
    return response


def save_file(args):
    target = _target(args)
    path = _require_parent(args["path"], "path")
    setting = RLPy.RSaveFileSetting()
    setting.SetSaveType(_enum("ESaveFileType", args.get("save_type", "motion")))
    if "start_time_ms" in args or "end_time_ms" in args:
        setting.SetSaveRange(_time(args.get("start_time_ms"), True), _time(args.get("end_time_ms"), True))
    if "motion_plus" in args:
        options = args["motion_plus"]
        motion_plus = RLPy.RSaveMotionPlusOption()
        motion_plus.SetMotionPlusOption(_flags("ESaveMotionPlusOption", options.get("data_flags")))
        motion_plus.SetMotionClipOption(_flags("ESaveMotionClipOption", options.get("clip_flags")))
        for name, setter, converter in (("save_timecode", "SetSaveTimecode", bool), ("timecode_start_time", "SetTimecodeStartTime", float), ("timecode_fps", "SetTimecodeFps", float)):
            if name in options:
                getattr(motion_plus, setter)(converter(options[name]))
        setting.SetSaveFileOption(motion_plus)
    elif "facial_animation_flags" in args:
        facial = RLPy.RSaveFacialAnimationOption()
        facial.SetFlag(_flags("ESaveFacialAnimationOption", args["facial_animation_flags"]))
        setting.SetSaveFileOption(facial)
    response = _status(RLPy.RFileIO.SaveFile(target, setting, path), "save file")
    response.update({"object_id": str(target.GetID()), "path": path})
    return response


def export_usd(args):
    path = _require_parent(args["path"], "path")
    prime_name = str(args.get("prime_name", ""))
    options = RLPy.RSUsdExportOption()
    for name in ("bOmni", "bTurnYUp", "bIncludeLight", "bIncludeIbl", "bIncludeSwitchCamera", "bDeleteHiddenFace", "bMultiMotion", "bMotionOnly", "bExportSelected", "bCharacterOnly", "bStaticMesh", "bIncludeMotion", "iMaxTextureSize", "iFps", "bOnlyIkBoneAnimation", "bRemoveFacialBoneAnimation", "bExportA2fMesh", "bBakeSubdivision", "bExportOrmTexture"):
        if name in args.get("options", {}):
            setattr(options, name, args["options"][name])
    result = RLPy.RFileIO.ExportUsdFile(
        path,
        prime_name,
        float(args.get("meter_per_unit", 0.01)),
        _enum("EMaterialType", args.get("material_type", "RTX_Real_Time")),
        _enum("EIncludeMotionType", args.get("include_motion_type", "Current_Pose")),
        _enum("EPostEffect", args.get("post_effect", "None")),
        options,
    )
    return dict(_status(result, "export USD"), path=path)


def _goz_option(value):
    value = value or {}
    option = RLPy.RExportGoZMeshOption()
    option.bIsCreate = bool(value.get("is_create", False))
    option.ePose = _enum("EExportGoZPose", value.get("pose", "current"), {"current": "Current", "t_pose": "TPose", "a_pose": "APose"})
    option.bDoScale = bool(value.get("do_scale", False))
    option.strPoseFilePath = value.get("pose_file_path", "")
    if option.strPoseFilePath:
        option.strPoseFilePath = _require_path(option.strPoseFilePath, "pose_file_path", exists=True)
    return option


def export_goz(args):
    folder = _require_path(args["folder_path"], "folder_path", exists=True, directory=True)
    result = RLPy.RFileIO.ExportGoZFile(_targets(args), folder, _goz_option(args.get("option")))
    return dict(_status(result, "export GoZ"), folder_path=folder)


def export_multi_pose_goz(args):
    folder = _require_path(args["folder_path"], "folder_path", exists=True, directory=True)
    poses = args.get("poses")
    if not isinstance(poses, list) or not poses:
        raise ValueError("poses must contain at least one pose")
    paths = RLPy.WStringVector()
    options = RLPy.RExportGoZMeshOptionVector()
    for pose in poses:
        output_path = _require_parent(pose["path"], "path")
        paths.append(output_path)
        options.append(_goz_option(pose.get("option")))
    result = RLPy.RFileIO.ExportMultiPoseGoZFile(_targets(args), paths, options)
    return dict(_status(result, "export multi-pose GoZ"), folder_path=folder)


def get_file_tags(args):
    path = _require_path(args["path"], "path", exists=True)
    tags = RLPy.WStringVector()
    result = RLPy.RFileIO.GetTagsFromFileHeader(path, tags, _enum("ETagType", args.get("tag_type", "developer")))
    response = _status(result, "read file tags")
    response.update({"path": path, "tags": [str(tag) for tag in tags]})
    return response


def export_bvh(args):
    target = _target(args)
    path = _require_parent(args["path"], "path")
    if any(name in args for name in ("start_time_ms", "end_time_ms", "sample_z", "y_up", "show_progress")):
        result = RLPy.RFileIO.ExportBvhFile2(
            target,
            path,
            _time(args.get("start_time_ms"), True),
            _time(args.get("end_time_ms"), True),
            bool(args.get("sample_z", True)),
            bool(args.get("y_up", True)),
            bool(args.get("show_progress", True)),
        )
    else:
        result = RLPy.RFileIO.ExportBvhFile(target, path)
    response = _status(result, "export BVH")
    response.update({"object_id": str(target.GetID()), "path": path})
    return response


def convert_fbx_to_rlmotion(args):
    source = _require_path(args["path"], "path", exists=True)
    output_folder = _require_path(args["output_folder"], "output_folder", exists=True, directory=True)
    tpose = args.get("tpose_path", "")
    thumbnail = args.get("thumbnail_path", "")
    if tpose:
        tpose = _require_path(tpose, "tpose_path", exists=True)
    if thumbnail:
        thumbnail = _require_path(thumbnail, "thumbnail_path", exists=True)
    result = RLPy.RFileIO.ConvertFbxFileToRLMotion(source, output_folder, tpose, thumbnail, float(args.get("thumbnail_seconds", 0.0)))
    return dict(_status(result, "convert FBX to RL motion"), path=source, output_folder=output_folder)


def output_default_preset_json(args):
    object_file = _require_path(args["object_file_name"], "object_file_name", exists=True)
    base_path = _require_path(args["base_path"], "base_path", exists=True, directory=True)
    return dict(_status(RLPy.RFileIO.OutputDefaultPresetJson(object_file, base_path), "write default preset JSON"), object_file_name=object_file, base_path=base_path)


def export_object(args):
    fmt = (args.get("format") or "").lower().replace("-", "_")
    if fmt == "fbx":
        return export_fbx(args)
    if fmt == "obj":
        return export_obj(args)
    if fmt == "glb":
        return export_glb(args)
    if fmt == "usd":
        return export_usd(args)
    if fmt == "bvh":
        return export_bvh(args)
    if fmt == "goz":
        return export_goz(args)
    if fmt in {"multi_pose_goz", "multipose_goz"}:
        return export_multi_pose_goz(args)
    raise ValueError("format must be one of: fbx, obj, glb, usd, bvh, goz, multi_pose_goz")


def get_export_capabilities(args):
    return {
        "compatibility": is_compatible_with_export_option(args),
        "fbx_license": check_export_fbx_license(args),
    }


def register(registry):
    registry["export_object"] = {
        "handler": export_object,
        "main_thread": True,
        "description": "Export an object or scene as fbx|obj|glb|usd|bvh|goz|multi_pose_goz.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["fbx", "obj", "glb", "usd", "bvh", "goz", "multi_pose_goz"],
                },
                "object_id": {"type": "string"},
                "object_ids": {"type": "array", "items": {"type": "string"}},
                "name": {"type": "string"},
                "path": {"type": "string"},
                "folder_path": {"type": "string"},
                "settings": {"type": "object"},
                "option": {},
                "option2": {"type": "array", "items": {"type": "string"}},
                "option3": {"type": "array", "items": {"type": "string"}},
                "texture_size": {"type": "string"},
                "texture_format": {"type": "string"},
                "include_motion_path": {"type": "string"},
                "pose_path": {"type": "string"},
                "mesh_motion_mode": {"type": "string"},
                "poses": {"type": "array", "items": {"type": "object"}},
                "prime_name": {"type": "string"},
                "meter_per_unit": {"type": "number"},
                "material_type": {"type": "string"},
                "include_motion_type": {"type": "string"},
                "post_effect": {"type": "string"},
                "options": {"type": "object"},
                "start_time_ms": {"type": "integer"},
                "end_time_ms": {"type": "integer"},
                "sample_z": {"type": "boolean"},
                "y_up": {"type": "boolean"},
                "show_progress": {"type": "boolean"},
            },
            "required": ["format"],
        },
    }
    registry["get_export_capabilities"] = {
        "handler": get_export_capabilities,
        "main_thread": True,
        "read_only": True,
        "description": "Check FBX export option compatibility and license for an object.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "name": {"type": "string"},
                "settings": {"type": "object"},
            },
        },
    }
    registry["save_file"] = {
        "handler": save_file,
        "main_thread": True,
        "description": "Save an object using RSaveFileSetting and optional motion or facial options.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "name": {"type": "string"},
                "path": {"type": "string"},
                "save_type": {"type": "string"},
                "start_time_ms": {"type": "integer"},
                "end_time_ms": {"type": "integer"},
                "motion_plus": {"type": "object"},
                "facial_animation_flags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["path"],
        },
    }
    registry["get_file_tags"] = {
        "handler": get_file_tags,
        "main_thread": True,
        "read_only": True,
        "description": "Read developer or user tags from an iClone file header.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "tag_type": {"type": "string", "enum": ["developer", "user"]},
            },
            "required": ["path"],
        },
    }
    registry["convert_fbx_to_rlmotion"] = {
        "handler": convert_fbx_to_rlmotion,
        "main_thread": True,
        "description": "Convert FBX animation to RL motion files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "output_folder": {"type": "string"},
                "tpose_path": {"type": "string"},
                "thumbnail_path": {"type": "string"},
                "thumbnail_seconds": {"type": "number"},
            },
            "required": ["path", "output_folder"],
        },
    }
    registry["output_default_preset_json"] = {
        "handler": output_default_preset_json,
        "main_thread": True,
        "description": "Write default preset JSON for an object file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_file_name": {"type": "string"},
                "base_path": {"type": "string"},
            },
            "required": ["object_file_name", "base_path"],
        },
    }

    _hidden = {"advertise": False, "main_thread": True}
    registry["load_fbx_file"] = dict(
        _hidden,
        handler=load_fbx_file,
        description="Load an FBX file through RFileIO.LoadFbxFile.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "import_option": {
                    "type": "string",
                    "enum": ["none", "standard_human_character", "humanoid", "creature", "prop"],
                },
                "fbx_key_path": {"type": "string"},
                "nude_template_path": {"type": "string"},
                "record_step": {"type": "boolean"},
            },
            "required": ["path"],
        },
    )
    registry["load_clothing_from_fbx"] = dict(
        _hidden,
        handler=load_clothing_from_fbx,
        description="Load clothing from FBX onto an avatar.",
        inputSchema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "name": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
    )
    registry["load_facial_profile"] = dict(
        _hidden,
        handler=load_facial_profile,
        description="Load a facial profile onto an optional target.",
        inputSchema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "name": {"type": "string"},
                "path": {"type": "string"},
                "record_step": {"type": "boolean"},
                "keep_eye_blink_jaw_open": {"type": "boolean"},
            },
            "required": ["path"],
        },
    )
    registry["is_compatible_with_export_option"] = dict(
        _hidden,
        handler=is_compatible_with_export_option,
        read_only=True,
        description="Check whether an object supports requested FBX export settings.",
        inputSchema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "name": {"type": "string"},
                "settings": {"type": "object"},
            },
        },
    )
    registry["check_export_fbx_license"] = dict(
        _hidden,
        handler=check_export_fbx_license,
        read_only=True,
        description="Check FBX export license for an object.",
        inputSchema={
            "type": "object",
            "properties": {"object_id": {"type": "string"}, "name": {"type": "string"}},
        },
    )
    registry["export_usd"] = dict(
        _hidden,
        handler=export_usd,
        description="Export the scene to USD.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "prime_name": {"type": "string"},
                "meter_per_unit": {"type": "number"},
                "material_type": {"type": "string"},
                "include_motion_type": {"type": "string"},
                "post_effect": {"type": "string"},
                "options": {"type": "object"},
            },
            "required": ["path"],
        },
    )
    registry["export_goz"] = dict(
        _hidden,
        handler=export_goz,
        description="Export selected or identified objects to GoZ.",
        inputSchema={
            "type": "object",
            "properties": {
                "object_ids": {"type": "array", "items": {"type": "string"}},
                "folder_path": {"type": "string"},
                "option": {"type": "object"},
            },
            "required": ["folder_path"],
        },
    )
    registry["export_multi_pose_goz"] = dict(
        _hidden,
        handler=export_multi_pose_goz,
        description="Export multiple GoZ poses.",
        inputSchema={
            "type": "object",
            "properties": {
                "object_ids": {"type": "array", "items": {"type": "string"}},
                "folder_path": {"type": "string"},
                "poses": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["folder_path", "poses"],
        },
    )
    registry["export_bvh"] = dict(
        _hidden,
        handler=export_bvh,
        description="Export an object to BVH.",
        inputSchema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "name": {"type": "string"},
                "path": {"type": "string"},
                "start_time_ms": {"type": "integer"},
                "end_time_ms": {"type": "integer"},
                "sample_z": {"type": "boolean"},
                "y_up": {"type": "boolean"},
                "show_progress": {"type": "boolean"},
            },
            "required": ["path"],
        },
    )
    registry["export_fbx"] = dict(
        _hidden,
        handler=export_fbx,
        description="Export an object to FBX.",
        inputSchema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "name": {"type": "string"},
                "path": {"type": "string"},
                "settings": {"type": "object"},
                "option": {"type": "array", "items": {"type": "string"}},
                "option2": {"type": "array", "items": {"type": "string"}},
                "option3": {"type": "array", "items": {"type": "string"}},
                "texture_size": {"type": "string"},
                "texture_format": {"type": "string"},
                "include_motion_path": {"type": "string"},
            },
            "required": ["path"],
        },
    )
    registry["export_obj"] = dict(
        _hidden,
        handler=export_obj,
        description="Export an object to OBJ.",
        inputSchema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "name": {"type": "string"},
                "path": {"type": "string"},
                "option": {"type": "array", "items": {"type": "string"}},
                "pose_path": {"type": "string"},
            },
            "required": ["path"],
        },
    )
    registry["export_glb"] = dict(
        _hidden,
        handler=export_glb,
        description="Export an object to GLB.",
        inputSchema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "name": {"type": "string"},
                "path": {"type": "string"},
                "settings": {"type": "object"},
                "mesh_motion_mode": {"type": "string"},
            },
            "required": ["path"],
        },
    )
