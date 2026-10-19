"""Run with a ready debug iClone and MiniViewport open: python this_file.py.
Uses the same local bridge as iClone MCP; fails if switching crashes or loses the widget.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server" / "src"))
from iclone_mcp.connection import ICloneConnection


async def check():
    connection = ICloneConnection()
    try:
        assert (await connection.request("get_status"))["ready"]
        before = await connection.request("get_ui", {"scope": "widgets", "contains": "MiniRenderWnd"})
        assert any(w["visible"] for w in before["widgets"]), "Open MiniViewport before running this check"
        for system in ("dx12", "dx11", "dx12", "dx11"):
            result = await connection.request("render_system", {"action": "set", "system": system})
            assert result["render_system"] == system, result
            await connection.close()
            await asyncio.sleep(2)
            after = await connection.request("get_ui", {"scope": "widgets", "contains": "MiniRenderWnd"})
            assert len(after["widgets"]) == len(before["widgets"]), after
            assert any(w["visible"] for w in after["widgets"]), after
            await connection.request("get_scene_info", {"limit": 1})
            print(system, "responsive; MiniViewport retained", flush=True)
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(check())
