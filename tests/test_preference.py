import importlib
import os
import sys
import types


PLUGIN_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "plugin")
)
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

preference = importlib.import_module("iclone_mcp_tool_preference")


class PreferenceInterface:
    enabled = True
    allow_write = True

    @classmethod
    def GetDdsTextureCacheEnabled(cls):
        return cls.enabled

    @classmethod
    def SetDdsTextureCacheEnabled(cls, value):
        if not cls.allow_write:
            return False
        cls.enabled = value
        return True


class PreferenceModule:
    @staticmethod
    def GetInterface():
        return PreferenceInterface


def setup_function():
    preference.RLPy2 = types.SimpleNamespace(RPreference=PreferenceModule)
    PreferenceInterface.enabled = True
    PreferenceInterface.allow_write = True


def test_dds_texture_cache_get_and_set_round_trip():
    setup_function()
    assert preference.dds_texture_cache({"action": "get"}) == {"enabled": True}
    assert preference.dds_texture_cache({"action": "set", "enabled": False}) == {
        "enabled": False,
        "changed": True,
    }


def test_dds_texture_cache_validates_input_and_write_result():
    setup_function()
    try:
        preference.dds_texture_cache({"action": "set", "enabled": 1})
    except ValueError:
        pass
    else:
        raise AssertionError("non-boolean preference values must be rejected")

    PreferenceInterface.allow_write = False
    try:
        preference.dds_texture_cache({"action": "set", "enabled": False})
    except RuntimeError:
        pass
    else:
        raise AssertionError("failed preference writes must be reported")


def test_manual_texture_loading_batch_release_and_validation():
    class Interface:
        manual = False
        pending = True
        def GetManualTextureLoading(self): return self.manual
        def HasPendingManualTextures(self): return self.pending
        def SetManualTextureLoading(self, value):
            self.manual = value
            return True
        def LoadPendingTextures(self):
            self.pending = False
            return True
    interface = Interface()
    preference.RLPy2 = types.SimpleNamespace(RPreference=types.SimpleNamespace(GetInterface=lambda: interface))
    assert preference.texture_loading({"action": "set", "manual": True}) == {"manual": True, "pending": True}
    assert preference.texture_loading({"action": "load"}) == {"manual": True, "pending": False}
    for args in ({"action": "set", "manual": 1}, {"action": "invalid"}):
        try:
            preference.texture_loading(args)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid arguments accepted")
