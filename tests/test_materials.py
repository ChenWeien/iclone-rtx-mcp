import os
import sys
import types


PLUGIN_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "plugin")
)
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

sys.modules.setdefault("RLPy", types.ModuleType("RLPy"))
import iclone_mcp_tool_materials as materials


class Color:
    def R(self):
        return 0.1

    def G(self):
        return 0.2

    def B(self):
        return 0.3


class Vector3:
    def __init__(self, x=0, y=0, z=0):
        self.x, self.y, self.z = x, y, z


class Key:
    def SetTime(self, value):
        self.time = value

    def SetTransitionType(self, value):
        self.transition = value


class MaterialSettings:
    def __init__(self):
        self.bAlphaThreashold = False
        self.fAlphaThreshold = 0
        self.fShadowThreshold = 0


class Component:
    def __init__(self):
        self.calls = []
        self._roughness = 0.4
        self._metalness = 0.0
        self._use_roughness_slider = False
        self._use_metalness_slider = False
        self._use_emissive_color = False
        self._emissive_color = Vector3(0.25, 0.5, 0.75)
        self._shader = "Digital_Human Eye Occlusion"
        self._domain = 10
        self._shader_parameters = {
            "Edge Roughness Multiplier": [1.0],
            "Volume Thickness": [0.5],
        }
        self._shader_textures = ["Coat Normal", "Coat Mask", "Glow Map"]
        self._shader_texture_paths = {}
        self._gi_thickness = 1.0

    def GetMaterialNames(self, mesh):
        return ["body"]

    def GetDiffuseColor(self, mesh, material):
        return Color()

    def GetRoughness(self, mesh, material):
        return self._roughness

    def GetEmissiveColor(self, mesh, material):
        return self._emissive_color

    def GetMetalness(self, mesh, material):
        return self._metalness

    def GetUseEmissiveColor(self, mesh, material):
        return self._use_emissive_color

    def GetMaterialDomain(self, mesh, material):
        return self._domain

    def SetMaterialDomain(self, mesh, material, value):
        self.calls.append(("material_domain", mesh, material, value))
        self._domain = value
        return materials.RLPy.RStatus.Success

    def GetAttributeValue(self, mesh, material, name):
        return 2.0

    def GetGiThickness(self, mesh, material):
        return self._gi_thickness

    def SetGiThickness(self, mesh, material, value):
        self._gi_thickness = value
        return materials.RLPy.RStatus.Success

    def SetUseMetalnessSlider(self, mesh, material, value):
        self.calls.append(("use_metalness_slider", mesh, material, value))
        self._use_metalness_slider = value
        return materials.RLPy.RStatus.Success

    def SetUseRoughnessSlider(self, mesh, material, value):
        self.calls.append(("use_roughness_slider", mesh, material, value))
        self._use_roughness_slider = value
        return materials.RLPy.RStatus.Success

    def GetUseMetalnessSlider(self, mesh, material):
        return self._use_metalness_slider

    def GetUseRoughnessSlider(self, mesh, material):
        return self._use_roughness_slider

    def SetMetalness(self, key, mesh, material, value):
        self.calls.append(("metalness", key.time, mesh, material, value))
        self._metalness = value
        return materials.RLPy.RStatus.Success

    def SetRoughness(self, key, mesh, material, value):
        self.calls.append(("roughness", key.time, mesh, material, value))
        self._roughness = value
        return materials.RLPy.RStatus.Success

    def SetEmissiveColor(self, key, mesh, material, value):
        self.calls.append(("glow_color", key.time, mesh, material, value.x, value.y, value.z))
        self._emissive_color = value
        return materials.RLPy.RStatus.Success

    def SetUseEmissiveColor(self, mesh, material, value):
        self.calls.append(("use_glow_color", mesh, material, value))
        self._use_emissive_color = value
        return materials.RLPy.RStatus.Success

    def LoadImageToTexture(self, mesh, material, channel, path):
        self.calls.append(("glow_map", mesh, material, channel, path))
        return materials.RLPy.RStatus.Success

    def RemoveMaterialTexture(self, mesh, material, channel):
        self.calls.append(("remove_texture", mesh, material, channel))
        return materials.RLPy.RStatus.Success

    def MakeUnique(self, mesh, material):
        self.calls.append(("make_unique", mesh, material))
        return materials.RLPy.RStatus.Success

    def GetShaderNames(self):
        return ["Digital_Human Eye Occlusion", "Digital_Human_Occlusion (HD)"]

    def GetShader(self, mesh, material):
        return self._shader

    def GetShaderParameterNames(self, mesh, material):
        return list(self._shader_parameters)

    def GetShaderParameter(self, mesh, material, name):
        return list(self._shader_parameters.get(name, []))

    def SetShaderParameter(self, mesh, material, name, values):
        if name not in self._shader_parameters:
            return "failure"
        self.calls.append(("shader_parameter", mesh, material, name, list(values)))
        self._shader_parameters[name] = list(values)
        return materials.RLPy.RStatus.Success

    def GetShaderTextureNames(self, mesh, material):
        return list(self._shader_textures)

    def LoadShaderTexture(self, mesh, material, name, path):
        if name not in self._shader_textures:
            return "failure"
        self.calls.append(("shader_texture", mesh, material, name, path))
        self._shader_texture_paths[name] = path
        return materials.RLPy.RStatus.Success

    def SetShader(self, mesh, material, shader):
        self.calls.append(("set_shader", mesh, material, shader))
        self._shader = shader
        return materials.RLPy.RStatus.Success

    def SetMaterialSettings(self, settings, mesh, material):
        self.calls.append(("alpha_threshold", mesh, material, settings.bAlphaThreashold, settings.fAlphaThreshold))
        return materials.RLPy.RStatus.Success


