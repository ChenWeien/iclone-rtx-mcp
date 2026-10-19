"""Run with debug iClone: python this_file.py baseline.iProject --pid <iClonePID>.

Uses port 9882 by default. Reloads the supplied project between cases and
leaves its sky deleted. Use a test project with a sky and ordinary props.
"""
import argparse
import asyncio
import ctypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server" / "src"))
from iclone_mcp.connection import ICloneConnection


async def check(project, port, pid):
    connection = ICloneConnection(port=port)

    def assert_no_dialog():
        failures = []
        user32 = ctypes.windll.user32
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        @callback_type
        def inspect(window, unused):
            process = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(ctypes.c_void_p(window), ctypes.byref(process))
            if process.value == pid:
                text = ctypes.create_unicode_buffer(4096)
                user32.GetWindowTextW(ctypes.c_void_p(window), text, len(text))
                if "Assertion failed!" in text.value:
                    failures.append(text.value)
            return True

        @callback_type
        def inspect_children(window, unused):
            inspect(window, unused)
            user32.EnumChildWindows(ctypes.c_void_p(window), inspect, None)
            return True

        user32.EnumWindows(inspect_children, None)
        assert not failures, failures

    async def scene():
        # Allow subsequent viewport/material updates to expose stale sources.
        for frame in (1, 2, 3):
            await connection.request("set_timeline", {"frame": frame})
            await asyncio.sleep(1)
            assert_no_dialog()
        return (await connection.request("get_scene_info"))["objects"]

    def signature(objects):
        return sorted((obj["name"], obj["type"]) for obj in objects)

    try:
        assert (await connection.request("get_status"))["ready"]
        for types in ({"Sky"}, {"Prop"}, {"Prop", "Sky"}):
            print("CHECK:", sorted(types), flush=True)
            await connection.request("load_project", {"path": str(project)})
            assert (await connection.request("get_render_settings"))["render_system"] == "dx12"
            before = await scene()
            assert any(obj["type"] == "Sky" for obj in before), "Project needs sky geometry"
            assert any(obj["type"] == "Prop" for obj in before), "Project needs ordinary props"
            deleted = [obj for obj in before if obj["type"] in types]
            ids = [obj["id"] for obj in deleted]
            await connection.request("delete_objects", {"object_ids": ids})
            after = await scene()
            assert not set(ids) & {obj["id"] for obj in after}, after
            survivors = [obj for obj in before if obj["type"] not in types]
            assert signature(after) == signature(survivors), after
            for _ in range(2):
                await connection.request("undo")
                assert signature(await scene()) == signature(before), "Undo did not restore scene"
                await connection.request("redo")
                assert signature(await scene()) == signature(survivors), "Redo did not remove objects"
            print("PASS delete/undo/redo:", sorted(types), flush=True)

        await connection.request("create_primitive", {"type": "box", "name": "After sky deletion"})
        assert any(obj["name"] == "After sky deletion" for obj in await scene())
        print("PASS add mesh after removing all props and sky", flush=True)
        await connection.request("load_project", {"path": str(project)})
        restored = await scene()
        assert signature(restored) == signature(before), "Reload did not restore sky"
        await connection.request("delete_objects", {
            "object_ids": [obj["id"] for obj in restored if obj["type"] == "Sky"]
        })
        assert not any(obj["type"] == "Sky" for obj in await scene())
        print("PASS reload sky and delete again", flush=True)
    finally:
        await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=lambda value: Path(value).resolve())
    parser.add_argument("--port", type=int, default=9882)
    parser.add_argument("--pid", type=int, required=True, help="PID of the iClone under test")
    args = parser.parse_args()
    assert args.project.is_file(), args.project
    asyncio.run(check(args.project, args.port, args.pid))
