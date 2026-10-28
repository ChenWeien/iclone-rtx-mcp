from __future__ import print_function

import math
import os
import sys
import time

import RLPy


PROTOCOL_VERSION = 1
INITIALIZATION_GRACE_SECONDS = 0
_ready_at = 0.0
SUPPORTED_EXTENSIONS = {
    ".iavatar",
    ".ccavatar",
    ".iacc",
    ".ccacc",
    ".iprop",
    ".imdprop",
    ".iimglayer",
    ".ilight",
    ".icam",
    ".cccam",
    ".iparticle",
    ".ipkfx",
    ".ilflare",
    ".italk",
    ".imd",
    ".imtlplus",
    ".imtl",
    ".iscene",
    ".ieffect",
    ".iatm",
    ".igrass",
    ".isky",
    ".ipath",
    ".ibuilding",
    ".itree",
    ".iactorgroup",
    ".ianim",
    ".ibuildingconfig",
    ".icloth",
    ".iconstraint",
    ".ies",
    ".ieye",
    ".ihair",
    ".ihand",
    ".imddata",
    ".imdext",
    ".imdturntostop",
    ".imodel",
    ".imograph",
    ".imotion",
    ".imotionplus",
    ".ipose",
    ".iproject",
    ".ipynb",
    ".iscript",
    ".ishoe",
    ".isubstance",
    ".isubstancesourcemap",
    ".iteeth",
    ".iterrain",
    ".itol",
    ".iwater",
    ".obj",
    ".fbx",
}

_TYPE_CONSTANTS = (
    ("Avatar", "EObjectType_Avatar"),
    ("Hair", "EObjectType_Hair"),
    ("Cloth", "EObjectType_Cloth"),
    ("Accessory", "EObjectType_Accessory"),
    ("Prop", "EObjectType_Prop"),
    ("Camera", "EObjectType_Camera"),
    ("Particle", "EObjectType_Particle"),
    ("Light", "EObjectType_Light"),
    ("SpotLight", "EObjectType_SpotLight"),
    ("PointLight", "EObjectType_PointLight"),
    ("DirectionalLight", "EObjectType_DirectionalLight"),
    ("PopcornFX", "EObjectType_PopcornFX"),
    ("Path", "EObjectType_Path"),
    ("Sky", "EObjectType_Sky"),
    ("LightAvatar", "EObjectType_LightAvatar"),
    ("MDProp", "EObjectType_MDProp"),
    ("ImageLayer", "EObjectType_ImageLayer"),
    ("LensFlare", "EObjectType_LensFlare"),
)

_COMMAND_PARAMETERS = {
    "get_status": {"include"},
    "get_scene_info": {"limit"},
    "get_object_info": {"object_id"},
    "select_objects": {"object_ids"},
    "set_transform": {
        "object_id",
        "name",
        "position_cm",
        "position",
        "rotation_deg_xyz",
        "rotation_degrees",
        "scale_xyz",
        "scale",
        "time_ms",
        "frame",
    },
    "import_asset": {"path", "name"},
    "delete_objects": {"object_ids"},
    "undo": set(),
    "redo": set(),
}


class CommandError(ValueError):
    pass


_UPSTREAM_MODULES = (
    "iclone_mcp_tool_core",
    "iclone_mcp_tool_scene",
    "iclone_mcp_tool_lensflare",
    "iclone_mcp_tool_project",
    "iclone_mcp_tool_fileio",
    "iclone_mcp_tool_transform",
    "iclone_mcp_tool_path",
    "iclone_mcp_tool_materials",
    "iclone_mcp_tool_render",
    "iclone_mcp_tool_timeline",
    "iclone_mcp_tool_camera",
    "iclone_mcp_tool_lights",
    "iclone_mcp_tool_avatar",
    "iclone_mcp_tool_facial",
    "iclone_mcp_tool_morphs",
    "iclone_mcp_tool_mocap",
    "iclone_mcp_tool_diagnostics",
    "iclone_mcp_tool_content",
)
_UPSTREAM_TOOL_REGISTRY = None
_UPSTREAM_REQUIRED_PARAMETERS = {}
_BRIDGE_NATIVE_TOOLS = frozenset(
    {
        "get_status",
        "get_scene_info",
        "get_object_info",
        "select_objects",
        "set_transform",
        "import_asset",
        "delete_objects",
        "undo",
        "redo",
    }
)


