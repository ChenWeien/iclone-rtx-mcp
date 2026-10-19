import RLPy

from iclone_mcp_tool_objects import _SEARCH_TYPES


def _frame(time, fps):
    return fps.GetFrameIndex(time)


def _time(frame, fps):
    return fps.IndexedFrameTime(frame)


def _fps_value(fps):
    return fps.ToFloat()


def get_timeline(_args):
    fps = RLPy.RGlobal.GetFps()
    current, start, end = RLPy.RGlobal.GetTime(), RLPy.RGlobal.GetStartTime(), RLPy.RGlobal.GetEndTime()
    return {
        "fps": _fps_value(fps),
        "playing": RLPy.RGlobal.IsPlaying(),
        "current_frame": _frame(current, fps),
        "start_frame": _frame(start, fps),
        "end_frame": _frame(end, fps),
    }


def set_timeline(args):
    if "frame" in args:
        target = _time(args["frame"], RLPy.RGlobal.GetFps())
    elif "milliseconds" in args:
        target = RLPy.RTime(args["milliseconds"])
    else:
        raise ValueError("frame or milliseconds is required")
    result = RLPy.RGlobal.SetTime(target)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not change timeline position")
    return get_timeline({})


def play(args):
    fps = RLPy.RGlobal.GetFps()
    start = _time(args.get("start_frame", _frame(RLPy.RGlobal.GetStartTime(), fps)), fps)
    end = _time(args.get("end_frame", _frame(RLPy.RGlobal.GetEndTime(), fps)), fps)
    RLPy.RGlobal.Play(start, end)
    return {"status": "ok"}


def pause(_args):
    RLPy.RGlobal.Pause()
    return get_timeline({})


def stop(_args):
    RLPy.RGlobal.Stop()
    return get_timeline({})


def control_timeline(args):
    action = (args.get("action") or "").lower()
    if action == "play":
        return play(args)
    if action == "pause":
        return pause(args)
    if action == "stop":
        return stop(args)
    raise ValueError("action must be one of: play, pause, stop")


def clear_scene_animations(args):
    if args.get("confirm") != "DELETE_ALL_SCENE_ANIMATIONS":
        raise ValueError("confirm must be DELETE_ALL_SCENE_ANIMATIONS")
    RLPy.RGlobal.Stop()
    objects, seen, failed = [], set(), []
    for object_type in _SEARCH_TYPES:
        for obj in RLPy.RScene.FindObjects(object_type):
            if obj.GetID() in seen:
                continue
            seen.add(obj.GetID())
            if RLPy.RGlobal.RemoveAllAnimations(obj) == RLPy.RStatus.Success:
                objects.append(obj.GetName())
            else:
                failed.append(obj.GetName())
    RLPy.RGlobal.SetTime(RLPy.RGlobal.GetStartTime())
    return {"status": "ok", "cleared_objects": objects, "failed_objects": failed}


def register(registry):
    registry["get_timeline"] = {
        "handler": get_timeline,
        "main_thread": True,
        "read_only": True,
        "description": "Return FPS, play state, and timeline frame bounds.",
        "inputSchema": {"type": "object", "properties": {}},
    }
    registry["set_timeline"] = {
        "handler": set_timeline,
        "main_thread": True,
        "description": "Move the playhead by frame or milliseconds.",
        "inputSchema": {
            "type": "object",
            "properties": {"frame": {"type": "integer"}, "milliseconds": {"type": "integer"}},
        },
    }
    registry["control_timeline"] = {
        "handler": control_timeline,
        "main_thread": True,
        "description": "Play, pause, or stop the timeline.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["play", "pause", "stop"]},
                "start_frame": {"type": "integer"},
                "end_frame": {"type": "integer"},
            },
            "required": ["action"],
        },
    }
    registry["clear_scene_animations"] = {
        "handler": clear_scene_animations,
        "main_thread": True,
        "destructive": True,
        "description": "Remove all supported scene animations. Requires confirm DELETE_ALL_SCENE_ANIMATIONS.",
        "inputSchema": {
            "type": "object",
            "properties": {"confirm": {"type": "string", "enum": ["DELETE_ALL_SCENE_ANIMATIONS"]}},
            "required": ["confirm"],
        },
    }

    _hidden = {"advertise": False, "main_thread": True}
    registry["play_timeline"] = dict(
        _hidden,
        handler=play,
        description="Play the timeline.",
        inputSchema={
            "type": "object",
            "properties": {"start_frame": {"type": "integer"}, "end_frame": {"type": "integer"}},
        },
    )
    registry["pause_timeline"] = dict(
        _hidden,
        handler=pause,
        description="Pause the timeline.",
        inputSchema={"type": "object", "properties": {}},
    )
    registry["stop_timeline"] = dict(
        _hidden,
        handler=stop,
        description="Stop the timeline.",
        inputSchema={"type": "object", "properties": {}},
    )
