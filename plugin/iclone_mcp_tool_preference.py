try:
    import RLPy2
except ImportError:
    RLPy2 = None


def dds_texture_cache(args):
    module = getattr(RLPy2, "Preference", None) if RLPy2 is not None else None
    getter = getattr(module, "GetInterface", None)
    if not callable(getter):
        raise RuntimeError("This iClone build does not expose the RLPy2 Preference API; rebuild and restart the application")
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
