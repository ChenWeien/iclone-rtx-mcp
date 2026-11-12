try:
    import RLPy2
except ImportError:
    RLPy2 = None


def dds_texture_cache(args):
    module = getattr(RLPy2, "RPreference", None) if RLPy2 is not None else None
    getter = getattr(module, "GetInterface", None)
    if not callable(getter):
        raise RuntimeError("This iClone build does not expose the RLPy2 RPreference API; rebuild and restart the application")
    interface = getter()
    if interface is None:
        raise RuntimeError("The iClone preference interface is unavailable")

    action = (args.get("action") or "get").lower()
    if action == "get":
        return {"enabled": bool(interface.GetDdsTextureCacheEnabled())}
    if action != "set":
        raise ValueError("action must be get or set")

    enabled = args.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean")
    previous = bool(interface.GetDdsTextureCacheEnabled())
    status = interface.SetDdsTextureCacheEnabled(enabled)
    if status is not None and not status:
        raise RuntimeError("iClone could not update the DDS texture cache preference")
    effective = bool(interface.GetDdsTextureCacheEnabled())
    if effective != enabled:
        raise RuntimeError("iClone did not apply the DDS texture cache preference")
    return {"enabled": effective, "changed": previous != effective}


def texture_loading(args):
    action = args.get("action", "get")
    if action not in ("get", "set", "load"):
        raise ValueError("action must be get, set, or load")
    if action == "set" and not isinstance(args.get("manual"), bool):
        raise ValueError("manual must be a boolean")
    module = getattr(RLPy2, "RPreference", None)
    getter = getattr(module, "GetInterface", None)
    interface = getter() if callable(getter) else None
    if interface is None or not hasattr(interface, "GetManualTextureLoading"):
        raise RuntimeError("Rebuild and restart iClone to use the texture loading API")
    if action == "set":
        status = interface.SetManualTextureLoading(args["manual"])
        if status is not None and not status:
            raise RuntimeError("Could not update texture loading mode")
        if bool(interface.GetManualTextureLoading()) != args["manual"]:
            raise RuntimeError("iClone did not apply texture loading mode")
    elif action == "load":
        status = interface.LoadPendingTextures()
        if status is not None and not status:
            raise RuntimeError("Could not release pending textures")
    return {"manual": bool(interface.GetManualTextureLoading()),
            "pending": bool(interface.HasPendingManualTextures())}


def register(registry):
    registry["dds_texture_cache"] = {
        "handler": dds_texture_cache,
        "main_thread": True,
        "description": "Get or enable/disable iClone's DDS texture cache preference.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["get", "set"]},
                "enabled": {"type": "boolean"},
            },
            "oneOf": [
                {"properties": {"action": {"const": "get"}}, "required": ["action"]},
                {"properties": {"action": {"const": "set"}, "enabled": {"type": "boolean"}}, "required": ["action", "enabled"]},
            ],
            "required": ["action"],
        },
    }

    registry["texture_loading"] = {
        "handler": texture_loading,
        "main_thread": True,
        "description": "Inspect or set manual texture loading, or release the current pending batch.",
        "inputSchema": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["get", "set", "load"]},
            "manual": {"type": "boolean"}}, "required": ["action"]},
    }