def advertised_tool_names(registry=None):
    """Return plugin tool names that should appear in the MCP catalog."""
    if registry is None:
        registry = _load_upstream_tools()
    return sorted(
        name
        for name, metadata in registry.items()
        if metadata.get("advertise", True)
    )


def _delete_object_by_name(params):
    scene_object = _require_object_name(params.get("name"))
    summary = _summary(scene_object)
    _delete_with_undo([scene_object])
    return {"deleted_objects": [summary]}


def _load_upstream_tools():
    global _UPSTREAM_TOOL_REGISTRY
    if _UPSTREAM_TOOL_REGISTRY is not None:
        return _UPSTREAM_TOOL_REGISTRY

    import importlib

    registry = {}
    modules = []
    previous_rlpy = sys.modules.get("RLPy")
    sys.modules["RLPy"] = RLPy
    try:
        for module_name in _UPSTREAM_MODULES:
            try:
                module = importlib.import_module(module_name)
            except Exception:
                continue
            modules.append(module)
        for module in modules:
            module.RLPy = RLPy
        objects_module = sys.modules.get("iclone_mcp_tool_objects")
        if objects_module is not None:
            objects_module.RLPy = RLPy
        for module in modules:
            try:
                module.register(registry)
            except Exception:
                continue
    finally:
        if previous_rlpy is None:
            sys.modules.pop("RLPy", None)
        else:
            sys.modules["RLPy"] = previous_rlpy

    # These two names are implemented by the bridge so their stable-ID
    # behavior and response envelopes remain backward compatible.
    registry.pop("import_asset", None)
    registry.pop("set_transform", None)
    if "delete_object" in registry:
        registry["delete_object"]["handler"] = _delete_object_by_name
        registry["delete_object"]["description"] = (
            "Deletes one iClone object by name and records the deletion for undo."
        )
        # Keep the by-name delete for bridge callers; MCP advertises delete_objects.
        registry["delete_object"]["advertise"] = False
        registry["delete_object"]["destructive"] = True
    for metadata in registry.values():
        metadata.setdefault("advertise", True)
        metadata.setdefault("read_only", False)
        metadata.setdefault("destructive", False)
    _UPSTREAM_TOOL_REGISTRY = registry
    return registry


def start_initialization_grace():
    global _ready_at
    _ready_at = time.monotonic() + INITIALIZATION_GRACE_SECONDS


def _readiness():
    remaining = max(0.0, _ready_at - time.monotonic())
    return remaining == 0.0, int(math.ceil(remaining))


def _object_types():
    result = []
    for type_name, constant_name in _TYPE_CONSTANTS:
        if hasattr(RLPy, constant_name):
            result.append((type_name, getattr(RLPy, constant_name)))
    return result


def _all_objects():
    mask = 0
    for unused_name, value in _object_types():
        mask |= value
    return list(RLPy.RScene.FindObjects(mask)) if mask else []


def _type_name(type_value):
    for name, value in _object_types():
        if type_value == value:
            return name
    try:
        return "Unknown({0})".format(int(type_value))
    except (TypeError, ValueError):
        return "Unknown({0})".format(type_value)


def _time_ms(time_value):
    return int(time_value.ToInt64())


def _vector(vector):
    return [float(vector.x), float(vector.y), float(vector.z)]


def _transform(transform):
    rotation_matrix = transform.R().ToRotationMatrix()
    euler = rotation_matrix.ToEulerAngle(RLPy.EEulerOrder_XYZ, 0.0, 0.0, 0.0)
    return {
        "position_cm": _vector(transform.T()),
        "rotation_deg_xyz": [
            math.degrees(float(euler[0])),
            math.degrees(float(euler[1])),
            math.degrees(float(euler[2])),
        ],
        "scale_xyz": _vector(transform.S()),
    }