class Object:
    def __init__(self):
        self.component = Component()

    def GetName(self):
        return "Avatar"

    def GetMeshNames(self):
        return ["mesh"]

    def GetMaterialComponent(self):
        return self.component


def setup_module():
    materials.RLPy = types.SimpleNamespace(
        EObjectType_Prop=1,
        EObjectType_Avatar=2,
        EObjectType_Sky=3,
        ETransitionType_Step=4,
        EMaterialTextureChannel_Diffuse=1,
        EMaterialTextureChannel_Glow=4,
        MaterialDomain_Opaque=10,
        MaterialDomain_AlphaBlended=11,
        RStatus=types.SimpleNamespace(Success="success"),
        RKey=Key,
        MaterialSettings=MaterialSettings,
        RVector3=Vector3,
        RGlobal=types.SimpleNamespace(GetTime=lambda: 123),
        RScene=types.SimpleNamespace(FindObject=lambda object_type, name: OBJECT if name == "Avatar" else None),
    )


OBJECT = Object()


def test_new_material_properties_are_read_and_keyed():
    result = materials.get_materials({"name": "Avatar"})
    item = result["materials"][0]
    assert item["roughness"] == 0.4
    assert item["material_domain"] == "opaque"
    assert item["attributes"]["TessellationLevel"] == 2.0

    result = materials.set_material_property(
        {"name": "Avatar", "property": "roughness", "value": 0.8}
    )
    assert result["status"] == "ok"
    assert OBJECT.component.calls[-1] == ("roughness", 123, "mesh", "body", 0.8)


def test_glow_color_mode_and_color_use_existing_material_api():
    item = materials.get_materials({"name": "Avatar"})["materials"][0]
    assert item["use_glow_color"] is False
    assert item["glow_color"] == {"x": 0.25, "y": 0.5, "z": 0.75}

    materials.set_material_property(
        {"name": "Avatar", "property": "use_glow_color", "value": True}
    )
    assert OBJECT.component.calls[-1] == ("use_glow_color", "mesh", "body", True)

    materials.set_material_property(
        {
            "name": "Avatar",
            "property": "glow_color",
            "value": {"r": 0.1, "g": 0.2, "b": 0.3},
        }
    )
    assert OBJECT.component.calls[-1] == (
        "glow_color",
        123,
        "mesh",
        "body",
        0.1,
        0.2,
        0.3,
    )


def test_glow_color_mode_rejects_non_boolean_value():
    try:
        materials.set_material_property(
            {"name": "Avatar", "property": "use_glow_color", "value": 1}
        )
    except ValueError as error:
        assert "boolean" in str(error)
    else:
        assert False


def test_glow_map_uses_existing_glow_texture_channel(tmp_path):
    texture_path = tmp_path / "glow.png"
    texture_path.write_bytes(b"image")

    result = materials.set_material_texture(
        {"name": "Avatar", "channel": "glow", "texture_path": str(texture_path)}
    )

    assert result["status"] == "ok"
    assert result["channel"] == "glow"
    assert OBJECT.component.calls[-1] == (
        "glow_map",
        "mesh",
        "body",
        materials.RLPy.EMaterialTextureChannel_Glow,
        str(texture_path),
    )


