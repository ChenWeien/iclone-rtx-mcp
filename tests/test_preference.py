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
    preference.RLPy2 = types.SimpleNamespace(Preference=PreferenceModule)
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