def _summary(scene_object):
    return {
        "id": str(scene_object.GetID()),
        "name": str(scene_object.GetName()),
        "type": _type_name(scene_object.GetType()),
    }


def _require_object(object_id):
    if not isinstance(object_id, str) or not object_id:
        raise CommandError("object_id must be a non-empty string.")
    scene_object = RLPy.RScene.QueryObjectByID(object_id)
    if scene_object is None:
        raise CommandError("No scene object has ID '{0}'.".format(object_id))
    return scene_object


def _require_object_name(name):
    if not isinstance(name, str) or not name:
        raise CommandError("name must be a non-empty string.")

    current_camera = RLPy.RScene.GetCurrentCamera()
    if current_camera is not None and str(current_camera.GetName()) == name:
        return current_camera

    find_object = getattr(RLPy.RScene, "FindObject", None)
    if find_object is None:
        raise CommandError("This iClone build cannot find objects by name.")
    for unused_type_name, object_type in _object_types():
        scene_object = find_object(object_type, name)
        if scene_object is not None:
            return scene_object
    raise CommandError("No scene object has name '{0}'.".format(name))


def _require_object_ids(value, allow_empty):
    if not isinstance(value, list):
        raise CommandError("object_ids must be an array of object ID strings.")
    if not allow_empty and not value:
        raise CommandError("object_ids must contain at least one object ID.")

    unique_ids = []
    seen = set()
    for object_id in value:
        if not isinstance(object_id, str) or not object_id:
            raise CommandError("Every object ID must be a non-empty string.")
        if object_id not in seen:
            seen.add(object_id)
            unique_ids.append(object_id)
    return unique_ids


def _require_vector(value, name):
    if not isinstance(value, list) or len(value) != 3:
        raise CommandError("{0} must contain exactly three numbers.".format(name))
    result = []
    for component in value:
        if isinstance(component, bool) or not isinstance(component, (int, float)):
            raise CommandError("{0} must contain exactly three numbers.".format(name))
        component = float(component)
        if not math.isfinite(component):
            raise CommandError("{0} values must be finite.".format(name))
        result.append(component)
    return result


def _vector_from_mapping(value, name, current):
    if not isinstance(value, dict):
        raise CommandError(
            "{0} must be an object with numeric x, y, and z components.".format(name)
        )
    return _require_vector(
        [value.get("x", current[0]), value.get("y", current[1]), value.get("z", current[2])],
        name,
    )


def _check_status(status, operation):
    if status != RLPy.RStatus.Success:
        raise CommandError("{0} failed.".format(operation))


def _begin_action(name):
    RLPy.RGlobal.BeginAction(name)


def _end_action():
    RLPy.RGlobal.EndAction()


def _qt_main_window():
    from PySide2 import QtWidgets
    from shiboken2 import wrapInstance

    address = RLPy.RUi.GetMainWindow()
    if address is None:
        raise CommandError("iClone's main window is not available.")
    return wrapInstance(int(address), QtWidgets.QMainWindow)


def _scene_info(limit):
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 500:
        raise CommandError("limit must be an integer between 1 and 500.")

    objects = _all_objects()
    selected_ids = [str(obj.GetID()) for obj in RLPy.RScene.GetSelectedObjects()]
    camera = RLPy.RScene.GetCurrentCamera()
    fps = RLPy.RGlobal.GetFps()
    fps_value = fps.ToFloat() if hasattr(fps, "ToFloat") else float(fps)
    return {
        "current_time_ms": _time_ms(RLPy.RGlobal.GetTime()),
        "start_time_ms": _time_ms(RLPy.RGlobal.GetStartTime()),
        "end_time_ms": _time_ms(RLPy.RGlobal.GetEndTime()),
        "fps": float(fps_value),
        "current_camera_id": str(camera.GetID()) if camera is not None else None,
        "selected_object_ids": selected_ids,
        "object_count": len(objects),
        "objects": [_summary(obj) for obj in objects[:limit]],
        "truncated": len(objects) > limit,
    }


