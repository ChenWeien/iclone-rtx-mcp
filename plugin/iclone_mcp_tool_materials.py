import math
import os

import RLPy


def _find(name):
    for object_type in (
        RLPy.EObjectType_Prop,
        RLPy.EObjectType_Avatar,
        getattr(RLPy, "EObjectType_Hair", None),
        getattr(RLPy, "EObjectType_Accessory", None),
        getattr(RLPy, "EObjectType_Cloth", None),
        getattr(RLPy, "EObjectType_Sky", None),
    ):
        if object_type is not None:
            obj = RLPy.RScene.FindObject(object_type, name)
            if obj is not None:
                return obj
    raise ValueError("Object not found: %s" % name)


def _targets(obj):
    component = obj.GetMaterialComponent()
    targets = []
    for mesh_name in obj.GetMeshNames():
        for material_name in component.GetMaterialNames(mesh_name):
            targets.append((mesh_name, material_name))
    return component, targets


def _material_target(args):
    obj = _find(args["name"])
    component, targets = _targets(obj)
    index = args.get("material_index")
    if index is None:
        index = 0
    if index < 0 or index >= len(targets):
        raise ValueError("Material index not found: %s" % index)
    mesh_name, material_name = targets[index]
    return obj, component, index, mesh_name, material_name


def _current_key():
    key = RLPy.RKey()
    key.SetTime(RLPy.RGlobal.GetTime())
    if hasattr(RLPy, "ETransitionType_Step"):
        key.SetTransitionType(RLPy.ETransitionType_Step)
    return key


def _vector3(value):
    return {"x": float(value.x), "y": float(value.y), "z": float(value.z)}


def _material_value(value, kind):
    if kind == "color":
        return {"r": float(value.R()), "g": float(value.G()), "b": float(value.B())}
    if kind == "vector3":
        return _vector3(value)
    if kind == "weights":
        return [float(item) for item in value]
    if kind == "domain":
        names = {
            "MaterialDomain_Opaque": "opaque",
            "MaterialDomain_AlphaTested": "alpha_tested",
            "MaterialDomain_AlphaBlended": "alpha_blended",
            "MaterialDomain_Transmissive": "transmissive",
            "MaterialDomain_TransmissiveAlphaTested": "transmissive_alpha_tested",
            "MaterialDomain_TransmissiveAlphaBlended": "transmissive_alpha_blended",
            "MaterialDomain__None": "none",
        }
        for constant, name in names.items():
            if getattr(RLPy, constant, object()) == value:
                return name
        return value
    if kind == "absorption_model":
        names = {
            "EHairAbsorptionModel_Color": "color",
            "EHairAbsorptionModel_Physics": "physics",
            "EHairAbsorptionModel_PhysicsNormalized": "physics_normalized",
        }
        for constant, name in names.items():
            if getattr(RLPy, constant, object()) == value:
                return name
        return value
    return value


_TEXTURE_CHANNELS = {
    "metallic": "EMaterialTextureChannel_Metallic",
    "diffuse": "EMaterialTextureChannel_Diffuse",
    "specular": "EMaterialTextureChannel_Specular",
    "shininess": "EMaterialTextureChannel_Shininess",
    "glow": "EMaterialTextureChannel_Glow",
    "displacement": "EMaterialTextureChannel_Displacement",
    "opacity": "EMaterialTextureChannel_Opacity",
    "diffuse_blend": "EMaterialTextureChannel_DiffuseBlend",
    "bump": "EMaterialTextureChannel_Bump",
    "reflection": "EMaterialTextureChannel_Reflection",
    "refraction": "EMaterialTextureChannel_Refraction",
    "cube": "EMaterialTextureChannel_Cube",
    "ambient_occlusion": "EMaterialTextureChannel_AmbientOcclusion",
    "normal": "EMaterialTextureChannel_Normal",
    "vector_displacement": "EMaterialTextureChannel_VectorDisplacement",
    "roughness": "EMaterialTextureChannel_Roughness",
}

_MATERIAL_ATTRIBUTES = (
    "TessellationLevel",
    "TessellationMultiplier",
    "TessellationThreshold",
)

_MATERIAL_GETTERS = {
    "glossiness": ("GetGlossinessWeight", "value"),
    "specular_weight": ("GetSpecularWeight", "value"),
    "opacity": ("GetOpacity", "value"),
    "self_illumination": ("GetSelfIlluminationWeight", "value"),
    "texture_weights": ("GetTextureWeights", "weights"),
    "two_sided": ("IsTwoSidedMaterial", "bool"),
    "shader": ("GetShader", "value"),
    "refraction": ("GetRefraction", "value"),
    "refraction_enabled": ("IsRefractionEnable", "bool"),
    "material_domain": ("GetMaterialDomain", "domain"),
    "thin_surface": ("IsThinSurface", "bool"),
    "shadow_caster": ("IsShadowCaster", "bool"),
    "shadow_no_l_fadeout": ("GetShadowNoLFadeout", "value"),
    "index_of_refraction": ("GetIndexOfRefraction", "value"),
    "transmission_factor": ("GetTransmissionFactor", "value"),
    "diffuse_transmission_factor": ("GetDiffuseTransmissionFactor", "value"),
    "volume_attenuation_distance": ("GetVolumeAttenuationDistance", "value"),
    "volume_attenuation_color": ("GetVolumeAttenuationColor", "vector3"),
    "sheen_weight": ("GetSheenWeight", "value"),
    "coat_weight": ("GetCoatWeight", "value"),
    "sheen_roughness": ("GetSheenRoughness", "value"),
    "coat_roughness": ("GetCoatRoughness", "value"),
    "coat_ior": ("GetCoatIOR", "value"),
    "sheen_tint": ("GetSheenTint", "vector3"),
    "coat_tint": ("GetCoatTint", "vector3"),
    "emissive_color": ("GetEmissiveColor", "vector3"),
    "glow_color": ("GetEmissiveColor", "vector3"),
    "use_glow_color": ("GetUseEmissiveColor", "bool"),
    "roughness": ("GetRoughness", "value"),
    "metalness": ("GetMetalness", "value"),
    "rtx_specular_weight": ("GetRtxSpecularWeight", "value"),
    "coat_normal_strength": ("GetCoatNormalStrength", "value"),
    "use_roughness_slider": ("GetUseRoughnessSlider", "bool"),
    "use_metalness_slider": ("GetUseMetalnessSlider", "bool"),
    "melanin": ("GetMelanin", "value"),
    "melanin_redness": ("GetMelaninRedness", "value"),
    "radial_roughness": ("GetRadialRoughness", "value"),
    "use_radial_roughness": ("GetUseRadialRoughness", "bool"),
    "hair_roughness_map_strength": ("GetHairRoughnessMapStrength", "value"),
    "cuticle_angle_degrees": ("GetCuticleAngleInDegrees", "value"),
    "absorption_model": ("GetAbsorptionModel", "absorption_model"),
    "hair_absorption_factor": ("GetHairAbsorptionFactor", "value"),
    "reflection": ("GetReflection", "value"),
    "reflection_enabled": ("IsReflectionEnable", "bool"),
    "gi_thickness": ("GetGiThickness", "value"),
}

