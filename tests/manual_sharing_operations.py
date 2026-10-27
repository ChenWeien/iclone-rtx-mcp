"""Run the sharing mutation regression in a disposable debug session.

python manual_sharing_operations.py OUTPUT_DIR [--port 9880] [--render]
Creates test objects and saves/reopens a test project. Leaves test objects in place.
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
    root = Path(__file__).resolve().parents[2]
    prefix = "SharingOps_" + output.name + "_"
    names = [prefix + suffix for suffix in ("A", "B", "C", "Outside", "Cone", "Child")]
    report = {}
    server.connection = ICloneConnection(port=port)

    def record(key, value):
        report[key] = value
        (output / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("PASS:", key, flush=True)

    async with Client(server.mcp, raise_exceptions=True) as client:
        async def call(tool, **args):
            result = await client.call_tool(tool, args)
            assert not result.is_error, (tool, result)
            return result.structured_content

        async def identify(targets):
            scene = (await call("get_scene_info"))["objects"]
            ids = []
            for name in targets:
                matches = [obj["id"] for obj in scene if obj["name"] == name]
                assert len(matches) == 1, (name, matches)
                ids.append(matches[0])
            return ids

        async def inspect(targets):
            return await call("get_mesh_sharing", object_ids=await identify(targets))

        async def geometry(tool, targets):
            return await call(tool, object_ids=await identify(targets))

        async def material(source, target, source_index=0, target_index=0):
            source_id, target_id = await identify([source, target])
            return await call("share_material", source_object_id=source_id, source_material_index=source_index,
                              target_object_id=target_id, target_material_index=target_index)

        async def python(source):
            script = output / "host_check.py"
            script.write_text(source, encoding="utf-8")
            return await call("run_python_file", path=str(script), confirm="RUN_PYTHON_FILE")

        async def update(targets):
            ids = await identify(targets)
            await python("import RLPy\nfor i in " + repr(ids) + ":\n"
                         "    obj = RLPy.RScene.QueryObjectByID(i)\n"
                         "    assert obj is not None, i\n    obj.Update()\n")

        async def history(action):
            await asyncio.sleep(0.1)
            await python("import RLPy\nRLPy.RGlobal." + action + "()\n")

        def ids(obj, key):
            return [i for mesh in obj["meshes"] for i in mesh[key] if i is not None]

        def resources(result, key):
            return [ids(obj, key) for obj in result["objects"]]

        def shared(result, key):
            values = resources(result, key)
            assert values and values[0] and all(value == values[0] for value in values), result

        def unique(result, key):
            values = [set(value) for value in resources(result, key)]
            assert all(values), result
            assert all(a.isdisjoint(b) for i, a in enumerate(values) for b in values[i + 1:]), result

        status = await call("get_iclone_status")
        assert status["ready"], status
        application = status["application"]
        scene = await call("get_scene_info")
        assert not any(obj["name"].startswith(prefix) for obj in scene["objects"]), "Test prefix already exists"
        for name, x in zip(names[:4], (-60, 60, 180, 300)):
            await call("create_primitive", type="box", name=name, position={"x": x, "y": 0, "z": 50})
        await call("create_primitive", type="cone", name=names[4])
        await call("create_primitive", type="box", name=names[5])
        for name in names[2:]:
            await call("set_object_state", name=name, visible=False)

        outside = await inspect([names[3]])
        baseline = await inspect(names[:3])
        shared(baseline, "geometry_data_ids")
        unique(baseline, "material_ids")
        result = await geometry("make_mesh_geometry_unique", names[:3])
        unique(result["sharing"], "geometry_data_ids")
        assert resources(result["sharing"], "material_ids") == resources(baseline, "material_ids")
        assert await inspect([names[3]]) == outside
        result = await geometry("make_mesh_geometry_unique", names[:3])
        assert not result["changed_object_ids"], result
        record("make_geometry_unique", result)

        result = await geometry("share_mesh_geometry", names[:3])
        shared(result["sharing"], "geometry_data_ids")
        assert resources(result["sharing"], "material_ids") == resources(baseline, "material_ids")
        assert await inspect([names[3]]) == outside
        result = await geometry("share_mesh_geometry", names[:3])
        assert not result["changed_object_ids"], result
        record("share_geometry_and_no_op", result)

        before = await inspect([names[0], names[4]])
        result = await geometry("share_mesh_geometry", [names[0], names[4]])
        assert not result["changed_object_ids"], result
        assert result["sharing"] == before
        assert all(obj["reason"] == "no_matching_geometry" for obj in result["skipped_objects"]), result
        record("mismatched_geometry", result)

        await geometry("make_mesh_geometry_unique", [names[0]])
        unique(await inspect(names[:2]), "geometry_data_ids")
        await history("Undo")
        shared(await inspect(names[:2]), "geometry_data_ids")
        await history("Redo")
        unique(await inspect(names[:2]), "geometry_data_ids")
        await geometry("share_mesh_geometry", names[:3])
        record("geometry_undo_redo", await inspect(names[:3]))

        before = await inspect(names[:3])
        result = await material(names[0], names[1])
        assert result["changed"], result
        shared(result["sharing"], "material_ids")
        assert resources(await inspect(names[:3]), "geometry_data_ids") == resources(before, "geometry_data_ids")
        assert (await inspect([names[2]]))["objects"][0] == before["objects"][2]
        assert not (await material(names[0], names[1]))["changed"]
        await history("Undo")
        unique(await inspect(names[:2]), "material_ids")
        await history("Redo")
        shared(await inspect(names[:2]), "material_ids")
        record("material_share_no_op_undo_redo", await inspect(names[:3]))

        for frame, color in ((1, {"r": 0, "g": 1, "b": 1}), (30, {"r": 1, "g": 0, "b": 0})):
            await call("set_timeline", frame=frame)
            await call("set_material_property", name=names[0], color=color)
            await update(names[:2])
            for name in names[:2]:
                actual = (await call("get_materials", name=name))["materials"][0]["diffuse"]
                assert all(abs(actual[key] - color[key]) < 1e-5 for key in color), (name, frame, actual)
        before = await inspect(names[:2])
        await call("make_material_unique", name=names[1], material_index=0)
        unique(await inspect(names[:2]), "material_ids")
        assert resources(await inspect(names[:2]), "geometry_data_ids") == resources(before, "geometry_data_ids")
        original_b = (await call("get_materials", name=names[1]))["materials"][0]["diffuse"]
        await call("set_material_property", name=names[0], color={"r": 0, "g": 1, "b": 1})
        await update(names[:2])
        assert (await call("get_materials", name=names[1]))["materials"][0]["diffuse"] == original_b
        record("shared_animation_and_material_unique", await inspect(names[:2]))

        parent_id, child_id = await identify([names[0], names[5]])
        await python("import RLPy\np = RLPy.RScene.QueryObjectByID(" + repr(parent_id) + ")\n"
                     "c = RLPy.RScene.QueryObjectByID(" + repr(child_id) + ")\n"
                     "assert p is not None and c is not None\nassert c.SetParent(p) == RLPy.RStatus.Success\n")
        child = await inspect([names[5]])
        await geometry("make_mesh_geometry_unique", [names[0]])
        assert await inspect([names[5]]) == child
        await geometry("share_mesh_geometry", names[:3])
        assert await inspect([names[5]]) == child
        record("unselected_attachment", child)

        source_id, target_id = await identify(names[:2])
        before = await inspect(names[:3])
        for tool, arguments in (
            ("share_mesh_geometry", {"object_ids": [source_id, "missing-scene-object"]}),
            ("share_material", {"source_object_id": source_id, "source_material_index": 0,
                                "target_object_id": target_id, "target_material_index": 999999}),
        ):
            result = await client.call_tool(tool, arguments)
            assert result.is_error, (tool, result)
        assert await inspect(names[:3]) == before
        record("invalid_input_preserves_scene", before)

        # A real multi-material fixture exercises container copying without touching face IDs.
        asset = root.parent / "RLOpenSDK/RLPy/PythonAPITest/ICFileSet/BuildingGen/W_Window_01a.iProp"
        multi_names = [prefix + "Multi_A", prefix + "Multi_B"]
        for name in multi_names:
            await call("import_asset", path=str(asset), name=name)
        multi = await inspect(multi_names)
        assert any(len(mesh["material_ids"]) > 1 for mesh in multi["objects"][1]["meshes"]), multi
        old_target = ids(multi["objects"][1], "material_ids")
        old_source = ids(multi["objects"][0], "material_ids")
        result = await material(*multi_names, source_index=0, target_index=1)
        after = result["sharing"]
        assert resources(after, "geometry_data_ids") == resources(multi, "geometry_data_ids")
        assert ids(after["objects"][0], "material_ids") == old_source
        assert set(ids(after["objects"][1], "material_ids")) == (set(old_target) - {old_target[1]}) | {old_source[0]}, result
        record("multi_material_slot_assignment", {"before": multi, "after": after})
        for name in multi_names:
            await call("set_object_state", name=name, visible=False)

        await geometry("share_mesh_geometry", names[:3])
        await material(names[0], names[2])
        project = output / ("sharing.ccProject" if "creator" in application.lower() else "sharing.iProject")
        await call("save_project", path=str(project))
        assert project.is_file()
        await call("load_project", path=str(project))
        reloaded = await inspect(names[:3])
        shared(reloaded, "geometry_data_ids")
        shared(await inspect([names[0], names[2]]), "material_ids")
        unique(await inspect(names[:2]), "material_ids")
        record("save_reopen", reloaded)

        if render:
            for system in ("dx11", "dx12"):
                await call("render_system", action="set", system=system)
                await server.connection.close()
                await asyncio.sleep(3)
                await call("set_render_settings", width=320, height=180, export_type="image", sample_count=8, mode="final")
                image = output / (system + ".png")
                await call("render_image", output_path=str(image), confirm="RENDER_IMAGE_WITH_CURRENT_SETTINGS")
                assert image.is_file() and image.stat().st_size > 100, image
                shared(await inspect(names[:3]), "geometry_data_ids")
                shared(await inspect([names[0], names[2]]), "material_ids")
                unique(await inspect(names[:2]), "material_ids")
                record(system, str(image))

        # Dynamic-mesh validation does not need an RTX pipeline for the avatar fixture.
        await call("render_system", action="set", system="dx11")
        await server.connection.close()
        await asyncio.sleep(3)

        avatars = [obj for obj in (await call("get_scene_info"))["objects"] if obj["type"] == "Avatar"]
        if not avatars:
            asset = root / "exe/Program/Assets/Share/IC8FileConvert/NeutralAvatar/RL_CC3_Plus.ccAvatar"
            await call("import_asset", path=str(asset))
            avatars = [obj for obj in (await call("get_scene_info"))["objects"] if obj["type"] == "Avatar"]
        assert len(avatars) == 1, avatars
        avatar_name = avatars[0]["name"]
        dynamic_box = prefix + "DynamicBox"
        await call("create_primitive", type="box", name=dynamic_box)
        avatar_id = (await identify([avatar_name]))[0]
        await python("import RLPy\na = RLPy.RScene.QueryObjectByID(" + repr(avatar_id) + ")\n"
                     "assert a is not None and len(a.GetSkeletonComponent().GetSkinBones()) > 0\n")
        before = await inspect([avatar_name, dynamic_box])
        result = await geometry("share_mesh_geometry", [avatar_name, dynamic_box])
        assert not result["changed_object_ids"], result
        assert any(obj["reason"] == "dynamic_or_unsupported_mesh" for obj in result["skipped_objects"]), result
        assert result["sharing"] == before
        record("dynamic_geometry_rejected", result)
        record("completed", True)
    await server.connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=lambda value: Path(value).resolve())
    parser.add_argument("--port", type=int, default=9880)
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    asyncio.run(check(args.output, args.port, args.render))