def _object_info(scene_object):
    selected_ids = {str(obj.GetID()) for obj in RLPy.RScene.GetSelectedObjects()}
    max_point = RLPy.RVector3()
    center_point = RLPy.RVector3()
    min_point = RLPy.RVector3()
    _check_status(
        scene_object.GetBounds(max_point, center_point, min_point),
        "Reading object bounds",
    )
    result = _summary(scene_object)
    result.update(
        {
            "selected": str(scene_object.GetID()) in selected_ids,
            "local_transform": _transform(scene_object.LocalTransform()),
            "world_transform": _transform(scene_object.WorldTransform()),
            "world_bounds": {
                "min_cm": _vector(min_point),
                "center_cm": _vector(center_point),
                "max_cm": _vector(max_point),
            },
        }
    )
    return result


def _get_status(host, port, include=None):
    version = RLPy.RApplication.GetProductVersion()
    if isinstance(version, (list, tuple)):
        version = ".".join(str(part) for part in version)
    ready, ready_in_seconds = _readiness()
    result = {
        "protocol_version": PROTOCOL_VERSION,
        "application": str(RLPy.RApplication.GetProductName()),
        "application_version": str(version),
        "application_pid": os.getpid(),
        "python_version": sys.version.split()[0],
        "listener": {"host": host, "port": int(port)},
        "ready": ready,
        "ready_in_seconds": ready_in_seconds,
        "capabilities": {"undoable_delete": False},
    }
    if not include:
        return result
    if isinstance(include, str):
        include = [include]
    if not isinstance(include, (list, tuple)):
        raise CommandError("include must be a string or array of strings.")
    sections = set(str(item).lower() for item in include)
    registry = _load_upstream_tools()
    section_tools = {
        "application": "get_application_info",
        "api": "get_api_version",
        "license": "get_license_state",
        "system": "get_system_compatibility",
        "runtime": "get_runtime_diagnostics",
        "network": "get_network_capabilities",
        "mocap": "get_mocap_status",
        "ping": "ping_iclone",
    }
    for section in sections:
        tool_name = section_tools.get(section)
        if tool_name is None:
            raise CommandError(
                "Unknown include section '{0}'. Use: {1}.".format(
                    section, ", ".join(sorted(section_tools))
                )
            )
        metadata = registry.get(tool_name)
        if metadata is None:
            raise CommandError("Status section '{0}' is unavailable.".format(section))
        result[section] = metadata["handler"]({})
    return result


def _select_objects(object_ids):
    ids = _require_object_ids(object_ids, allow_empty=True)
    objects = [_require_object(object_id) for object_id in ids]
    _begin_action("MCP Select Objects")
    try:
        _check_status(RLPy.RScene.ClearSelectObjects(), "Clearing selection")
        if objects:
            _check_status(RLPy.RScene.SelectObjects(objects), "Selecting objects")
    finally:
        _end_action()
    return {"selected_object_ids": ids}


