import os
import sys
import types


PLUGIN_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "plugin")
)
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

fake_rlpy = types.ModuleType("RLPy")
fake_rlpy.RScene = types.SimpleNamespace()
sys.modules["RLPy"] = fake_rlpy

import iclone_mcp_tool_timeline as timeline


def test_set_timeline_milliseconds_uses_tick_conversion():
    class _Time:
        def __init__(self, value=0):
            self.value = value

        def ToInt(self):
            return self.value

    class _Fps:
        def ToFloat(self):
            return 60.0

        def GetFrameIndex(self, time):
            return int(round(time.ToInt() / 100))

    class _RTime:
        def __init__(self):
            pass

        @staticmethod
        def FromValue(value):
            assert isinstance(value, int)
            return _Time(value)

    state = {"time": _Time(0)}
    fake_rlpy.RStatus = types.SimpleNamespace(Success="success")
    fake_rlpy.RTime = _RTime
    fake_rlpy.RTick = types.SimpleNamespace(FromMilliSecond=lambda value: _Time(int(value * 6)))
    fake_rlpy.RGlobal = types.SimpleNamespace(
        GetFps=lambda: _Fps(),
        GetTime=lambda: state["time"],
        GetStartTime=lambda: _Time(0),
        GetEndTime=lambda: _Time(179900),
        IsPlaying=lambda: False,
        SetTime=lambda value: state.update(time=value) or "success",
    )
    original_rlpy = timeline.RLPy
    timeline.RLPy = fake_rlpy
    try:
        result = timeline.set_timeline({"milliseconds": 1667})
        assert state["time"].ToInt() == 10002
        assert result["current_frame"] == 100
    finally:
        timeline.RLPy = original_rlpy
