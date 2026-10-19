import math
import os

import RLPy

from iclone_mcp_tool_objects import find_by_name


_CREATE_LIGHT_ACTIONS = {
    "directional": ("qtCreateDirectionalLight", RLPy.EObjectType_DirectionalLight),
    "spot": ("qtCreateSpotLight", RLPy.EObjectType_SpotLight),
    "point": ("qtCreatePointLight", RLPy.EObjectType_PointLight),
}

_VOLUMETRIC_LIGHT_TYPES = (
    ("SpotLight", RLPy.EObjectType_SpotLight),
    ("PointLight", RLPy.EObjectType_PointLight),
)

_KEYABLE_VOLUMETRIC_FIELDS = (
    "intensity",
    "scatter_color",
    "medium_density_multiplier",
    "absorption",
    "eccentricity",
    "falloff_power",
)


def _find(name):
    if name:
        light = find_by_name(name)
        return light
    for object_type in (RLPy.EObjectType_Light, RLPy.EObjectType_SpotLight, RLPy.EObjectType_PointLight, RLPy.EObjectType_DirectionalLight):
        lights = RLPy.RScene.FindObjects(object_type)
        if lights:
            return lights[0]
    raise ValueError("No light found")


def _find_light(args):
    object_id = args.get("object_id")
    if object_id is not None:
        light = RLPy.RScene.QueryObjectByID(str(object_id))
        if light is None:
            raise ValueError("Light not found: %s" % object_id)
        return light
    return _find(args.get("name"))


def _light_type_name(light):
    light_type = light.GetType()
    for name, enum_value in _VOLUMETRIC_LIGHT_TYPES:
        if light_type == enum_value:
            return name
    type_name = light.GetType()
    if hasattr(type_name, "ToString"):
        return str(type_name.ToString())
    return str(type_name)


def _is_volumetric_light(light):
    return _light_type_name(light) in ("SpotLight", "PointLight")


def _require_volumetric_api(light):
    if not hasattr(light, "GetVolumetricLightEnable"):
        raise RuntimeError("Volumetric light API is unavailable. Rebuild RLPy and iClone.")


def _color_vector3(value):
    if value is None:
        return None
    if hasattr(value, "X") and hasattr(value, "Y") and hasattr(value, "Z"):
        return {"r": float(value.X()), "g": float(value.Y()), "b": float(value.Z())}
    if hasattr(value, "x") and hasattr(value, "y") and hasattr(value, "z"):
        return {"r": float(value.x), "g": float(value.y), "b": float(value.z)}
    return None


def _vector3_from_color(value):
    if not isinstance(value, dict):
        raise ValueError("scatter_color must be an object with r, g, and b")
    return RLPy.RVector3(float(value.get("r", 1)), float(value.get("g", 1)), float(value.get("b", 1)))


def _read_volumetric(light):
    _require_volumetric_api(light)
    type_name = _light_type_name(light)
    if not _is_volumetric_light(light):
        raise ValueError("Volumetric light is only supported for spot and point lights.")

    data = {
        "id": str(light.GetID()),
        "name": light.GetName(),
        "type": type_name,
        "enabled": bool(light.GetVolumetricLightEnable()),
        "unlink_light_intensity": bool(light.GetVolumetricLightUnlinkIntensity()),
        "intensity": float(light.GetVolumetricLightIntensity()),
        "scatter_color": _color_vector3(light.GetVolumetricLightScatterColor()),
        "medium_density_multiplier": float(light.GetVolumetricLightMediumDensity()),
        "absorption": float(light.GetVolumetricLightAbsorption()),
        "eccentricity": float(light.GetVolumetricLightEccentricity()),
        "tessellation_amount": int(light.GetVolumetricLightTessellationAmount()),
    }
    if type_name == "SpotLight":
        data["falloff_power"] = int(light.GetVolumetricLightFalloffPower())
    return data


def _maybe_attach_volumetric(data, light):
    if _is_volumetric_light(light) and hasattr(light, "GetVolumetricLightEnable"):
        try:
            data["volumetric"] = _read_volumetric(light)
        except Exception:
            pass
    return data


