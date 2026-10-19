import os
import sys
import types


PLUGIN_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "plugin")
)
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

RLPy = sys.modules.setdefault("RLPy", types.ModuleType("RLPy"))
RLPy.EObjectType_Prop = 0
RLPy.EObjectType_Avatar = 1
RLPy.EObjectType_Camera = 2
RLPy.EObjectType_Particle = 3
RLPy.EObjectType_Light = 4
RLPy.EObjectType_SpotLight = 5
RLPy.EObjectType_PointLight = 6
RLPy.EObjectType_DirectionalLight = 7
import iclone_mcp_tool_lights as lights


class Light:
    def __init__(self, name="Dir. Light", light_type=RLPy.EObjectType_DirectionalLight, object_id="100"):
        self._name = name
        self._type = light_type
        self._id = object_id
        self.angle = None
        self.patch_calls = []

    def GetID(self):
        return self._id

    def GetName(self):
        return self._name

    def GetType(self):
        return self._type

    def GetColor(self):
        return types.SimpleNamespace(R=lambda: 1, G=lambda: 1, B=lambda: 1)

    def GetActive(self):
        return True

    def GetMultiplier(self):
        return 1

    def SetAngle(self, time, value):
        self.angle = (time, value)
        return lights.RLPy.RStatus.Success


class VolumetricLight(Light):
    def __init__(self, name, light_type, object_id):
        super().__init__(name=name, light_type=light_type, object_id=object_id)
        self.enabled = True
        self.unlink = False
        self.intensity = 2.0
        self.scatter = types.SimpleNamespace(X=lambda: 0.9, Y=lambda: 0.2, Z=lambda: 1.0)
        self.medium_density = 354.06
        self.absorption = 0.0
        self.eccentricity = -0.31
        self.tessellation_amount = 0
        self.falloff_power = 1

    def GetVolumetricLightEnable(self):
        return self.enabled

    def GetVolumetricLightUnlinkIntensity(self):
        return self.unlink

    def GetVolumetricLightIntensity(self):
        return self.intensity

    def GetVolumetricLightScatterColor(self):
        return self.scatter

    def GetVolumetricLightMediumDensity(self):
        return self.medium_density

    def GetVolumetricLightAbsorption(self):
        return self.absorption

    def GetVolumetricLightEccentricity(self):
        return self.eccentricity

    def GetVolumetricLightTessellationAmount(self):
        return self.tessellation_amount

    def GetVolumetricLightFalloffPower(self):
        return self.falloff_power

    def SetVolumetricLightEnable(self, value):
        self.enabled = bool(value)
        return lights.RLPy.RStatus.Success

    def SetVolumetricLightUnlinkIntensity(self, value):
        self.unlink = bool(value)
        return lights.RLPy.RStatus.Success

    def SetVolumetricLightTessellationAmount(self, value):
        self.tessellation_amount = int(value)
        return lights.RLPy.RStatus.Success

    def PatchVolumetricLightKey(
        self,
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
        patch_falloff=False,
        falloff_power=1,
    ):
        self.patch_calls.append(
            {
                "patch_intensity": patch_intensity,
                "intensity": intensity,
                "patch_scatter": patch_scatter,
                "patch_density": patch_density,
                "patch_absorption": patch_absorption,
                "patch_eccentricity": patch_eccentricity,
                "patch_falloff": patch_falloff,
            }
        )
        if patch_intensity:
            self.intensity = intensity
        if patch_scatter:
            self.scatter = scatter_color
        if patch_density:
            self.medium_density = medium_density
        if patch_absorption:
            self.absorption = absorption
        if patch_eccentricity:
            self.eccentricity = eccentricity
        if patch_falloff:
            self.falloff_power = falloff_power
        return lights.RLPy.RStatus.Success


class PointVolumetricLight(VolumetricLight):
    def PatchVolumetricLightKey(
        self,
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
    ):
        return super().PatchVolumetricLightKey(
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
            False,
            1,
        )


SPOT_LIGHT = VolumetricLight("Spotlight", RLPy.EObjectType_SpotLight, "559")
POINT_LIGHT = PointVolumetricLight("Point light", RLPy.EObjectType_PointLight, "560")
LIGHT = Light()