def _set_transform(params):
    object_id = params.get("object_id")
    object_name = params.get("name")
    if object_id is not None and object_name is not None:
        raise CommandError("Pass either object_id or name, not both.")
    if object_id is None and object_name is None:
        raise CommandError("Either object_id or name is required.")
    scene_object = (
        _require_object(object_id)
        if object_id is not None
        else _require_object_name(object_name)
    )

    aliases = (
        ("position_cm", "position"),
        ("rotation_deg_xyz", "rotation_degrees"),
        ("scale_xyz", "scale"),
    )
    for current_name, upstream_name in aliases:
        if params.get(current_name) is not None and params.get(upstream_name) is not None:
            raise CommandError(
                "Pass either {0} or {1}, not both.".format(current_name, upstream_name)
            )
    supplied = [
        name
        for name in (
            "position_cm",
            "position",
            "rotation_deg_xyz",
            "rotation_degrees",
            "scale_xyz",
            "scale",
        )
        if params.get(name) is not None
    ]
    if not supplied:
        raise CommandError(
            "At least one transform vector is required: position_cm/position, "
            "rotation_deg_xyz/rotation_degrees, or scale_xyz/scale."
        )

    position_input = params.get("position_cm")
    if position_input is None:
        position_input = params.get("position")
    rotation_input = params.get("rotation_deg_xyz")
    if rotation_input is None:
        rotation_input = params.get("rotation_degrees")
    scale_input = params.get("scale_xyz")
    if scale_input is None:
        scale_input = params.get("scale")

    time_ms = params.get("time_ms")
    frame = params.get("frame")
    if time_ms is not None and frame is not None:
        raise CommandError("Pass either time_ms or frame, not both.")
    if time_ms is None and frame is None:
        time_value = RLPy.RGlobal.GetTime()
    elif time_ms is not None:
        if isinstance(time_ms, bool) or not isinstance(time_ms, int) or time_ms < 0:
            raise CommandError("time_ms must be a non-negative integer.")
        time_value = RLPy.RTime.FromValue(time_ms)
    else:
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            raise CommandError("frame must be a non-negative integer.")
        fps = RLPy.RGlobal.GetFps()
        if not hasattr(fps, "IndexedFrameTime"):
            raise CommandError("This iClone build cannot convert frames to time.")
        time_value = fps.IndexedFrameTime(frame)

    control = scene_object.GetControl("Transform")
    if control is None:
        raise CommandError("Object '{0}' has no transform control.".format(scene_object.GetID()))

    keyed_transform = RLPy.RTransform()
    _check_status(control.GetValue(time_value, keyed_transform), "Reading transform")
    current_position = _vector(keyed_transform.T())
    current_rotation = _transform(keyed_transform)["rotation_deg_xyz"]
    current_scale = _vector(keyed_transform.S())
    if position_input is not None:
        position = (
            _vector_from_mapping(position_input, "position", current_position)
            if isinstance(position_input, dict)
            else _require_vector(position_input, "position_cm")
        )
        keyed_transform.T().x, keyed_transform.T().y, keyed_transform.T().z = position
    if rotation_input is not None:
        rotation = (
            _vector_from_mapping(rotation_input, "rotation_degrees", current_rotation)
            if isinstance(rotation_input, dict)
            else _require_vector(rotation_input, "rotation_deg_xyz")
        )
        rotation_matrix = RLPy.RMatrix3.FromEulerAngle(
            RLPy.EEulerOrder_XYZ,
            math.radians(rotation[0]),
            math.radians(rotation[1]),
            math.radians(rotation[2]),
        )[0]
        keyed_transform.R().FromRotationMatrix(rotation_matrix)
    if scale_input is not None:
        scale = (
            _vector_from_mapping(scale_input, "scale", current_scale)
            if isinstance(scale_input, dict)
            else _require_vector(scale_input, "scale_xyz")
        )
        keyed_transform.S().x, keyed_transform.S().y, keyed_transform.S().z = scale

    _begin_action("MCP Set Transform")
    try:
        _check_status(
            control.SetValue(time_value, keyed_transform),
            "Writing transform",
        )
    finally:
        _end_action()

    return {
        "object": _object_info(scene_object),
        "keyed_time_ms": _time_ms(time_value),
        "keyed_local_transform": _transform(keyed_transform),
    }


def _import_asset(path, name):
    if not isinstance(path, str) or not path:
        raise CommandError("path must be a non-empty string.")
    if not os.path.isabs(path):
        raise CommandError("path must be absolute.")
    path = os.path.normpath(path)
    if not os.path.isfile(path):
        raise CommandError("Asset file does not exist: {0}".format(path))
    extension = os.path.splitext(path)[1].lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise CommandError("Unsupported asset extension: {0}".format(extension or "<none>"))
    if name is not None and (not isinstance(name, str) or not name.strip()):
        raise CommandError("name must be a non-empty string when supplied.")

    before_ids = {str(obj.GetID()) for obj in _all_objects()}
    imported = []
    should_rollback = False
    _begin_action("MCP Import Asset")
    try:
        RLPy.RScene.ClearSelectObjects()
        loaded_object = RLPy.RFileIO.LoadObject(path, True)
        after_objects = _all_objects()
        imported = [obj for obj in after_objects if str(obj.GetID()) not in before_ids]
        if not imported and loaded_object is not None:
            imported = [loaded_object]
        if not imported:
            raise CommandError("iClone did not create an object from the asset.")
        if name is not None:
            if len(imported) != 1:
                should_rollback = True
                raise CommandError("name can only be used when exactly one object is imported.")
            _check_status(imported[0].SetName(name.strip()), "Renaming imported object")
    except Exception:
        _end_action()
        if should_rollback:
            RLPy.RGlobal.Undo()
        raise
    else:
        _end_action()

    return {"imported_objects": [_summary(obj) for obj in imported]}