_MATERIAL_PROPERTY_SETTERS = {
    "glossiness": ("AddGlossinessKey", "number", True),
    "specular_weight": ("AddSpecularKey", "number", True),
    "self_illumination": ("AddSelfIlluminationKey", "number", True),
    "opacity": ("AddOpacityKey", "number", True),
    "refraction": ("AddRefractionKey", "number", True),
    "index_of_refraction": ("SetIndexOfRefraction", "number", True),
    "transmission_factor": ("SetTransmissionFactor", "number", True),
    "diffuse_transmission_factor": ("SetDiffuseTransmissionFactor", "number", True),
    "volume_attenuation_distance": ("SetVolumeAttenuationDistance", "number", True),
    "volume_attenuation_color": ("SetVolumeAttenuationColor", "vector3", True),
    "sheen_weight": ("SetSheenWeight", "number", True),
    "coat_weight": ("SetCoatWeight", "number", True),
    "sheen_roughness": ("SetSheenRoughness", "number", True),
    "coat_roughness": ("SetCoatRoughness", "number", True),
    "coat_ior": ("SetCoatIOR", "number", True),
    "sheen_tint": ("SetSheenTint", "vector3", True),
    "coat_tint": ("SetCoatTint", "vector3", True),
    "emissive_color": ("SetEmissiveColor", "vector3", True),
    "glow_color": ("SetEmissiveColor", "vector3", True),
    "use_glow_color": ("SetUseEmissiveColor", "bool", False),
    "roughness": ("SetRoughness", "number", True),
    "metalness": ("SetMetalness", "number", True),
    "rtx_specular_weight": ("SetRtxSpecularWeight", "number", False),
    "coat_normal_strength": ("SetCoatNormalStrength", "number", True),
    "use_roughness_slider": ("SetUseRoughnessSlider", "bool", False),
    "use_metalness_slider": ("SetUseMetalnessSlider", "bool", False),
    "melanin": ("SetMelanin", "number", False),
    "melanin_redness": ("SetMelaninRedness", "number", False),
    "radial_roughness": ("SetRadialRoughness", "number", True),
    "use_radial_roughness": ("SetUseRadialRoughness", "bool", False),
    "hair_roughness_map_strength": ("SetHairRoughnessMapStrength", "number", False),
    "cuticle_angle_degrees": ("SetCuticleAngleInDegrees", "number", False),
    "hair_absorption_factor": ("SetHairAbsorptionFactor", "number", True),
    "reflection": ("AddReflectionKey", "number", True),
    "two_sided": ("SetTwoSidedMaterial", "bool", False),
    "refraction_enabled": ("SetRefractionEnable", "bool", False),
    "thin_surface": ("SetThinSurface", "bool", False),
    "shadow_caster": ("SetShadowCaster", "bool", False),
    "shadow_no_l_fadeout": ("SetShadowNoLFadeout", "number", False),
    "reflection_enabled": ("SetReflectionEnable", "bool", False),
    "material_domain": ("SetMaterialDomain", "domain", False),
    "absorption_model": ("SetAbsorptionModel", "absorption_model", False),
    "gi_thickness": ("SetGiThickness", "number", False),
}

_CAPABILITY_WIDGETS = {
    "material_domain": "qtMaterialDomainComboBox",
    "use_roughness_slider": "qtUseRoughnessSliderCheckBox",
    "use_metalness_slider": "qtUseMetalnessSliderCheckBox",
    "hair_absorption_factor": "qtHairAbsorptionFactorCombospinbox",
    "hair_roughness_map_strength": "qtHairRoughnessMapStrength",
    "radial_roughness": "qtHairRadialRoughnessCombospinbox",
}

_CAPABILITY_RANGES = {
    "roughness": (0.0, 1.0, "ratio"),
    "metalness": (0.0, 1.0, "ratio"),
    "sheen_weight": (0.0, 1.0, "ratio"),
    "coat_weight": (0.0, 1.0, "ratio"),
    "hair_alpha_multiplier": (0.0, None, "ratio"),
    "hair_alpha_power": (0.0, None, "power"),
    "hair_absorption_factor": (0.0, None, "ratio"),
    "hair_roughness_map_strength": (0.0, 100.0, "percent"),
    "radial_roughness": (0.0, 1.0, "ratio"),
    "gi_thickness": (1.0, 2.0, "engine_factor"),
}

_GENERIC_PARAMETER_ALIASES = {
    "hair_alpha_multiplier": ("Hair Alpha Multiplier", "Alpha Multiplier", "Hair_Alpha_Multiplier"),
    "hair_alpha_power": ("Hair Alpha Power", "Alpha Power", "Hair_Alpha_Power"),
    "roughness_multiplier": ("Edge Roughness Multiplier",),
    "volume_thickness": ("Volume Thickness", "Volume_Thickness"),
}

_GENERIC_TEXTURE_ALIASES = {
    "coat_normal": ("Coat Normal", "Coat_Normal", "CoatNormal"),
    "coat_mask": ("Coat Mask", "Coat_Mask", "CoatMask"),
    "glow_map": ("Glow Map", "Glow_Map", "GlowMap"),
}


def _property_input(value, kind):
    if kind == "number":
        if isinstance(value, bool):
            raise ValueError("Material property value must be numeric")
        return float(value)
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError("Material property value must be boolean")
        return value
    if kind == "vector3":
        if not isinstance(value, dict):
            raise ValueError("Material property value must be an XYZ object")
        x = value.get("x", value.get("r"))
        y = value.get("y", value.get("g"))
        z = value.get("z", value.get("b"))
        if x is None or y is None or z is None:
            raise ValueError("Material property value needs x/y/z or r/g/b")
        return RLPy.RVector3(float(x), float(y), float(z))
    if kind == "domain":
        names = {
            "opaque": "MaterialDomain_Opaque",
            "alpha_tested": "MaterialDomain_AlphaTested",
            "alpha_blended": "MaterialDomain_AlphaBlended",
            "transmissive": "MaterialDomain_Transmissive",
            "transmissive_alpha_tested": "MaterialDomain_TransmissiveAlphaTested",
            "transmissive_alpha_blended": "MaterialDomain_TransmissiveAlphaBlended",
            "none": "MaterialDomain__None",
        }
        constant = names.get(value) if isinstance(value, str) else None
        if constant is None or not hasattr(RLPy, constant):
            raise ValueError("Unsupported material domain")
        return getattr(RLPy, constant)
    if kind == "absorption_model":
        names = {
            "color": "EHairAbsorptionModel_Color",
            "physics": "EHairAbsorptionModel_Physics",
            "physics_normalized": "EHairAbsorptionModel_PhysicsNormalized",
        }
        constant = names.get(value) if isinstance(value, str) else None
        if constant is None or not hasattr(RLPy, constant):
            raise ValueError("Unsupported hair absorption model")
        return getattr(RLPy, constant)
    return value


def _shader_values(value):
    if isinstance(value, bool):
        raise ValueError("Shader parameter values must be numeric")
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, dict):
        values = [value.get(key) for key in ("x", "y", "z", "w")]
        if values[0] is None:
            values = [value.get(key) for key in ("r", "g", "b", "a")]
        while values and values[-1] is None:
            values.pop()
        if not values or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in values):
            raise ValueError("Shader parameter values must be numeric")
        return [float(item) for item in values]
    if isinstance(value, (list, tuple)) and value:
        if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
            raise ValueError("Shader parameter values must be numeric")
        return [float(item) for item in value]
    raise ValueError("Shader parameter value must be a number, vector, or numeric array")