def setup_module():
    lights.RLPy = types.SimpleNamespace(
        EObjectType_Light=4,
        EObjectType_SpotLight=5,
        EObjectType_PointLight=6,
        EObjectType_DirectionalLight=7,
        RStatus=types.SimpleNamespace(Success="success"),
        RGlobal=types.SimpleNamespace(GetTime=lambda: 7),
        RScene=types.SimpleNamespace(
            QueryObjectByID=lambda object_id: {
                "100": LIGHT,
                "559": SPOT_LIGHT,
                "560": POINT_LIGHT,
            }.get(str(object_id)),
            FindObjects=lambda unused_type: [],
        ),
        RVector3=lambda x, y, z: types.SimpleNamespace(x=x, y=y, z=z),
    )
    lights._find = lambda unused_name: LIGHT


def test_directional_angle_is_converted_to_radians():
    result = lights.set_light({"name": "Dir. Light", "angle_degrees": 90})

    assert result["angle_degrees"] == 90
    assert LIGHT.angle[0] == 7
    assert abs(LIGHT.angle[1] - 1.5707963267948966) < 1e-9


def test_create_light_rejects_unsupported_type():
    try:
        lights.create_light({"type": "area"})
    except ValueError as error:
        assert "directional" in str(error)
    else:
        raise AssertionError("unsupported light type was accepted")


def test_get_volumetric_light_prefers_object_id():
    result = lights.get_volumetric_light({"object_id": "559"})

    assert result["id"] == "559"
    assert result["type"] == "SpotLight"
    assert result["falloff_power"] == 1
    assert result["eccentricity"] == -0.31


def test_get_volumetric_light_point_omits_falloff_power():
    result = lights.get_volumetric_light({"object_id": "560"})

    assert result["type"] == "PointLight"
    assert "falloff_power" not in result


def test_set_volumetric_light_point_rejects_falloff_power():
    try:
        lights.set_volumetric_light({"object_id": "560", "falloff_power": 2})
    except ValueError as error:
        assert "spot" in str(error).lower()
    else:
        raise AssertionError("point light accepted falloff_power")


def test_set_volumetric_light_batches_key_fields():
    scatter = lights.RLPy.RVector3(0.1, 0.2, 0.3)
    result = lights.set_volumetric_light(
        {
            "object_id": "559",
            "intensity": 3.5,
            "scatter_color": {"r": 0.1, "g": 0.2, "b": 0.3},
            "medium_density_multiplier": 10.0,
        }
    )

    assert len(SPOT_LIGHT.patch_calls) == 1
    assert SPOT_LIGHT.patch_calls[0]["patch_intensity"]
    assert SPOT_LIGHT.patch_calls[0]["patch_scatter"]
    assert SPOT_LIGHT.patch_calls[0]["patch_density"]
    assert result["intensity"] == 3.5
    assert result["medium_density_multiplier"] == 10.0
    assert scatter.x == 0.1


def test_get_light_nests_volumetric_for_spot():
    original_find_light = lights._find_light
    lights._find_light = lambda args: SPOT_LIGHT
    try:
        result = lights.get_light({"object_id": "559"})
    finally:
        lights._find_light = original_find_light

    assert "volumetric" in result
    assert result["volumetric"]["type"] == "SpotLight"
    assert result["volumetric"]["falloff_power"] == 1


def test_get_volumetric_light_requires_rlpy_api():
    class LegacyLight(Light):
        pass

    original_find_light = lights._find_light
    lights._find_light = lambda args: LegacyLight("Legacy", RLPy.EObjectType_SpotLight, "999")
    try:
        try:
            lights.get_volumetric_light({"object_id": "999"})
        except RuntimeError as error:
            assert "Rebuild RLPy" in str(error)
        else:
            raise AssertionError("legacy light was accepted")
    finally:
        lights._find_light = original_find_light


if __name__ == "__main__":
    setup_module()
    for name, value in list(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
            print("passed:", name)
    print("all tests passed")