def get_light(args):
    light = _find_light(args)
    color = light.GetColor()
    data = {
        "id": str(light.GetID()),
        "name": light.GetName(),
        "type": light.GetType(),
        "active": light.GetActive(),
        "multiplier": light.GetMultiplier(),
        "color": {"r": color.R(), "g": color.G(), "b": color.B()},
    }
    for key, method_name in (
        ("range", "GetRange"),
        ("inverse_square", "GetInverseSquare"),
        ("cast_shadow", "IsCastShadow"),
        ("rectangle_shape", "IsRectangleShape"),
        ("tube_shape", "IsTubeShape"),
        ("tube_length", "GetTubeLength"),
        ("tube_radius", "GetTubeRadius"),
        ("tube_soft_radius", "GetTubeSoftRadius"),
        ("transmission", "GetTransmission"),
        ("shadow_strength", "GetDarkenShadowStrength"),
    ):
        method = getattr(light, method_name, None)
        if method:
            try:
                data[key] = method()
            except Exception:
                data[key] = None
    include_volumetric = args.get("include_volumetric")
    if include_volumetric is False:
        return data
    if include_volumetric:
        data["volumetric"] = get_volumetric_light({"object_id": str(light.GetID())})
        return data
    return _maybe_attach_volumetric(data, light)


def get_volumetric_light(args):
    return _read_volumetric(_find_light(args))


def set_volumetric_light(args):
    light = _find_light(args)
    _require_volumetric_api(light)
    type_name = _light_type_name(light)
    if not _is_volumetric_light(light):
        raise ValueError("Volumetric light is only supported for spot and point lights.")

    if type_name == "PointLight" and args.get("falloff_power") is not None:
        raise ValueError("falloff_power is only supported for spot lights.")

    if args.get("enabled") is not None:
        if light.SetVolumetricLightEnable(bool(args["enabled"])) != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not set volumetric light enabled state")

    if args.get("unlink_light_intensity") is not None:
        if light.SetVolumetricLightUnlinkIntensity(bool(args["unlink_light_intensity"])) != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not set volumetric light unlink_light_intensity")

    if args.get("tessellation_amount") is not None:
        if light.SetVolumetricLightTessellationAmount(int(args["tessellation_amount"])) != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not set volumetric light tessellation_amount")

    patch_fields = [key for key in _KEYABLE_VOLUMETRIC_FIELDS if args.get(key) is not None]
    if patch_fields:
        patch_intensity = "intensity" in patch_fields
        patch_scatter = "scatter_color" in patch_fields
        patch_density = "medium_density_multiplier" in patch_fields
        patch_absorption = "absorption" in patch_fields
        patch_eccentricity = "eccentricity" in patch_fields
        patch_falloff = "falloff_power" in patch_fields

        intensity = float(args.get("intensity", 0.0))
        scatter_color = _vector3_from_color(args.get("scatter_color"))
        medium_density = float(args.get("medium_density_multiplier", 0.0))
        absorption = float(args.get("absorption", 0.0))
        eccentricity = float(args.get("eccentricity", 0.0))
        falloff_power = int(args.get("falloff_power", 1))

        patch_method = getattr(light, "PatchVolumetricLightKey", None)
        if patch_method is None:
            raise RuntimeError("Volumetric light API is unavailable. Rebuild RLPy and iClone.")

        if type_name == "SpotLight":
            result = patch_method(
                patch_intensity,
                intensity,
                patch_scatter,
                scatter_color,
                patch_density,
                medium_density,
                patch_absorption,
                absorption,
                patch_eccentricity,
                eccentricity,
                patch_falloff,
                falloff_power,
            )
        else:
            result = patch_method(
                patch_intensity,
                intensity,
                patch_scatter,
                scatter_color,
                patch_density,
                medium_density,
                patch_absorption,
                absorption,
                patch_eccentricity,
                eccentricity,
            )

        if result != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not set volumetric light key fields")

    return _read_volumetric(light)