def _delete_objects(object_ids):
    ids = _require_object_ids(object_ids, allow_empty=False)
    objects = [_require_object(object_id) for object_id in ids]
    summaries = [_summary(obj) for obj in objects]

    _delete_with_undo(objects)
    return {"deleted_objects": summaries}


def _delete_with_undo(objects):
    try:
        import RLPy2
    except ImportError as error:
        raise CommandError(
            "iClone's RLPy2 Edit API is unavailable; restart the iClone MCP plugin."
        ) from error

    system = RLPy2.System.GetInterface()
    edit = RLPy2.Edit.GetInterface()
    if system is None or edit is None:
        raise CommandError("iClone's RLPy2 Edit API is unavailable.")

    handles = RLPy2.RArrayListHandle()
    for scene_object in objects:
        if not handles.Add(system.ToHandle(scene_object.GetID())):
            raise CommandError("Preparing iClone object handles failed.")
    if not edit.DeleteSceneObjects(handles, True, True):
        raise CommandError("Deleting iClone objects failed.")


def dispatch(command_type, params, host, port):
    if not isinstance(command_type, str) or not command_type:
        raise CommandError("type must be a non-empty string.")
    if not isinstance(params, dict):
        raise CommandError("params must be a JSON object.")

    upstream_registry = None
    upstream_metadata = None
    if command_type not in _COMMAND_PARAMETERS:
        upstream_registry = _load_upstream_tools()
        upstream_metadata = upstream_registry.get(command_type)
        if upstream_metadata is None:
            raise CommandError("Unknown command type '{0}'.".format(command_type))
        _COMMAND_PARAMETERS[command_type] = set(
            upstream_metadata.get("inputSchema", {}).get("properties", {})
        )
        _UPSTREAM_REQUIRED_PARAMETERS[command_type] = set(
            upstream_metadata.get("inputSchema", {}).get("required", ())
        )

    unexpected = sorted(set(params) - _COMMAND_PARAMETERS[command_type])
    if unexpected:
        raise CommandError(
            "Unexpected parameter(s): {0}.".format(", ".join(unexpected))
        )
    required = _UPSTREAM_REQUIRED_PARAMETERS.get(command_type, ())
    if required:
        missing = sorted(set(required) - set(params))
        if missing:
            raise CommandError(
                "Missing required parameter(s): {0}.".format(", ".join(missing))
            )
    ready, ready_in_seconds = _readiness()
    if command_type != "get_status" and not ready:
        raise CommandError(
            "iClone is still initializing; retry in about {0} seconds.".format(
                ready_in_seconds
            )
        )

    if command_type == "get_status":
        return _get_status(host, port, params.get("include"))
    if command_type == "get_scene_info":
        return _scene_info(params.get("limit", 100))
    if command_type == "get_object_info":
        return _object_info(_require_object(params.get("object_id")))
    if command_type == "select_objects":
        return _select_objects(params.get("object_ids"))
    if command_type == "set_transform":
        return _set_transform(params)
    if command_type == "import_asset":
        return _import_asset(params.get("path"), params.get("name"))
    if command_type == "delete_objects":
        return _delete_objects(params.get("object_ids"))
    if command_type == "undo":
        RLPy.RGlobal.Undo()
        return {"performed": True}
    if command_type == "redo":
        RLPy.RGlobal.Redo()
        return {"performed": True}

    if upstream_registry is None:
        upstream_registry = _load_upstream_tools()
    metadata = upstream_metadata or upstream_registry.get(command_type)
    if metadata is None:
        raise CommandError("Unknown command type '{0}'.".format(command_type))
    try:
        return metadata["handler"](params)
    except CommandError:
        raise
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as error:
        raise CommandError(str(error))