def _shader_names(component, mesh_name, material_name):
    getter = getattr(component, "GetShaderParameterNames", None)
    if getter is None:
        return []
    try:
        return [str(value) for value in (getter(mesh_name, material_name) or [])]
    except Exception:
        return []


def _shader_texture_names(component, mesh_name, material_name):
    getter = getattr(component, "GetShaderTextureNames", None)
    if getter is None:
        return []
    try:
        return [str(value) for value in (getter(mesh_name, material_name) or [])]
    except Exception:
        return []


def _normalized_name(value):
    return "".join(character.lower() for character in str(value) if character.isalnum())


def _find_shader_name(names, aliases):
    normalized = {_normalized_name(name): name for name in names}
    for alias in aliases:
        match = normalized.get(_normalized_name(alias))
        if match is not None:
            return match
    return None


def _generic_parameter_name(component, mesh_name, material_name, property_name):
    aliases = _GENERIC_PARAMETER_ALIASES.get(property_name, (property_name,))
    return _find_shader_name(_shader_names(component, mesh_name, material_name), aliases)


def _generic_texture_name(component, mesh_name, material_name, channel_name):
    aliases = _GENERIC_TEXTURE_ALIASES.get(channel_name, (channel_name,))
    return _find_shader_name(_shader_texture_names(component, mesh_name, material_name), aliases)


def _generic_parameter_value(component, mesh_name, material_name, parameter_name):
    getter = getattr(component, "GetShaderParameter", None)
    if getter is None:
        return None
    values = getter(mesh_name, material_name, parameter_name)
    if values is None or values == []:
        return None
    values = [float(value) for value in values]
    return values[0] if len(values) == 1 else values


def _read_property(component, mesh_name, material_name, property_name):
    spec = _MATERIAL_GETTERS.get(property_name)
    if spec is not None:
        method = getattr(component, spec[0], None)
        if method is not None:
            return _material_value(method(mesh_name, material_name), spec[1])
    parameter_name = _generic_parameter_name(component, mesh_name, material_name, property_name)
    if parameter_name is not None:
        return _generic_parameter_value(component, mesh_name, material_name, parameter_name)
    return None