def create_light(args):
    light_type = str(args.get("type", "")).lower()
    if light_type not in _CREATE_LIGHT_ACTIONS:
        raise ValueError("type must be 'directional', 'spot', or 'point'")

    action_name, object_type = _CREATE_LIGHT_ACTIONS[light_type]
    before = {str(obj.GetID()) for obj in RLPy.RScene.FindObjects(object_type)}
    from iclone_mcp_tool_diagnostics import trigger_ui_action

    selected = list(RLPy.RScene.GetSelectedObjects())
    try:
        RLPy.RScene.ClearSelectObjects()
        action = trigger_ui_action({"object_name": action_name})
    finally:
        RLPy.RScene.ClearSelectObjects()
        if selected:
            RLPy.RScene.SelectObjects(selected)
    created = [
        {"id": str(obj.GetID()), "name": obj.GetName()}
        for obj in RLPy.RScene.FindObjects(object_type)
        if str(obj.GetID()) not in before
    ]
    if not created:
        raise RuntimeError("iClone did not report a newly created light")
    return {"type": light_type, "action": action, "created_lights": created}


def set_light(args):
    light = _find_light(args)
    time = RLPy.RGlobal.GetTime()
    angle_degrees = args.get("angle_degrees")
    if angle_degrees is not None:
        angle_degrees = float(angle_degrees)
        if not 0.0 <= angle_degrees <= 180.0:
            raise ValueError("angle_degrees must be between 0 and 180")
        method = getattr(light, "SetAngle", None)
        if method is None or method(time, math.radians(angle_degrees)) != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not set directional light angle")
    if args.get("active") is not None:
        try:
            result = light.SetActive(time, args["active"])
        except TypeError:
            result = light.SetActive(args["active"])
        if result != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not change light state")
    if args.get("multiplier") is not None and light.SetMultiplier(time, args["multiplier"]) != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not change light multiplier")
    if args.get("color") is not None:
        value = args["color"]
        if light.SetColor(time, RLPy.RRgb(value.get("r", 1), value.get("g", 1), value.get("b", 1))) != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not change light color")
    for key, method_name in (("range", "SetRange"), ("shadow_strength", "SetDarkenShadowStrength")):
        if args.get(key) is not None:
            method = getattr(light, method_name, None)
            if method is None or method(time, float(args[key])) != RLPy.RStatus.Success:
                raise RuntimeError("iClone could not set light %s" % key)
    for key, method_name in (("inverse_square", "SetInverseSquare"), ("cast_shadow", "SetCastShadow"), ("rectangle_shape", "SetRectangleShape"), ("tube_shape", "SetTubeShape"), ("transmission", "SetTransmission")):
        if args.get(key) is not None:
            method = getattr(light, method_name, None)
            if method is None or method(bool(args[key])) != RLPy.RStatus.Success:
                raise RuntimeError("iClone could not set light %s" % key)
    for key, method_name in (("tube_length", "SetTubeLength"), ("tube_radius", "SetTubeRadius"), ("tube_soft_radius", "SetTubeSoftRadius")):
        if args.get(key) is not None:
            method = getattr(light, method_name, None)
            if method is None or method(float(args[key])) != RLPy.RStatus.Success:
                raise RuntimeError("iClone could not set light %s" % key)
    if args.get("rect_width") is not None or args.get("rect_height") is not None:
        method = getattr(light, "SetRectWidthHeight", None)
        if method is None or method(RLPy.RVector2(float(args.get("rect_width", 1)), float(args.get("rect_height", 1)))) != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not set rectangular light dimensions")
    if any(args.get(key) is not None for key in ("spot_angle", "spot_falloff", "spot_attenuation")):
        method = getattr(light, "SetSpotLightBeam", None)
        if method is None or method(time, float(args.get("spot_angle", 45)), float(args.get("spot_falloff", 0)), float(args.get("spot_attenuation", 0))) != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not set spotlight beam")
    for key, method_name in (("ies_path", "LoadIes"), ("rect_texture_path", "LoadRectTexture")):
        if args.get(key) is not None:
            path = os.path.abspath(args[key])
            if not os.path.isfile(path):
                raise FileNotFoundError("Light file not found: %s" % path)
            method = getattr(light, method_name, None)
            if method is None or method(path) != RLPy.RStatus.Success:
                raise RuntimeError("iClone could not load light file")
    if args.get("clear_rect_texture"):
        method = getattr(light, "ClearRectTexture", None)
        if method is None or method() != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not clear rectangular light texture")
    volumetric = args.get("volumetric")
    if volumetric is not None:
        if not isinstance(volumetric, dict):
            raise ValueError("volumetric must be an object")
        vol_args = dict(volumetric)
        vol_args["object_id"] = str(light.GetID())
        set_volumetric_light(vol_args)
    response = get_light({"object_id": str(light.GetID())})
    if angle_degrees is not None:
        response["angle_degrees"] = angle_degrees
    return response