def test_remove_material_texture_uses_public_channel_api():
    result = materials.remove_material_texture(
        {"name": "Avatar", "channel": "diffuse"}
    )

    assert result == {
        "status": "ok",
        "name": "Avatar",
        "material_index": 0,
        "channel": "diffuse",
    }
    assert OBJECT.component.calls[-1] == (
        "remove_texture",
        "mesh",
        "body",
        materials.RLPy.EMaterialTextureChannel_Diffuse,
    )


def test_metal_mirror_material_applies_settings_in_order():
    result = materials.set_metal_mirror_material({"name": "Avatar"})

    assert result["status"] == "ok"
    assert OBJECT.component.calls[-4:] == [
        ("use_metalness_slider", "mesh", "body", True),
        ("use_roughness_slider", "mesh", "body", True),
        ("metalness", 123, "mesh", "body", 1.0),
        ("roughness", 123, "mesh", "body", 0.0),
    ]


def test_make_material_unique_targets_selected_material():
    result = materials.make_material_unique({"name": "Avatar"})

    assert result == {
        "status": "ok",
        "name": "Avatar",
        "material_index": 0,
        "mesh": "mesh",
        "material": "body",
    }
    assert OBJECT.component.calls[-1] == ("make_unique", "mesh", "body")


def test_shader_names_and_exact_shader_setting():
    result = materials.get_material_shader_names({"name": "Avatar"})
    assert result["current"] == "Digital_Human Eye Occlusion"
    assert "Digital_Human_Occlusion (HD)" in result["shaders"]

    result = materials.set_material_shader(
        {"name": "Avatar", "shader": "Digital_Human_Occlusion (HD)"}
    )
    assert result["status"] == "ok"
    assert OBJECT.component.calls[-1] == (
        "set_shader",
        "mesh",
        "body",
        "Digital_Human_Occlusion (HD)",
    )


def test_alpha_threshold_uses_material_settings():
    result = materials.set_material_alpha_threshold({"name": "Avatar", "value": 60})

    assert result["status"] == "ok"
    assert result["enabled"] is True
    assert result["value"] == 60
    assert OBJECT.component.calls[-1] == ("alpha_threshold", "mesh", "body", True, 60.0)


def test_shader_capabilities_and_generic_parameter_readback():
    result = materials.get_material_capabilities({"name": "Avatar"})
    parameter = next(item for item in result["properties"] if item["name"] == "roughness_multiplier")
    assert parameter["supported"] is True
    assert parameter["source"] == "shader_parameter"
    assert parameter["parameter_name"] == "Edge Roughness Multiplier"

    result = materials.set_material_property(
        {"name": "Avatar", "property": "roughness_multiplier", "value": 1.25}
    )
    assert result["effective"] == 1.25
    assert result["changed"] is True

    result = materials.set_material_shader_parameter(
        {"name": "Avatar", "parameter": "Edge Roughness Multiplier", "value": [0.9, 0.8]}
    )
    assert result["readback"] == [0.9, 0.8]
    assert OBJECT.component.calls[-1] == (
        "shader_parameter", "mesh", "body", "Edge Roughness Multiplier", [0.9, 0.8]
    )


def test_domain_sliders_and_coat_texture_use_verified_paths(tmp_path):
    result = materials.set_material_domain(
        {"name": "Avatar", "domain": "alpha_blended"}
    )
    assert result["effective"] == "alpha_blended"

    result = materials.set_material_slider_state(
        {"name": "Avatar", "roughness_enabled": True, "metalness_enabled": True}
    )
    assert result["readback"]["roughness_enabled"] is True
    assert result["readback"]["metalness_enabled"] is True

    texture_path = str(tmp_path / "coat-normal-test.png")
    (tmp_path / "coat-normal-test.png").write_bytes(b"image")
    result = materials.set_material_texture(
        {"name": "Avatar", "channel": "coat_normal", "texture_path": texture_path}
    )
    assert result["texture_name"] == "Coat Normal"
    assert OBJECT.component.calls[-1] == (
        "shader_texture", "mesh", "body", "Coat Normal", texture_path
    )


def test_gi_thickness_keeps_the_engine_factor_contract():
    result = materials.set_material_property(
        {"name": "Avatar", "property": "gi_thickness", "value": 2.0}
    )
    assert result["effective"] == 2.0
    try:
        materials.set_material_property(
            {"name": "Avatar", "property": "gi_thickness", "value": 1.5}
        )
    except ValueError as error:
        assert "engine factor" in str(error)
    else:
        assert False


def test_unknown_shader_parameter_is_a_capability_error():
    try:
        materials.set_material_shader_parameter(
            {"name": "Avatar", "parameter": "Missing Parameter", "value": 1.0}
        )
    except ValueError as error:
        assert "Unknown shader parameter" in str(error)
    else:
        assert False
