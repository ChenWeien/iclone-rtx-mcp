import os

import RLPy

try:
    import RLPy2
except Exception:
    RLPy2 = None

from iclone_mcp_tool_objects import find_by_name


def _text(value):
    return str(value) if value is not None else ""


def _field(value, name, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _require_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a non-empty string" % name)
    return value.strip()


def _path(value, name, must_exist=False, directory=False):
    value = os.path.normpath(_require_text(value, name))
    if not os.path.isabs(value):
        raise ValueError("%s must be an absolute path" % name)
    if must_exist:
        valid = os.path.isdir(value) if directory else os.path.isfile(value)
        if not valid:
            raise FileNotFoundError("%s not found: %s" % (name, value))
    return value


def _content_manager():
    if RLPy2 is None or not hasattr(RLPy2, "ContentManager"):
        raise RuntimeError("RLPy2.ContentManager is not available in this iClone build")
    interface = RLPy2.ContentManager.GetInterface()
    if interface is None:
        raise RuntimeError("The iClone ContentManager interface is not available")
    return interface


def _search_manager():
    if RLPy2 is not None and hasattr(RLPy2, "ContentManagerSearch"):
        interface = RLPy2.ContentManagerSearch.GetInterface()
        if interface is not None:
            return interface
    application = getattr(RLPy, "RApplication", None)
    if application is None:
        raise RuntimeError("The iClone content search API is not available")
    return application


def _search_enum(enum_name, value, legacy_prefix):
    if isinstance(value, int) and not isinstance(value, bool):
        if RLPy2 is not None:
            enum_type = getattr(RLPy2, enum_name, None)
            if enum_type is not None:
                for member in dir(enum_type):
                    if not member.startswith("_") and getattr(enum_type, member) == value:
                        return getattr(enum_type, member)
        return value

    value = _require_text(value, enum_name).lower().replace("-", "_")
    aliases = {
        "econtentmanagersearchmode": {"smart": "Smart", "general": "General"},
        "econtentmanagersearchmaintab": {"marketplace": "Marketplace", "ai_studio": "AIStudio", "aistudio": "AIStudio"},
        "econtentmanagersearchsubtab": {"item": "Item", "pack": "Pack", "pack_items": "PackItems", "packitems": "PackItems"},
    }
    member_name = aliases[enum_name.lower()].get(value)
    if member_name is None:
        raise ValueError("Unknown %s: %s" % (enum_name, value))
    enum_type = getattr(RLPy2, enum_name, None) if RLPy2 is not None else None
    if enum_type is not None and hasattr(enum_type, member_name):
        return getattr(enum_type, member_name)
    legacy_name = "%s_%s" % (legacy_prefix, member_name)
    legacy_value = getattr(RLPy, legacy_name, None)
    if legacy_value is None:
        raise RuntimeError("%s is not exposed by this iClone build" % enum_name)
    return legacy_value


def _template_folder_type(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    value = _require_text(value, "folder_type")
    candidates = [value]
    if value.startswith("ETemplateRootFolder_"):
        candidates.insert(0, value[len("ETemplateRootFolder_"):])
    for candidate in candidates:
        for name in (candidate, candidate[:1].upper() + candidate[1:]):
            result = getattr(RLPy, "ETemplateRootFolder_" + name, None)
            if result is not None:
                return result
    raise ValueError("Unknown folder_type: %s" % value)


def _category(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    value = _require_text(value, "base_category").lower().replace("-", "_")
    aliases = {
        "cc_stage_imodel": "CC_STAGE_IMODEL",
        "ic_media_imodel": "IC_MEDIA_IMODEL",
    }
    member = aliases.get(value)
    enum_type = getattr(RLPy2, "RAPCategoryID", None) if RLPy2 is not None else None
    if member is None or enum_type is None or not hasattr(enum_type, member):
        raise ValueError("Unknown base_category: %s" % value)
    return getattr(enum_type, member)


def _container_items(container):
    result = []
    try:
        for item in container:
            if isinstance(item, (tuple, list)) and len(item) == 2:
                result.append((str(item[0]), item[1]))
            else:
                try:
                    result.append((str(item), container[item]))
                except Exception:
                    result.append((str(item), item))
    except TypeError:
        return result
    return result


def _item_info(item):
    return {
        "file_name": _text(_field(item, "strFileName", "")),
        "install_path": _text(_field(item, "strInstallPath", "")),
        "file_version": int(_field(item, "nFileVersion", 0)),
        "content_id": _text(_field(item, "strContentID", "")),
        "tags": [_text(tag) for tag in (_field(item, "kTags", []) or [])],
    }


def _pack_info(pack):
    return {
        "content_id": _text(_field(pack, "strPackContentID", "")),
        "name": _text(_field(pack, "strPackName", "")),
        "local_thumbnail_url": _text(_field(pack, "strLocalThumbnailUrl", "")),
        "web_thumbnail_url": _text(_field(pack, "strWebThumbnailUrl", "")),
        "store_url": _text(_field(pack, "strStoreUrl", "")),
        "item_content_ids": [_text(cid) for cid in (_field(pack, "kItemInPackCIDs", []) or [])],
    }


def _search_result(result):
    return {
        "content_id": _text(_field(result, "content_id", _field(result, "strContentID", ""))),
        "display_name": _text(_field(result, "display_name", _field(result, "strDisplayName", ""))),
        "thumbnail_url": _text(_field(result, "thumbnail_url", _field(result, "strThumbnailUrl", ""))),
        "is_pack": bool(_field(result, "is_pack", _field(result, "bIsPack", False))),
        "is_installed": bool(_field(result, "is_installed", _field(result, "bIsInstalled", False))),
        "is_purchased": bool(_field(result, "is_purchased", _field(result, "bIsPurchased", False))),
        "is_content_triable": bool(_field(result, "is_content_triable", _field(result, "bIsContentTriable", False))),
        "is_expired": bool(_field(result, "is_expired", _field(result, "bIsExpired", False))),
        "is_item_of_pack_triable": bool(_field(result, "is_item_of_pack_triable", _field(result, "bIsItemOfPackTriable", False))),
        "metadata_prepared": bool(_field(result, "metadata_prepared", _field(result, "bMetaDataPrepared", False))),
        "index": int(_field(result, "index", _field(result, "nIndex", -1))),
    }


def _search_state(interface):
    pagination = interface.GetSearchPaginationInfo()
    results = interface.GetSearchResultSnapshot()
    return {
        "count": int(interface.GetSearchResultCount()),
        "pagination": {
            "page": int(_field(pagination, "page", _field(pagination, "nPage", 0))),
            "page_size": int(_field(pagination, "page_size", _field(pagination, "nPageSize", 0))),
            "total": int(_field(pagination, "total", _field(pagination, "nTotal", 0))),
            "page_count": int(_field(pagination, "page_count", _field(pagination, "nPageCount", 0))),
        },
        "results": [_search_result(result) for result in results],
    }


def get_content_paths(args):
    folder_type = _template_folder_type(args["folder_type"])
    application = RLPy.RApplication
    return {
        "folder_type": args["folder_type"],
        "default_path": _text(application.GetDefaultContentFolder(folder_type)),
        "custom_path": _text(application.GetCustomContentFolder(folder_type)),
    }


def get_content_id(args):
    path = _path(args["path"], "path", must_exist=True)
    return {"path": path, "content_id": _text(RLPy.RApplication.GetContentId(path))}


def resolve_content_paths(args):
    content_ids = args.get("content_ids")
    if not isinstance(content_ids, list) or not content_ids:
        raise ValueError("content_ids must contain at least one content ID")
    content_ids = [_require_text(cid, "content_id") for cid in content_ids]

    if RLPy2 is not None and hasattr(RLPy2, "ContentManager"):
        interface = _content_manager()
        ids = RLPy2.RArrayListWString()
        for content_id in content_ids:
            ids.Add(content_id)
        paths = RLPy2.RMapWStr2WStr()
        interface.QueryFilePathByContentID(ids, paths)
        result = {content_id: "" for content_id in content_ids}
        result.update({key: _text(value) for key, value in _container_items(paths)})
        return {"paths": result}

    result = {}
    for content_id in content_ids:
        result[content_id] = _text(RLPy.RApplication.GetFilePathByContentID(content_id))
    return {"paths": result}


def search_content(args):
    action = (args.get("action") or "search").lower()
    if action == "page":
        return get_content_search_results(args)
    if action != "search":
        raise ValueError("action must be search or page")

    has_text = bool(args.get("search_text"))
    has_image = bool(args.get("image_path"))
    if has_text == has_image:
        raise ValueError("Pass exactly one of search_text or image_path")

    interface = _search_manager()
    mode = _search_enum("EContentManagerSearchMode", args.get("search_mode", "smart"), "EContentManagerSearchMode")
    main_tab = _search_enum("EContentManagerSearchMainTab", args.get("main_tab", "ai_studio"), "EContentManagerSearchMainTab")
    sub_tab = _search_enum("EContentManagerSearchSubTab", args.get("sub_tab", "item"), "EContentManagerSearchSubTab")
    interface.SetSearchContext(mode, main_tab, sub_tab)
    if has_text:
        interface.ExecuteSearchByText(_require_text(args["search_text"], "search_text"))
    else:
        interface.ExecuteSearchByImage(_path(args["image_path"], "image_path", must_exist=True))

    timeout_ms = args.get("timeout_ms", 10000)
    if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or timeout_ms < 0:
        raise ValueError("timeout_ms must be a non-negative integer")
    completed = bool(interface.WaitForSearchFinish(timeout_ms))
    if "page" in args:
        interface.SetSearchPage(int(args["page"]))
    result = _search_state(interface)
    result.update({"completed": completed, "search_mode": args.get("search_mode", "smart")})
    return result


def get_content_search_results(args):
    interface = _search_manager()
    if "page" in args:
        page = args["page"]
        if isinstance(page, bool) or not isinstance(page, int) or page < 0:
            raise ValueError("page must be a non-negative integer")
        interface.SetSearchPage(page)
    return _search_state(interface)


def get_content_account(_args):
    interface = _content_manager()
    return {
        "logged_in": bool(interface.IsMemberLogIn()),
        "member_id": _text(interface.GetLoginMemberID()),
        "target_server": int(interface.GetTargetServer()),
    }


def get_motion_content_catalog(_args):
    interface = _content_manager()
    item_map = RLPy2.RMapWStr2RContentManagerItemInfo()
    pack_list = RLPy2.RArrayListRContentManagerPackInfo()
    loaded = bool(interface.GetAllMotionPackItemInfo(item_map, pack_list))
    return {
        "loaded": loaded,
        "items": {key: _item_info(value) for key, value in _container_items(item_map)},
        "packs": [_pack_info(pack) for pack in pack_list],
    }


def install_content(args):
    content_id = _require_text(args.get("content_id"), "content_id")
    if args.get("confirm") != "INSTALL_CONTENT":
        raise ValueError("confirm must be INSTALL_CONTENT")
    started = bool(_content_manager().InstallContent(content_id))
    return {"content_id": content_id, "started": started}


def show_content_folder(args):
    path = _require_text(args.get("path"), "path")
    shown = bool(_content_manager().ShowSGFolderByPath(path))
    return {"path": path, "shown": shown}


def open_content_browser(args):
    if args.get("path"):
        return show_content_folder(args)
    info_type = getattr(RLPy2, "CContentBrowserInfo", None) if RLPy2 is not None else None
    if info_type is None:
        raise RuntimeError("CContentBrowserInfo is not exposed by this iClone build")
    info = info_type()
    info.eBaseCategory = _category(args.get("base_category", "ic_media_imodel"))
    for field, default, minimum in (("nWidth", 835, 1), ("nHeight", 750, 1), ("nX", -1, None), ("nY", -1, None)):
        value = args.get(field[1:].lower(), default)
        if isinstance(value, bool) or not isinstance(value, int) or (minimum is not None and value < minimum):
            raise ValueError("%s must be an integer" % field[1:].lower())
        setattr(info, field, value)
    _content_manager().OpenContentBrowser(info)
    return {"opened": True, "base_category": args.get("base_category", "ic_media_imodel")}


def sync_custom_content_files(args):
    paths = args.get("paths")
    if not isinstance(paths, list) or not paths:
        raise ValueError("paths must contain at least one file path")
    if args.get("confirm") != "SYNC_CUSTOM_CONTENT_FILES":
        raise ValueError("confirm must be SYNC_CUSTOM_CONTENT_FILES")
    paths = [_path(value, "path", must_exist=True) for value in paths]
    file_paths = RLPy2.RArrayListWString()
    for path in paths:
        file_paths.Add(path)
    result_map = RLPy2.RMapWStr2WStr()
    synced = bool(_content_manager().SyncCustomFiles(file_paths, result_map))
    return {"synced": synced, "content_ids": {key: _text(value) for key, value in _container_items(result_map)}}


def _object(args):
    if args.get("object_id"):
        value = RLPy.RScene.QueryObjectByID(_require_text(args["object_id"], "object_id"))
        if value is None:
            raise ValueError("Object not found: %s" % args["object_id"])
        return value
    if args.get("name"):
        return find_by_name(args["name"])
    return None


def _load_option(value):
    value = value or "none"
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    name = str(value).lower().replace("-", "_")
    names = {"none": "None", "no_progress": "NoProgress"}
    member = names.get(name)
    option = getattr(RLPy, "ELoadFileOption__" + member, None) if member else None
    if option is None and member:
        option = getattr(RLPy, "ELoadFileOption_" + member, None)
    if option is None:
        raise ValueError("Unknown load_option: %s" % value)
    return option


def _scene_objects():
    objects = []
    seen = set()
    for constant_name in ("EObjectType_Object", "EObjectType_LensFlare"):
        object_type = getattr(RLPy, constant_name, None)
        if object_type is None:
            continue
        for value in RLPy.RScene.FindObjects(object_type) or []:
            object_id = str(value.GetID())
            if object_id not in seen:
                seen.add(object_id)
                objects.append(value)
    return objects


def load_file(args):
    kind = (args.get("kind") or "auto").lower().replace("-", "_")
    if kind not in {
        "auto",
        "fbx",
        "alembic",
        "motion",
        "facial_profile",
        "clothing",
        "vocal",
        "substance_textures",
    }:
        raise ValueError(
            "kind must be one of: auto, fbx, alembic, motion, facial_profile, clothing, vocal, substance_textures"
        )
    if kind == "fbx":
        from iclone_mcp_tool_fileio import load_fbx_file

        return load_fbx_file(args)
    if kind == "alembic":
        from iclone_mcp_tool_project import load_alembic

        return load_alembic(args)
    if kind == "motion":
        from iclone_mcp_tool_project import load_motion

        return load_motion(args)
    if kind == "facial_profile":
        from iclone_mcp_tool_fileio import load_facial_profile

        return load_facial_profile(args)
    if kind == "clothing":
        from iclone_mcp_tool_fileio import load_clothing_from_fbx

        return load_clothing_from_fbx(args)
    if kind == "vocal":
        from iclone_mcp_tool_facial import load_vocal

        return load_vocal(args)
    if kind == "substance_textures":
        from iclone_mcp_tool_project import load_substance_painter_textures

        return load_substance_painter_textures(args)

    path = args.get("path")
    content_id = args.get("content_id")
    if bool(path) == bool(content_id):
        raise ValueError("Pass exactly one of path or content_id")
    if content_id:
        content_id = _require_text(content_id, "content_id")
        resolved = resolve_content_paths({"content_ids": [content_id]})["paths"].get(content_id, "")
        if not resolved and args.get("install_if_missing"):
            if args.get("confirm") != "INSTALL_CONTENT":
                raise ValueError("confirm must be INSTALL_CONTENT when install_if_missing is true")
            if not bool(_content_manager().InstallContent(content_id)):
                raise RuntimeError("iClone could not start content installation")
            resolved = resolve_content_paths({"content_ids": [content_id]})["paths"].get(content_id, "")
            if not resolved:
                return {"status": "install_started", "loaded": False, "content_id": content_id}
        if not resolved:
            raise FileNotFoundError("Content is not installed: %s" % content_id)
        path = resolved
    path = _path(path, "path", must_exist=True)
    before = {str(value.GetID()) for value in _scene_objects()}
    target = _object(args)
    record_step = bool(args.get("record_step", True))
    option = _load_option(args.get("load_option"))
    has_extra = target is not None or "time_ms" in args or "frame" in args or args.get("load_option") is not None
    if has_extra:
        if "time_ms" in args:
            load_time = RLPy.RTime.FromValue(int(args["time_ms"]))
        elif "frame" in args:
            load_time = RLPy.RGlobal.GetFps().IndexedFrameTime(int(args["frame"]))
        else:
            load_time = RLPy.RTime.NEGATIVE_ONE
        status = RLPy.RFileIO.LoadFile(path, record_step, target, load_time, option)
    else:
        status = RLPy.RFileIO.LoadFile(path, record_step)
    if status != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not load the content")
    imported = [
        {"id": str(value.GetID()), "name": str(value.GetName())}
        for value in _scene_objects()
        if str(value.GetID()) not in before
    ]
    return {"status": "ok", "loaded": True, "path": path, "content_id": content_id or "", "imported_objects": imported}


def content_paths(args):
    action = (args.get("action") or "").lower()
    if action == "roots":
        return get_content_paths(args)
    if action == "list_folders":
        from iclone_mcp_tool_diagnostics import list_content_folders

        return list_content_folders(args)
    if action == "list_files":
        from iclone_mcp_tool_diagnostics import list_content_files

        return list_content_files(args)
    if action == "get_id":
        return get_content_id(args)
    if action == "resolve":
        return resolve_content_paths(args)
    raise ValueError("action must be one of: roots, list_folders, list_files, get_id, resolve")


def register(registry):
    registry["load_file"] = {
        "handler": load_file,
        "main_thread": True,
        "description": "Load a local file or content ID; set kind to route to specialized loaders.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content_id": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": [
                        "auto",
                        "fbx",
                        "alembic",
                        "motion",
                        "facial_profile",
                        "clothing",
                        "vocal",
                        "substance_textures",
                    ],
                },
                "install_if_missing": {"type": "boolean"},
                "confirm": {"type": "string", "enum": ["INSTALL_CONTENT"]},
                "object_id": {"type": "string"},
                "name": {"type": "string"},
                "avatar_name": {"type": "string"},
                "audio_path": {"type": "string"},
                "clip_name": {"type": "string"},
                "start_frame": {"type": "integer", "minimum": 0},
                "record_step": {"type": "boolean"},
                "time_ms": {"type": "integer", "minimum": 0},
                "frame": {"type": "integer", "minimum": 0},
                "load_option": {"type": "string", "enum": ["none", "no_progress"]},
                "import_option": {"type": "string"},
                "up_axis": {"type": "string"},
                "keep_eye_blink_jaw_open": {"type": "boolean"},
            },
        },
    }
    registry["search_content"] = {
        "handler": search_content,
        "main_thread": True,
        "read_only": True,
        "description": "Search content (action search) or page existing results (action page).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["search", "page"]},
                "search_text": {"type": "string"},
                "image_path": {"type": "string"},
                "search_mode": {"type": "string", "enum": ["smart", "general"]},
                "main_tab": {"type": "string", "enum": ["marketplace", "ai_studio"]},
                "sub_tab": {"type": "string", "enum": ["item", "pack", "pack_items"]},
                "timeout_ms": {"type": "integer", "minimum": 0},
                "page": {"type": "integer", "minimum": 0},
            },
        },
    }
    registry["content_paths"] = {
        "handler": content_paths,
        "main_thread": True,
        "read_only": True,
        "description": "Content path helpers: roots|list_folders|list_files|get_id|resolve.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["roots", "list_folders", "list_files", "get_id", "resolve"],
                },
                "folder_type": {"type": "string"},
                "parent": {"type": "string"},
                "path": {"type": "string"},
                "content_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["action"],
        },
    }
    registry["open_content_browser"] = {
        "handler": open_content_browser,
        "main_thread": True,
        "description": "Open the content browser, or show a Smart Content folder when path is set.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "base_category": {"type": "string", "enum": ["cc_stage_imodel", "ic_media_imodel"]},
                "width": {"type": "integer", "minimum": 1},
                "height": {"type": "integer", "minimum": 1},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            },
        },
    }
    registry["get_content_account"] = {
        "handler": get_content_account,
        "main_thread": True,
        "read_only": True,
        "description": "Return ContentManager login and target-server state.",
        "inputSchema": {"type": "object", "properties": {}},
    }
    registry["get_motion_content_catalog"] = {
        "handler": get_motion_content_catalog,
        "main_thread": True,
        "read_only": True,
        "description": "Return motion content item and pack metadata.",
        "inputSchema": {"type": "object", "properties": {}},
    }
    registry["install_content"] = {
        "handler": install_content,
        "main_thread": True,
        "destructive": True,
        "description": "Start installation of a content item or pack. Confirmation required.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content_id": {"type": "string"},
                "confirm": {"type": "string", "enum": ["INSTALL_CONTENT"]},
            },
            "required": ["content_id", "confirm"],
        },
    }
    registry["sync_custom_content_files"] = {
        "handler": sync_custom_content_files,
        "main_thread": True,
        "destructive": True,
        "description": "Synchronize local custom content files. Confirmation required.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}},
                "confirm": {"type": "string", "enum": ["SYNC_CUSTOM_CONTENT_FILES"]},
            },
            "required": ["paths", "confirm"],
        },
    }

    _hidden = {"advertise": False, "main_thread": True}
    registry["get_content_paths"] = dict(
        _hidden,
        handler=get_content_paths,
        read_only=True,
        description="Return default and custom content paths for a folder type.",
        inputSchema={"type": "object", "properties": {"folder_type": {"type": "string"}}, "required": ["folder_type"]},
    )
    registry["get_content_id"] = dict(
        _hidden,
        handler=get_content_id,
        read_only=True,
        description="Resolve a content file path to its content ID.",
        inputSchema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    )
    registry["resolve_content_paths"] = dict(
        _hidden,
        handler=resolve_content_paths,
        read_only=True,
        description="Resolve content IDs to local file paths.",
        inputSchema={
            "type": "object",
            "properties": {"content_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["content_ids"],
        },
    )
    registry["get_content_search_results"] = dict(
        _hidden,
        handler=get_content_search_results,
        read_only=True,
        description="Read the current content-search page.",
        inputSchema={"type": "object", "properties": {"page": {"type": "integer", "minimum": 0}}},
    )
    registry["show_content_folder"] = dict(
        _hidden,
        handler=show_content_folder,
        description="Show a Smart Content Manager folder path.",
        inputSchema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    )
