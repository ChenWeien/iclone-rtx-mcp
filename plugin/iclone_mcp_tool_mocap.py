import RLPy


def get_mocap_status(_args):
    """Read the state of iClone's own motion-capture manager without changing it."""
    manager = RLPy.RGlobal.GetMocapManager()
    if manager is None:
        return {"available": False, "running": False}
    return {"available": True, "running": bool(manager.IsRunning())}


def get_network_capabilities(_args):
    """Report native iClone 8 TCP/UDP client availability for diagnostics."""
    return {
        "tcp_client": hasattr(RLPy, "RTcpClient"),
        "udp_client": hasattr(RLPy, "RUdpClient"),
        "note": "The MCP server itself already provides local loopback NDJSON control. Native TCP/UDP device bridges need a device-specific protocol and are intentionally not auto-connected.",
    }


def register(registry):
    _hidden = {"advertise": False, "main_thread": True}
    registry["get_mocap_status"] = dict(
        _hidden,
        handler=get_mocap_status,
        read_only=True,
        description="Check whether iClone mocap manager is available and running.",
        inputSchema={"type": "object", "properties": {}},
    )
    registry["get_network_capabilities"] = dict(
        _hidden,
        handler=get_network_capabilities,
        read_only=True,
        description="Report native TCP/UDP client availability without connecting.",
        inputSchema={"type": "object", "properties": {}},
    )
