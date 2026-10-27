"""Verify a debug iClone session: python manual_mesh_sharing.py OUTPUT_DIR [--port 9880].

Creates named test props, edits their materials and saves/reopens a test project.
Run in a disposable session. Reports identities through the actual MCP tool.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server" / "src"))
from mcp import Client
from iclone_mcp import server
from iclone_mcp.connection import ICloneConnection


async def check(output, port, render):
    output.mkdir(parents=True, exist_ok=True)
    server.connection = ICloneConnection(port=port)
    report = {}

    def record(key, value):
        report[key] = value
        (output / "mesh_sharing_results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    async with Client(server.mcp, raise_exceptions=True) as client:
        async def call(tool_name, **args):
            result = await client.call_tool(tool_name, args)
            assert not result.is_error, (tool_name, result)
            return result.structured_content

        async def diffuse(name, expected):
            # RLPy key writes require Update() before reading evaluated material values.
            await call("run_python_file", path=str(update_script), confirm="RUN_PYTHON_FILE")
            color = (await call("get_materials", name=name))["materials"][0]["diffuse"]
            assert all(abs(color[k] - expected[k]) < 1e-5 for k in expected), (name, expected, color)
            return color

        async def objects():
            return (await call("get_scene_info"))["objects"]

        async def identify(name):
            matches = [obj for obj in await objects() if obj["name"] == name]
            assert len(matches) == 1, (name, matches)
            return matches[0]["id"]

        async def sharing(*names):
            ids = [await identify(name) for name in names]
            return await call("get_mesh_sharing", object_ids=ids)

        def resource_ids(obj, key):
            return {value for mesh in obj["meshes"] for value in mesh[key] if value is not None}

        def assert_geometry_only(result):
            first, second = result["objects"]
            geometry = resource_ids(first, "geometry_data_ids")
            assert geometry and geometry == resource_ids(second, "geometry_data_ids"), result
            materials = resource_ids(first, "material_ids")
            assert materials and resource_ids(second, "material_ids"), result
            assert materials.isdisjoint(resource_ids(second, "material_ids")), result

        assert (await call("get_iclone_status"))["ready"]
        names = ("SharingCheck_A", "SharingCheck_B", "SharingCheck_Clone")
        assert not {obj["name"] for obj in await objects()} & set(names), "Test names already exist"
        for name, x in zip(names[:2], (-60, 60)):
            await call("create_primitive", type="box", name=name, position={"x": x, "y": 0, "z": 50})
        baseline = await sharing(*names[:2])
        assert_geometry_only(baseline)
        record("loaded_twice", baseline)
        print("PASS: repeated loads share geometry and retain independent materials", flush=True)

        await call("clone_object", name=names[0], new_name=names[2])
        before = await sharing(names[0], names[2])
        await call("make_material_unique", name=names[2], material_index=0)
        after = await sharing(names[0], names[2])
        assert_geometry_only(after)
        for old, new in zip(before["objects"], after["objects"]):
            assert resource_ids(old, "geometry_data_ids") == resource_ids(new, "geometry_data_ids")
        assert resource_ids(before["objects"][1], "material_ids") != resource_ids(after["objects"][1], "material_ids")
        assert resource_ids(before["objects"][0], "material_ids") == resource_ids(after["objects"][0], "material_ids")
        record("make_material_unique", {"before": before, "after": after})
        print("PASS: Make Material Unique replaces the material and preserves geometry sharing", flush=True)

        await call("set_object_state", name=names[2], visible=False)
        update_script = output / "evaluate_test_materials.py"
        target_ids = [await identify(name) for name in names[:2]]
        update_script.write_text(
            "import RLPy\nfor object_id in " + repr(target_ids) + ":\n"
            "    obj = RLPy.RScene.QueryObjectByID(object_id)\n"
            "    assert obj is not None, object_id\n"
            "    obj.Update()\n", encoding="utf-8"
        )
        original_b = await call("get_materials", name=names[1])
        await call("set_material_property", name=names[0], color={"r": 1, "g": 0, "b": 0})
        animated = {}
        for frame in (1, 30):
            await call("set_timeline", frame=frame)
            await call("set_material_property", name=names[0], color={"r": 0, "g": frame / 30, "b": 1})
            assert (await call("get_materials", name=names[1]))["materials"][0]["diffuse"] == original_b["materials"][0]["diffuse"]
            animated[frame] = await diffuse(names[0], {"r": 0, "g": frame / 30, "b": 1})
        assert animated[1] != animated[30], animated
        for frame in (1, 30):
            await call("set_timeline", frame=frame)
            await diffuse(names[0], animated[frame])
            assert (await call("get_materials", name=names[1]))["materials"][0]["diffuse"] == original_b["materials"][0]["diffuse"]
        record("material_edits", animated)
        assert_geometry_only(await sharing(*names[:2]))
        print("PASS: material edits and animation leave the other prop unchanged", flush=True)

        project = output / "geometry_only_sharing.iProject"
        saved = await call("save_project", path=str(project))
        assert saved["status"] == "ok" and project.is_file(), saved
        await call("load_project", path=str(project))
        reloaded = await sharing(*names[:2])
        assert_geometry_only(reloaded)
        record("save_reload", reloaded)
        print("PASS: save/reopen preserves geometry sharing and independent materials", flush=True)

        if render:
            for system in ("dx11", "dx12"):
                await call("render_system", action="set", system=system)
                await server.connection.close()
                await asyncio.sleep(3)
                await call("set_render_settings", width=320, height=180, export_type="image", sample_count=8, mode="final")
                image = output / (system + ".png")
                await call("render_image", output_path=str(image), confirm="RENDER_IMAGE_WITH_CURRENT_SETTINGS")
                assert image.is_file() and image.stat().st_size > 100, image
                assert_geometry_only(await sharing(*names[:2]))
                record(system, str(image))
                print("PASS: " + system + " render with independent materials and shared geometry", flush=True)

        # With --render this also exercises built-in PBR preview slots in DX12.
        room = Path(__file__).resolve().parents[2] / "exe/Program/Assets/ExternalFiles/CreateObjectMenu/Surface/Room.iProp"
        room_names = ("SharingCheck_Room_A", "SharingCheck_Room_B")
        assert not {obj["name"] for obj in await objects()} & set(room_names), "Room test names already exist"
        for name in room_names:
            await call("import_asset", path=str(room), name=name)
        room_resources = await sharing(*room_names)
        assert_geometry_only(room_resources)
        record("builtin_pbr_room_import", room_resources)
        print("PASS: Room imports and its material preview refresh completes", flush=True)

        record("completed", True)
    await server.connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=lambda x: Path(x).resolve())
    parser.add_argument("--port", type=int, default=9880)
    parser.add_argument("--render", action="store_true", help="Also render a small image with DX11 and DX12")
    args = parser.parse_args()
    asyncio.run(check(args.output, args.port, args.render))