def _values_equal(left, right):
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=1e-5, abs_tol=1e-5)
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(_values_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(_values_equal(left[key], right[key]) for key in left)
    return left == right


def _capability(property_name, readable, writable, supported, reason=None):
    minimum, maximum, unit = _CAPABILITY_RANGES.get(property_name, (None, None, None))
    return {
        "name": property_name,
        "widget_name": _CAPABILITY_WIDGETS.get(property_name),
        "supported": bool(supported),
        "readable": bool(readable),
        "writable": bool(writable),
        "visible": _CAPABILITY_WIDGETS.get(property_name) is not None,
        "enabled": bool(supported),
        "unit": unit,
        "minimum": minimum,
        "maximum": maximum,
        "reason": reason,
    }


def _material_capabilities(component, mesh_name, material_name):
    shader_parameters = _shader_names(component, mesh_name, material_name)
    shader_textures = _shader_texture_names(component, mesh_name, material_name)
    properties = []
    names = list(dict.fromkeys(list(_MATERIAL_GETTERS) + list(_MATERIAL_PROPERTY_SETTERS)))
    names.extend(("hair_alpha_multiplier", "hair_alpha_power", "roughness_multiplier", "volume_thickness", "roughness_scale"))
    for property_name in names:
        getter = _MATERIAL_GETTERS.get(property_name)
        setter = _MATERIAL_PROPERTY_SETTERS.get(property_name)
        readable = getter is not None and getattr(component, getter[0], None) is not None
        writable = setter is not None and getattr(component, setter[0], None) is not None
        generic_name = _generic_parameter_name(component, mesh_name, material_name, property_name)
        if generic_name is not None:
            readable = getattr(component, "GetShaderParameter", None) is not None
            writable = getattr(component, "SetShaderParameter", None) is not None
        reason = None
        if property_name == "roughness_scale":
            readable = False
            writable = False
            reason = "The legacy global PBR roughness-scale API is deprecated; no new global material field is exposed."
        elif not readable and not writable:
            reason = "The installed material component does not expose this property."
        item = _capability(property_name, readable, writable, readable or writable, reason)
        if generic_name is not None:
            item["source"] = "shader_parameter"
            item["parameter_name"] = generic_name
        elif getter is not None or setter is not None:
            item["source"] = "RIMaterialComponent"
        properties.append(item)

    for channel_name, aliases in _GENERIC_TEXTURE_ALIASES.items():
        texture_name = _find_shader_name(shader_textures, aliases)
        properties.append(
            {
                "name": channel_name,
                "widget_name": None,
                "supported": texture_name is not None and getattr(component, "LoadShaderTexture", None) is not None,
                "readable": texture_name is not None,
                "writable": texture_name is not None and getattr(component, "LoadShaderTexture", None) is not None,
                "visible": False,
                "enabled": texture_name is not None,
                "unit": "file_path",
                "minimum": None,
                "maximum": None,
                "reason": None if texture_name is not None else "The material does not declare this shader texture.",
                "source": "shader_texture",
                "texture_name": texture_name,
            }
        )
    return properties


def get_material_capabilities(args):
    obj, component, index, mesh_name, material_name = _material_target(args)
    return {
        "name": obj.GetName(),
        "material_index": index,
        "mesh": mesh_name,
        "material": material_name,
        "shader": str(component.GetShader(mesh_name, material_name)) if getattr(component, "GetShader", None) else None,
        "properties": _material_capabilities(component, mesh_name, material_name),
        "shader_parameters": _shader_names(component, mesh_name, material_name),
        "shader_textures": _shader_texture_names(component, mesh_name, material_name),
    }


def get_material_shader_parameters(args):
    obj, component, index, mesh_name, material_name = _material_target(args)
    names = _shader_names(component, mesh_name, material_name)
    getter = getattr(component, "GetShaderParameter", None)
    if getter is None:
        raise RuntimeError("This iClone installation does not expose shader parameter inspection")
    values = {}
    for parameter_name in names:
        value = _generic_parameter_value(component, mesh_name, material_name, parameter_name)
        if value is not None:
            values[parameter_name] = value
    return {"name": obj.GetName(), "material_index": index, "mesh": mesh_name, "material": material_name, "parameters": values}


def set_material_shader_parameter(args):
    obj, component, index, mesh_name, material_name = _material_target(args)
    parameter = args.get("parameter")
    if not isinstance(parameter, str) or not parameter:
        raise ValueError("parameter must be a non-empty string")
    parameter_name = _find_shader_name(_shader_names(component, mesh_name, material_name), (parameter,))
    if parameter_name is None:
        raise ValueError("Unknown shader parameter: {0}".format(parameter))
    setter = getattr(component, "SetShaderParameter", None)
    if setter is None:
        raise RuntimeError("This iClone installation does not expose shader parameter setting")
    requested = _shader_values(args.get("value"))
    result = setter(mesh_name, material_name, parameter_name, requested)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set shader parameter: {0}".format(parameter_name))
    readback = _generic_parameter_value(component, mesh_name, material_name, parameter_name)
    if readback is None or not _values_equal(readback, requested[0] if len(requested) == 1 else requested):
        raise RuntimeError("Shader parameter write was not observable: {0}".format(parameter_name))
    return {
        "status": "ok",
        "name": obj.GetName(),
        "material_index": index,
        "parameter": parameter_name,
        "requested": requested,
        "readback": readback,
    }


def get_material_shader_textures(args):
    obj, component, index, mesh_name, material_name = _material_target(args)
    return {
        "name": obj.GetName(),
        "material_index": index,
        "mesh": mesh_name,
        "material": material_name,
        "textures": _shader_texture_names(component, mesh_name, material_name),
    }


def get_materials(args):
    view = args.get("view") or "properties"
    if view not in ("properties", "render_bindings"):
        raise ValueError("view must be properties or render_bindings")
    if args.get("object_id") is not None:
        from iclone_mcp_commands import _require_object
        obj = _require_object(args["object_id"])
    else:
        if not isinstance(args.get("name"), str) or not args["name"]:
            raise ValueError("Provide object_id or name")
        obj = _find(args["name"])
    if view == "render_bindings":
        if args.get("material_index") is not None:
            raise ValueError("material_index applies to the properties view; render_bindings reports native mesh slots")
        try:
            import RLPy2
            query, system = RLPy2.Query.GetInterface(), RLPy2.System.GetInterface()
            handles = query.GetObjectMeshes(system.ToHandle(obj.GetID()))
        except (ImportError, AttributeError):
            raise RuntimeError("Render material inspection requires the updated RLPy2 API; rebuild and restart the application")
        meshes = []
        for handle in handles:
            mesh = RLPy2.IMesh.GetObject(handle)
            if mesh is None or not hasattr(mesh, "GetRenderMaterialDiagnostics"):
                raise RuntimeError("Render material inspection requires IMesh.GetRenderMaterialDiagnostics; rebuild and restart the application")
            meshes.append({"name": str(query.HandleName(handle)), "render_bindings": mesh.GetRenderMaterialDiagnostics()})
        return {"object_id": str(obj.GetID()), "name": obj.GetName(), "view": view, "meshes": meshes}
    component, targets = _targets(obj)
    selected = args.get("material_index")
    if selected is not None and (isinstance(selected, bool) or not isinstance(selected, int) or selected < 0 or selected >= len(targets)):
        raise ValueError("Material index not found: %s" % selected)
    materials = []
    for index, (mesh_name, material_name) in enumerate(targets):
        if selected is not None and index != selected:
            continue
        color = component.GetDiffuseColor(mesh_name, material_name)
        item = {
            "index": index,
            "mesh": mesh_name,
            "name": material_name,
            "diffuse": _material_value(color, "color"),
        }
        for label, method_name in (
            ("ambient", "GetAmbientColor"),
            ("specular", "GetSpecularColor"),
        ):
            method = getattr(component, method_name, None)
            if method:
                try:
                    item[label] = _material_value(method(mesh_name, material_name), "color")
                except Exception:
                    item[label] = None
        for label, method_name in (
            ("glossiness", "GetGlossinessWeight"),
            ("specular_weight", "GetSpecularWeight"),
            ("opacity", "GetOpacity"),
            ("self_illumination", "GetSelfIlluminationWeight"),
        ):
            method = getattr(component, method_name, None)
            if method:
                try:
                    item[label] = method(mesh_name, material_name)
                except Exception:
                    item[label] = None
        for label, (method_name, kind) in _MATERIAL_GETTERS.items():
            method = getattr(component, method_name, None)
            if method:
                try:
                    item[label] = _material_value(method(mesh_name, material_name), kind)
                except Exception:
                    item[label] = None
        item["attributes"] = {}
        get_attribute = getattr(component, "GetAttributeValue", None)
        if get_attribute:
            for attribute in _MATERIAL_ATTRIBUTES:
                try:
                    item["attributes"][attribute] = get_attribute(mesh_name, material_name, attribute)
                except Exception:
                    item["attributes"][attribute] = None
        item["shader_parameters"] = {}
        for parameter_name in _shader_names(component, mesh_name, material_name):
            try:
                value = _generic_parameter_value(component, mesh_name, material_name, parameter_name)
                if value is not None:
                    item["shader_parameters"][parameter_name] = value
            except Exception:
                continue
        item["shader_textures"] = _shader_texture_names(component, mesh_name, material_name)
        for property_name in ("hair_alpha_multiplier", "hair_alpha_power", "roughness_multiplier", "volume_thickness"):
            try:
                value = _read_property(component, mesh_name, material_name, property_name)
                if value is not None:
                    item[property_name] = value
            except Exception:
                item[property_name] = None
        materials.append(item)
    return {"name": obj.GetName(), "materials": materials}


def get_material_shader_names(args):
    obj, component, index, mesh_name, material_name = _material_target(args)
    get_names = getattr(component, "GetShaderNames", None)
    get_shader = getattr(component, "GetShader", None)
    if get_names is None or get_shader is None:
        raise RuntimeError("This iClone installation does not expose shader inspection")
    return {
        "name": obj.GetName(),
        "material_index": index,
        "mesh": mesh_name,
        "material": material_name,
        "current": str(get_shader(mesh_name, material_name)),
        "shaders": [str(value) for value in get_names()],
    }


def get_material_shader(args):
    return get_material_shader_names(args)


def convert_material_shader(args):
    obj, component, index, mesh_name, material_name = _material_target(args)
    target_shader = args.get("shader") or args.get("target_shader")
    if not isinstance(target_shader, str) or not target_shader:
        raise ValueError("shader must be a non-empty string")
    before = str(component.GetShader(mesh_name, material_name))
    result = set_material_shader(dict(args, shader=target_shader))
    result.update({"before_shader": before, "after_shader": result["readback"]})
    return result


def get_material_domain(args):
    return _property_result(args, "material_domain")


def set_material_domain(args):
    return set_material_property(dict(args, property="material_domain", value=args["domain"]))


def get_material_slider_state(args):
    obj, component, index, mesh_name, material_name = _material_target(args)
    return {
        "name": obj.GetName(),
        "material_index": index,
        "roughness_enabled": bool(component.GetUseRoughnessSlider(mesh_name, material_name))
        if getattr(component, "GetUseRoughnessSlider", None)
        else None,
        "metalness_enabled": bool(component.GetUseMetalnessSlider(mesh_name, material_name))
        if getattr(component, "GetUseMetalnessSlider", None)
        else None,
    }


def set_material_slider_state(args):
    updates = []
    for property_name, argument_name in (("use_roughness_slider", "roughness_enabled"), ("use_metalness_slider", "metalness_enabled")):
        if argument_name in args:
            updates.append(set_material_property(dict(args, property=property_name, value=args[argument_name])))
    if not updates:
        raise ValueError("Provide roughness_enabled or metalness_enabled")
    return {"status": "ok", "name": args["name"], "material_index": args.get("material_index", 0), "readback": get_material_slider_state(args)}


def get_material_glow_color(args):
    return _property_result(args, "glow_color")


def set_material_glow_color(args):
    return set_material_property(dict(args, property="glow_color", value=args["color"]))


def set_material_glow_map(args):
    return set_material_texture(dict(args, channel="glow", texture_path=args["texture_path"]))


def _property_result(args, property_name):
    obj, component, index, mesh_name, material_name = _material_target(args)
    value = _read_property(component, mesh_name, material_name, property_name)
    if value is None:
        raise RuntimeError("Material property is not readable: {0}".format(property_name))
    return {"name": obj.GetName(), "material_index": index, "property": property_name, "value": value, "readback": value}


def set_material_shader(args):
    obj, component, index, mesh_name, material_name = _material_target(args)
    shader = args.get("shader")
    if not isinstance(shader, str) or not shader:
        raise ValueError("shader must be a non-empty string")
    get_names = getattr(component, "GetShaderNames", None)
    get_shader = getattr(component, "GetShader", None)
    method = getattr(component, "SetShader", None)
    if get_names is None or get_shader is None or method is None:
        raise RuntimeError("This iClone installation does not expose shader setting")
    shaders = [str(value) for value in get_names()]
    if shader not in shaders:
        raise ValueError("Unsupported shader. Use one of: %s" % ", ".join(shaders))
    result = method(mesh_name, material_name, shader)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set the material shader")
    readback = str(get_shader(mesh_name, material_name))
    if readback != shader:
        raise RuntimeError("Material shader write was not observable")
    return {
        "status": "ok",
        "name": obj.GetName(),
        "material_index": index,
        "mesh": mesh_name,
        "material": material_name,
        "shader": shader,
        "requested": shader,
        "readback": readback,
    }


def set_material_color(args):
    obj, component, index, mesh_name, material_name = _material_target(args)
    color = args["color"]
    key = _current_key()
    rgb = RLPy.RRgb(color.get("r", 1.0), color.get("g", 1.0), color.get("b", 1.0))
    override_texture = args.get("override_diffuse_texture", True)
    if override_texture:
        result = component.AddTextureWeightKey(
            key,
            mesh_name,
            material_name,
            RLPy.EMaterialTextureChannel_Diffuse,
            0.0,
        )
        if result != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not reduce diffuse texture contribution")
    result = component.AddDiffuseKey(key, mesh_name, material_name, rgb)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not apply diffuse color")
    return {
        "status": "ok",
        "name": obj.GetName(),
        "material_index": index,
        "color": color,
        "override_diffuse_texture": override_texture,
    }


def set_material_texture(args):
    texture_path = os.path.abspath(args["texture_path"])
    if not os.path.isfile(texture_path):
        raise ValueError("Texture file not found: %s" % texture_path)
    channel_name = args.get("channel", "diffuse").lower()
    enum_name = _TEXTURE_CHANNELS.get(channel_name)
    obj, component, index, mesh_name, material_name = _material_target(args)
    generic_texture_name = None
    if enum_name is None:
        generic_texture_name = _generic_texture_name(component, mesh_name, material_name, channel_name)
        if generic_texture_name is None:
            raise ValueError("Unsupported channel. Use one of: %s" % ", ".join(sorted(set(_TEXTURE_CHANNELS) | set(_GENERIC_TEXTURE_ALIASES))))
        method = getattr(component, "LoadShaderTexture", None)
        if method is None:
            raise RuntimeError("This iClone installation does not expose shader texture setting")
        result = method(mesh_name, material_name, generic_texture_name, texture_path)
    else:
        channel = getattr(RLPy, enum_name, None)
        if channel is None:
            raise RuntimeError("This iClone installation does not expose material channel: %s" % channel_name)
        result = component.LoadImageToTexture(mesh_name, material_name, channel, texture_path)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not load the texture into the %s channel" % channel_name)
    if generic_texture_name is not None and generic_texture_name not in _shader_texture_names(component, mesh_name, material_name):
        raise RuntimeError("Shader texture write was not observable: {0}".format(generic_texture_name))
    return {
        "status": "ok",
        "name": obj.GetName(),
        "material_index": index,
        "channel": channel_name,
        "texture_path": texture_path,
        "texture_name": generic_texture_name,
        "readback": {"declared": generic_texture_name is not None or enum_name is not None},
    }


def remove_material_texture(args):
    obj, component, index, mesh_name, material_name = _material_target(args)
    channel_name = args.get("channel", "diffuse").lower()
    enum_name = _TEXTURE_CHANNELS.get(channel_name)
    channel = getattr(RLPy, enum_name, None) if enum_name else None
    if channel is None:
        raise ValueError("Unsupported texture channel: %s" % channel_name)
    result = component.RemoveMaterialTexture(mesh_name, material_name, channel)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not remove the %s texture" % channel_name)
    return {"status": "ok", "name": obj.GetName(), "material_index": index, "channel": channel_name}


def set_material_value(args):
    property_name = args["property"].lower()
    if property_name not in {"opacity", "glossiness", "self_illumination"}:
        raise ValueError("Use set_material_property for extended material properties")
    value = float(args["value"])
    if value < 0.0 or value > 1.0:
        raise ValueError("Material value must be between 0 and 1")
    args = dict(args)
    args["value"] = value
    return set_material_property(args)


def set_material_property(args):
    # Convenience routing so the advertised property bag covers former sibling tools.
    property_name = args.get("property")
    if isinstance(property_name, str):
        property_name = property_name.lower()
    # Do not special-case property=glow_color here: set_material_glow_color routes
    # into this function with value=..., and the normal setter table handles it.
    if "color" in args and property_name is None and "channel" in args:
        return set_material_color_channel(args)
    if "color" in args and property_name is None:
        return set_material_color(args)
    if "domain" in args and property_name is None:
        return set_material_domain(args)
    if ("roughness_enabled" in args or "metalness_enabled" in args) and property_name is None:
        return set_material_slider_state(args)
    if "attribute" in args and "value" in args and property_name in (None, "attribute"):
        return set_material_attribute(args)
    if property_name == "alpha_threshold" or (
        "value" in args and "enabled" in args and property_name is None
    ):
        return set_material_alpha_threshold(args)
    if property_name is None:
        raise ValueError("property is required unless using color/domain/slider/attribute shortcuts")

    property_name = property_name.lower()
    spec = _MATERIAL_PROPERTY_SETTERS.get(property_name)
    obj, component, index, mesh_name, material_name = _material_target(args)
    if property_name == "roughness_scale":
        raise ValueError("roughness_scale is a deprecated global setting; use a material-local shader parameter instead")
    if property_name == "gi_thickness" and (
        isinstance(args["value"], bool) or args["value"] not in (1, 2, 1.0, 2.0)
    ):
        raise ValueError("gi_thickness must be the engine factor 1.0 or 2.0")
    before = _read_property(component, mesh_name, material_name, property_name)
    if spec is None:
        parameter_name = _generic_parameter_name(component, mesh_name, material_name, property_name)
        if parameter_name is None:
            raise ValueError("Unsupported property. Use get_material_capabilities first")
        setter = getattr(component, "SetShaderParameter", None)
        if setter is None:
            raise RuntimeError("This iClone installation does not expose shader parameter setting")
        requested_values = _shader_values(args["value"])
        result = setter(mesh_name, material_name, parameter_name, requested_values)
        if result != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not apply material shader parameter %s" % parameter_name)
        readback = _generic_parameter_value(component, mesh_name, material_name, parameter_name)
        requested = requested_values[0] if len(requested_values) == 1 else requested_values
        if readback is None or not _values_equal(readback, requested):
            raise RuntimeError("Material shader parameter write was not observable: %s" % parameter_name)
        return {
            "status": "ok",
            "name": obj.GetName(),
            "material_index": index,
            "property": property_name,
            "parameter_name": parameter_name,
            "value": args["value"],
            "requested": args["value"],
            "effective": readback,
            "changed": not _values_equal(before, readback),
            "readback": readback,
        }
    method_name, kind, uses_key = spec
    method = getattr(component, method_name, None)
    if method is None:
        raise RuntimeError("This iClone installation does not expose: %s" % method_name)
    value = _property_input(args["value"], kind)
    call_args = (_current_key(), mesh_name, material_name, value) if uses_key else (mesh_name, material_name, value)
    result = method(*call_args)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not apply material property %s" % property_name)
    readback = _read_property(component, mesh_name, material_name, property_name)
    if readback is None:
        raise RuntimeError("Material property has no readable capability: %s" % property_name)
    requested = _material_value(value, kind)
    if not _values_equal(readback, requested):
        raise RuntimeError("Material property write was not observable: %s" % property_name)
    return {
        "status": "ok",
        "name": obj.GetName(),
        "material_index": index,
        "property": property_name,
        "value": args["value"],
        "requested": args["value"],
        "effective": readback,
        "changed": not _values_equal(before, readback),
        "readback": readback,
    }


def set_material_alpha_threshold(args):
    _obj, component, index, mesh_name, material_name = _material_target(args)
    value = float(args.get("value", 0))
    if not 0.0 <= value <= 100.0:
        raise ValueError("value must be between 0 and 100")
    settings = RLPy.MaterialSettings()
    settings.bAlphaThreashold = bool(args.get("enabled", True))
    settings.fAlphaThreshold = value
    settings.fShadowThreshold = 100.0
    result = component.SetMaterialSettings(settings, mesh_name, material_name)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set the material alpha threshold")
    return {
        "status": "ok",
        "name": args["name"],
        "material_index": index,
        "mesh": mesh_name,
        "material": material_name,
        "enabled": settings.bAlphaThreashold,
        "value": value,
    }


def share_material(args):
    from iclone_mcp_commands import _require_object, _require_object_ids
    from iclone_mcp_tool_scene import get_mesh_sharing

    source_id = args.get("source_object_id")
    target_id = args.get("target_object_id")
    ids = _require_object_ids([source_id, target_id], allow_empty=False)
    source = _require_object(source_id)
    target = _require_object(target_id)
    for prefix, obj in (("source", source), ("target", target)):
        index = args.get(prefix + "_material_index")
        if type(index) is not int or index < 0:
            raise ValueError(prefix + "_material_index must be a non-negative integer")
        if not callable(getattr(obj, "GetMaterialComponent", None)):
            raise ValueError(prefix + " object has no material component")
        if obj.GetMaterialComponent() is None:
            raise ValueError(prefix + " object has no material component")
        component, targets = _targets(obj)
        if component is None or index >= len(targets):
            raise ValueError(prefix + "_material_index is out of range")
    try:
        import RLPy2
        method = RLPy2.Edit.GetInterface().ShareMaterial
        system = RLPy2.System.GetInterface()
    except (ImportError, AttributeError):
        raise RuntimeError("Material sharing requires the updated RLPy2.Edit API; rebuild and restart the application.")
    changed = method(system.ToHandle(source.GetID()), args["source_material_index"],
                     system.ToHandle(target.GetID()), args["target_material_index"])
    return {
        "status": "ok", "changed": bool(changed),
        "source_object_id": source_id, "source_material_index": args["source_material_index"],
        "target_object_id": target_id, "target_material_index": args["target_material_index"],
        "sharing": get_mesh_sharing({"object_ids": ids}),
    }


def make_material_unique(args):
    obj, component, index, mesh_name, material_name = _material_target(args)
    method = getattr(component, "MakeUnique", None)
    if method is None:
        raise RuntimeError("This iClone installation does not expose: MakeUnique")
    result = method(mesh_name, material_name)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not make the material unique")
    return {
        "status": "ok",
        "name": obj.GetName(),
        "material_index": index,
        "mesh": mesh_name,
        "material": material_name,
    }


def set_metal_mirror_material(args):
    for property_name, value in (
        ("use_metalness_slider", True),
        ("use_roughness_slider", True),
        ("metalness", 1.0),
        ("roughness", 0.0),
    ):
        set_material_property(dict(args, property=property_name, value=value))
    return {
        "status": "ok",
        "name": args["name"],
        "material_index": args.get("material_index", 0),
        "metalness": 1.0,
        "roughness": 0.0,
    }


def set_material_color_channel(args):
    obj, component, index, mesh_name, material_name = _material_target(args)
    channel = args.get("channel", "diffuse").lower()
    methods = {
        "ambient": "AddAmbientKey",
        "diffuse": "AddDiffuseKey",
        "specular": "AddSpecularKey",
    }
    method = getattr(component, methods.get(channel, ""), None)
    if method is None:
        raise ValueError("channel must be ambient, diffuse, or specular")
    color = args["color"]
    result = method(
        _current_key(),
        mesh_name,
        material_name,
        RLPy.RRgb(color.get("r", 1), color.get("g", 1), color.get("b", 1)),
    )
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set material color channel")
    return {"status": "ok", "name": obj.GetName(), "material_index": index, "channel": channel, "color": color}


def set_texture_weight(args):
    obj, component, index, mesh_name, material_name = _material_target(args)
    channel_name = args.get("channel", "diffuse").lower()
    enum_name = _TEXTURE_CHANNELS.get(channel_name)
    channel = getattr(RLPy, enum_name, None) if enum_name else None
    if channel is None:
        raise ValueError("Unsupported texture channel: %s" % channel_name)
    weight = float(args["weight"])
    if weight < 0 or weight > 1:
        raise ValueError("weight must be between 0 and 1")
    result = component.AddTextureWeightKey(_current_key(), mesh_name, material_name, channel, weight)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set texture weight")
    return {"status": "ok", "name": obj.GetName(), "material_index": index, "channel": channel_name, "weight": weight}


def set_uv_data(args):
    obj, component, index, mesh_name, material_name = _material_target(args)
    channel_name = args.get("channel", "diffuse").lower()
    enum_name = _TEXTURE_CHANNELS.get(channel_name)
    channel = getattr(RLPy, enum_name, None) if enum_name else None
    if channel is None:
        raise ValueError("Unsupported texture channel: %s" % channel_name)
    offset, tile = args.get("offset", {}), args.get("tile", {})
    uv_offset = RLPy.RVector2(offset.get("x", 0), offset.get("y", 0))
    uv_tile = RLPy.RVector2(tile.get("x", 1), tile.get("y", 1))
    rotate = math.radians(float(args.get("rotate_degrees", 0)))
    result = component.AddUvDataKey(_current_key(), mesh_name, material_name, channel, uv_offset, uv_tile, rotate)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set UV data")
    return {"status": "ok", "name": obj.GetName(), "material_index": index, "channel": channel_name, "offset": offset, "tile": tile, "rotate_degrees": float(args.get("rotate_degrees", 0))}


def remove_uv_data(args):
    obj, component, index, mesh_name, material_name = _material_target(args)
    channel_name = args.get("channel", "diffuse").lower()
    enum_name = _TEXTURE_CHANNELS.get(channel_name)
    channel = getattr(RLPy, enum_name, None) if enum_name else None
    if channel is None:
        raise ValueError("Unsupported texture channel: %s" % channel_name)
    result = component.RemoveUvDataKey(_current_key(), mesh_name, material_name, channel)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not remove UV data")
    return {"status": "ok", "name": obj.GetName(), "material_index": index, "channel": channel_name}


def load_video_texture(args):
    obj, component, index, mesh_name, material_name = _material_target(args)
    video_path = os.path.abspath(args["video_path"])
    if not os.path.isfile(video_path):
        raise FileNotFoundError("Video file not found: %s" % video_path)
    channel_name = args.get("channel", "diffuse").lower()
    enum_name = _TEXTURE_CHANNELS.get(channel_name)
    channel = getattr(RLPy, enum_name, None) if enum_name else None
    if channel is None:
        raise ValueError("Unsupported texture channel: %s" % channel_name)
    key = _current_key()
    result = component.LoadVideoToTexture(key, mesh_name, material_name, channel, video_path)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not load video texture")
    if "volume" in args and hasattr(component, "AddVideoVolumeKey"):
        volume = float(args["volume"])
        if component.AddVideoVolumeKey(key, mesh_name, material_name, channel, volume, bool(args.get("mute", False))) != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not set video texture volume")
    return {"status": "ok", "name": obj.GetName(), "material_index": index, "channel": channel_name, "video_path": video_path}


def set_material_attribute(args):
    obj, component, index, mesh_name, material_name = _material_target(args)
    method = getattr(component, "SetAttributeValue", None)
    if method is None:
        raise RuntimeError("This iClone installation does not expose SetAttributeValue")
    attribute = args["attribute"]
    if attribute not in _MATERIAL_ATTRIBUTES:
        raise ValueError("Unsupported attribute")
    value = float(args["value"])
    result = method(mesh_name, material_name, attribute, value)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not set material attribute")
    return {"status": "ok", "name": obj.GetName(), "material_index": index, "attribute": attribute, "value": value}


def get_material_attribute(args):
    obj, component, index, mesh_name, material_name = _material_target(args)
    method = getattr(component, "GetAttributeValue", None)
    if method is None:
        raise RuntimeError("This iClone installation does not expose GetAttributeValue")
    attribute = args["attribute"]
    if attribute not in _MATERIAL_ATTRIBUTES:
        raise ValueError("Unsupported attribute")
    value = method(mesh_name, material_name, attribute)
    return {"name": obj.GetName(), "material_index": index, "attribute": attribute, "value": float(value)}


def material_texture(args):
    action = (args.get("action") or "load").lower()
    if action == "load":
        return set_material_texture(args)
    if action == "remove":
        return remove_material_texture(args)
    if action == "load_video":
        return load_video_texture(args)
    if action == "set_weight":
        return set_texture_weight(args)
    if action == "set_uv":
        return set_uv_data(args)
    if action == "remove_uv":
        return remove_uv_data(args)
    raise ValueError(
        "action must be one of: load, remove, load_video, set_weight, set_uv, remove_uv"
    )


def material_shader(args):
    action = (args.get("action") or "get").lower()
    if action in {"get", "list"}:
        return get_material_shader_names(args)
    if action == "set":
        return set_material_shader(args)
    if action == "convert":
        return convert_material_shader(args)
    if action == "get_parameters":
        return get_material_shader_parameters(args)
    if action == "set_parameter":
        return set_material_shader_parameter(args)
    if action == "list_textures":
        return get_material_shader_textures(args)
    raise ValueError(
        "action must be one of: get, list, set, convert, get_parameters, set_parameter, list_textures"
    )


def register(registry):
    common = {
        "name": {"type": "string"},
        "material_index": {"type": "integer"},
    }
    registry["get_materials"] = {
        "handler": get_materials,
        "main_thread": True,
        "read_only": True,
        "description": "Inspect material properties or lightweight native renderer bindings. Prefer a stable object_id; material_index limits property inspection to one slot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "object_id": {"type": "string"},
                "material_index": {"type": "integer", "minimum": 0},
                "view": {"type": "string", "enum": ["properties", "render_bindings"]},
            },
            "anyOf": [{"required": ["object_id"]}, {"required": ["name"]}],
        },
    }
    registry["get_material_capabilities"] = {
        "handler": get_material_capabilities,
        "main_thread": True,
        "read_only": True,
        "description": "Inspect material properties, shader parameters, texture slots, widget names, and read/write capabilities.",
        "inputSchema": {"type": "object", "properties": common, "required": ["name"]},
    }
    registry["set_material_property"] = {
        "handler": set_material_property,
        "main_thread": True,
        "description": "Set RIMaterialComponent properties (scalars, vectors, domain, glow mode/color, tessellation attributes).",
        "inputSchema": {"type": "object", "properties": dict(common, property={"type": "string"}, value={}, channel={"type": "string"}, color={"type": "object"}, domain={"type": "string"}, attribute={"type": "string"}, enabled={"type": "boolean"}, override_diffuse_texture={"type": "boolean"}, roughness_enabled={"type": "boolean"}, metalness_enabled={"type": "boolean"}), "required": ["name"]},
    }
    registry["material_texture"] = {
        "handler": material_texture,
        "main_thread": True,
        "description": "Load, remove, weight, UV-key, or video-load a material texture channel. Use channel 'glow' for Glow Map.",
        "inputSchema": {
            "type": "object",
            "properties": dict(
                common,
                action={"type": "string", "enum": ["load", "remove", "load_video", "set_weight", "set_uv", "remove_uv"]},
                channel={"type": "string"},
                texture_path={"type": "string"},
                video_path={"type": "string"},
                weight={"type": "number", "minimum": 0, "maximum": 1},
                offset={"type": "object"},
                tile={"type": "object"},
                rotate_degrees={"type": "number"},
                volume={"type": "number"},
                mute={"type": "boolean"},
            ),
            "required": ["name", "action"],
        },
    }
    registry["material_shader"] = {
        "handler": material_shader,
        "main_thread": True,
        "description": "Inspect or change a material shader and its declared parameters/textures.",
        "inputSchema": {
            "type": "object",
            "properties": dict(
                common,
                action={"type": "string", "enum": ["get", "list", "set", "convert", "get_parameters", "set_parameter", "list_textures"]},
                shader={"type": "string"},
                target_shader={"type": "string"},
                parameter={"type": "string"},
                value={},
            ),
            "required": ["name", "action"],
        },
    }
    registry['share_material'] = {
        "handler": share_material,
        "main_thread": True,
        "description": 'Assign the source material instance to one target slot without changing geometry or slot order. Material indices follow get_materials. Later edits affect all users of the shared material. Supports undo.',
        "inputSchema": {'type': 'object', 'properties': {'source_object_id': {'type': 'string'}, 'source_material_index': {'type': 'integer', 'minimum': 0}, 'target_object_id': {'type': 'string'}, 'target_material_index': {'type': 'integer', 'minimum': 0}}, 'required': ['source_object_id', 'source_material_index', 'target_object_id', 'target_material_index']},
    }
    registry["make_material_unique"] = {
        "handler": make_material_unique,
        "main_thread": True,
        "description": "Make one object's material instance independent from shared material instances.",
        "inputSchema": {"type": "object", "properties": common, "required": ["name"]},
    }
    registry["set_metal_mirror_material"] = {
        "handler": set_metal_mirror_material,
        "main_thread": True,
        "description": "Configure a material as a metal mirror with metalness 1 and roughness 0.",
        "inputSchema": {"type": "object", "properties": common, "required": ["name"]},
    }

    # Legacy wrappers kept for bridge dispatch; not advertised to MCP clients.
    _hidden = {"advertise": False, "main_thread": True}
    registry["get_material_domain"] = dict(_hidden, handler=get_material_domain, description="Read the material domain for one material.", inputSchema={"type": "object", "properties": common, "required": ["name"]}, read_only=True)
    registry["set_material_domain"] = dict(_hidden, handler=set_material_domain, description="Set a material domain and return verified readback.", inputSchema={"type": "object", "properties": dict(common, domain={"type": "string", "enum": ["opaque", "alpha_tested", "alpha_blended", "transmissive", "transmissive_alpha_tested", "transmissive_alpha_blended", "none"]}), "required": ["name", "domain"]})
    registry["get_material_slider_state"] = dict(_hidden, handler=get_material_slider_state, description="Read material roughness and metalness slider enablement.", inputSchema={"type": "object", "properties": common, "required": ["name"]}, read_only=True)
    registry["set_material_slider_state"] = dict(_hidden, handler=set_material_slider_state, description="Set material roughness and/or metalness slider enablement.", inputSchema={"type": "object", "properties": dict(common, roughness_enabled={"type": "boolean"}, metalness_enabled={"type": "boolean"}), "required": ["name"]})
    registry["get_material_shader"] = dict(_hidden, handler=get_material_shader, description="Read the current material shader.", inputSchema={"type": "object", "properties": common, "required": ["name"]}, read_only=True)
    registry["convert_material_shader"] = dict(_hidden, handler=convert_material_shader, description="Convert a material to an available shader and return before/after readback.", inputSchema={"type": "object", "properties": dict(common, shader={"type": "string"}, target_shader={"type": "string"}), "required": ["name"]})
    registry["get_material_shader_parameters"] = dict(_hidden, handler=get_material_shader_parameters, description="Read declared custom shader parameters and their values.", inputSchema={"type": "object", "properties": common, "required": ["name"]}, read_only=True)
    registry["set_material_shader_parameter"] = dict(_hidden, handler=set_material_shader_parameter, description="Set a declared custom shader parameter and verify its value.", inputSchema={"type": "object", "properties": dict(common, parameter={"type": "string"}, value={}), "required": ["name", "parameter", "value"]})
    registry["get_material_shader_textures"] = dict(_hidden, handler=get_material_shader_textures, description="Read declared custom shader texture slots.", inputSchema={"type": "object", "properties": common, "required": ["name"]}, read_only=True)
    registry["get_material_glow_color"] = dict(_hidden, handler=get_material_glow_color, description="Read material Glow Color/emissive color.", inputSchema={"type": "object", "properties": common, "required": ["name"]}, read_only=True)
    registry["set_material_glow_color"] = dict(_hidden, handler=set_material_glow_color, description="Set material Glow Color/emissive color and verify readback.", inputSchema={"type": "object", "properties": dict(common, color={"type": "object"}), "required": ["name", "color"]})
    registry["set_material_glow_map"] = dict(_hidden, handler=set_material_glow_map, description="Load a material Glow Map through the existing glow channel.", inputSchema={"type": "object", "properties": dict(common, texture_path={"type": "string"}), "required": ["name", "texture_path"]})
    registry["get_material_shader_names"] = dict(_hidden, handler=get_material_shader_names, description="List the shader types available for one material and return the current shader.", inputSchema={"type": "object", "properties": common, "required": ["name"]}, read_only=True)
    registry["set_material_shader"] = dict(_hidden, handler=set_material_shader, description="Set one material to an exact shader type returned by get_material_shader_names.", inputSchema={"type": "object", "properties": dict(common, shader={"type": "string"}), "required": ["name", "shader"]})
    registry["set_material_color"] = dict(_hidden, handler=set_material_color, description="Set diffuse RGB color.", inputSchema={"type": "object", "properties": dict(common, color={"type": "object"}, override_diffuse_texture={"type": "boolean"}), "required": ["name", "color"]})
    registry["set_material_texture"] = dict(_hidden, handler=set_material_texture, description="Load an image into a material texture channel; use channel 'glow' for Glow Map.", inputSchema={"type": "object", "properties": dict(common, channel={"type": "string"}, texture_path={"type": "string"}), "required": ["name", "texture_path"]})
    registry["remove_material_texture"] = dict(_hidden, handler=remove_material_texture, description="Remove a material texture channel through the public material API.", inputSchema={"type": "object", "properties": dict(common, channel={"type": "string"}), "required": ["name"]})
    registry["set_material_value"] = dict(_hidden, handler=set_material_value, description="Set opacity, glossiness, or self illumination between 0 and 1.", inputSchema={"type": "object", "properties": dict(common, property={"type": "string"}, value={"type": "number", "minimum": 0, "maximum": 1}), "required": ["name", "property", "value"]})
    registry["set_material_alpha_threshold"] = dict(_hidden, handler=set_material_alpha_threshold, description="Set a material alpha-threshold value between 0 and 100.", inputSchema={"type": "object", "properties": dict(common, enabled={"type": "boolean"}, value={"type": "number", "minimum": 0, "maximum": 100}), "required": ["name", "value"]})
    registry["set_material_color_channel"] = dict(_hidden, handler=set_material_color_channel, description="Set ambient, diffuse, or specular color.", inputSchema={"type": "object", "properties": dict(common, channel={"type": "string", "enum": ["ambient", "diffuse", "specular"]}, color={"type": "object"}), "required": ["name", "channel", "color"]})
    registry["set_texture_weight"] = dict(_hidden, handler=set_texture_weight, description="Set a material texture channel weight between 0 and 1.", inputSchema={"type": "object", "properties": dict(common, channel={"type": "string"}, weight={"type": "number", "minimum": 0, "maximum": 1}), "required": ["name", "weight"]})
    registry["set_uv_data"] = dict(_hidden, handler=set_uv_data, description="Key UV offset, tiling, and rotation for a texture channel.", inputSchema={"type": "object", "properties": dict(common, channel={"type": "string"}, offset={"type": "object"}, tile={"type": "object"}, rotate_degrees={"type": "number"}), "required": ["name"]})
    registry["remove_uv_data"] = dict(_hidden, handler=remove_uv_data, description="Remove the current UV key for a texture channel.", inputSchema={"type": "object", "properties": dict(common, channel={"type": "string"}), "required": ["name"]})
    registry["load_video_texture"] = dict(_hidden, handler=load_video_texture, description="Load a video into a material texture channel.", inputSchema={"type": "object", "properties": dict(common, channel={"type": "string"}, video_path={"type": "string"}, volume={"type": "number"}, mute={"type": "boolean"}), "required": ["name", "video_path"]})
    attribute_schema = dict(common, attribute={"type": "string", "enum": list(_MATERIAL_ATTRIBUTES)})
    registry["set_material_attribute"] = dict(_hidden, handler=set_material_attribute, description="Set a documented RIMaterialComponent tessellation attribute.", inputSchema={"type": "object", "properties": dict(attribute_schema, value={"type": "number"}), "required": ["name", "attribute", "value"]})
    registry["get_material_attribute"] = dict(_hidden, handler=get_material_attribute, description="Read a documented RIMaterialComponent tessellation attribute.", inputSchema={"type": "object", "properties": attribute_schema, "required": ["name", "attribute"]}, read_only=True)