_VOLUMETRIC_LIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "object_id": {"type": "string"},
        "name": {"type": "string"},
        "enabled": {"type": "boolean"},
        "unlink_light_intensity": {"type": "boolean"},
        "intensity": {"type": "number"},
        "scatter_color": {"type": "object"},
        "medium_density_multiplier": {"type": "number"},
        "absorption": {"type": "number"},
        "falloff_power": {"type": "integer", "minimum": 1, "maximum": 100},
        "eccentricity": {"type": "number", "minimum": -0.99, "maximum": 0.99},
        "tessellation_amount": {"type": "integer", "minimum": 0, "maximum": 6},
    },
}


def register(registry):
    registry["create_light"] = {
        "handler": create_light,
        "main_thread": True,
        "description": "Ajoute une lumière iClone supportée par l'action de création native.",
        "inputSchema": {"type": "object", "properties": {"type": {"type": "string", "enum": ["directional", "spot", "point"]}}, "required": ["type"]},
    }
    registry["get_light"] = {
        "handler": get_light,
        "main_thread": True,
        "read_only": True,
        "description": "Lit les propriétés de base et avancées d'une lumière iClone 8. Set include_volumetric to merge volumetric panel values.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "name": {"type": "string"},
                "include_volumetric": {"type": "boolean"},
            },
        },
    }
    registry["set_light"] = {
        "handler": set_light,
        "main_thread": True,
        "description": "Modifie les propriétés de base et avancées des lumières iClone 8. Pass volumetric as a nested object to update volumetric settings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "name": {"type": "string"},
                "active": {"type": "boolean"},
                "angle_degrees": {"type": "number", "minimum": 0, "maximum": 180},
                "multiplier": {"type": "number"},
                "color": {"type": "object"},
                "range": {"type": "number"},
                "inverse_square": {"type": "boolean"},
                "cast_shadow": {"type": "boolean"},
                "rectangle_shape": {"type": "boolean"},
                "tube_shape": {"type": "boolean"},
                "tube_length": {"type": "number"},
                "tube_radius": {"type": "number"},
                "tube_soft_radius": {"type": "number"},
                "rect_width": {"type": "number"},
                "rect_height": {"type": "number"},
                "spot_angle": {"type": "number"},
                "spot_falloff": {"type": "number"},
                "spot_attenuation": {"type": "number"},
                "transmission": {"type": "boolean"},
                "shadow_strength": {"type": "number"},
                "ies_path": {"type": "string"},
                "rect_texture_path": {"type": "string"},
                "clear_rect_texture": {"type": "boolean"},
                "volumetric": {"type": "object"},
            },
        },
    }

    # Legacy wrappers kept for bridge dispatch; not advertised to MCP clients.
    _hidden = {"advertise": False, "main_thread": True}
    registry["get_volumetric_light"] = dict(
        _hidden,
        handler=get_volumetric_light,
        read_only=True,
        description="Reads volumetric light panel values for a spot or point light.",
        inputSchema={"type": "object", "properties": {"object_id": {"type": "string"}, "name": {"type": "string"}}},
    )
    registry["set_volumetric_light"] = dict(
        _hidden,
        handler=set_volumetric_light,
        description="Writes volumetric light panel values for a spot or point light.",
        inputSchema=_VOLUMETRIC_LIGHT_SCHEMA,
    )
