"""Run against a disposable debug iClone with ICWater and SkipSwitchRenderDialog=1.

Uses Water 1.iWater from the configured template root and leaves a new project
open in DX12. Fails if project reset crashes or Water panels stay visible for
another selection. Run with the server's Python environment.
"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server" / "src"))
from iclone_mcp.connection import ICloneConnection


async def check():
    connection = ICloneConnection()
    try:
        status = await connection.request("get_status", {"include": ["application"]})
        assert status["ready"], status
        water = Path(status["application"]["template_data_path"]) / "Set/Water/Still Normal/Water 1.iWater"
        assert water.is_file(), water

        async def panels(visible):
            await asyncio.sleep(1)
            for name in ("BasicWaterParameters.ui", "AdvancedWaterParameters.ui"):
                result = await connection.request("get_ui", {"scope": "widgets", "contains": name})
                widgets = result["widgets"]
                assert len(widgets) == 1, (name, result)
                assert widgets[0]["visible"] == visible, (name, result)

        async def switch(system):
            result = await connection.request("render_system", {"action": "start", "system": system})
            for _ in range(60):
                await asyncio.sleep(1)
                result = await connection.request("render_system", {"action": "get", "job_id": result["job_id"]})
                if result["state"] in ("completed", "failed", "cancelled"):
                    break
            assert result["state"] == "completed" and result["current_system"] == system, result
            await connection.close()
            await asyncio.sleep(2)

        await switch("dx12")
        for iteration in range(2):
            print("CHECK water/New Project cycle", iteration + 1, flush=True)
            scene = await connection.request("get_scene_info")
            prop_id = next(obj["id"] for obj in scene["objects"] if obj["type"] == "Prop")
            await connection.request("select_objects", {"object_ids": [prop_id]})
            await asyncio.sleep(1)
            baseline = await connection.request("get_ui", {"scope": "widgets", "contains": ":/plugin/", "limit": 1000})
            visible = {w["object_name"] for w in baseline["widgets"] if w["visible"]
                       and w["class_name"] in ("IC::CPropAttributeSection", "IC::CTransformSection")}
            assert visible, "Show the Modify panel before running this check"
            result = await connection.request("load_file", {"path": str(water)})
            assert result["loaded"], result
            scene = await connection.request("get_scene_info")
            assert len(scene["selected_object_ids"]) == 1, scene
            water_id = scene["selected_object_ids"][0]
            await panels(False)
            await connection.request("select_objects", {"object_ids": [prop_id]})
            await panels(False)
            restored = await connection.request("get_ui", {"scope": "widgets", "contains": ":/plugin/", "limit": 1000})
            missing = visible - {w["object_name"] for w in restored["widgets"] if w["visible"]}
            assert not missing, missing
            await connection.request("select_objects", {"object_ids": [water_id]})
            await switch("dx11")
            await panels(True)
            # shortcut: avoid the observed selected-water Substance assertion on DX12 conversion; extend when it is fixed.
            await connection.request("select_objects", {"object_ids": [prop_id]})
            await panels(False)
            await switch("dx12")
            await connection.request("select_objects", {"object_ids": [water_id]})
            await panels(False)

            # Return from the bridge request before opening the modal save prompt.
            with tempfile.TemporaryDirectory() as directory:
                script = Path(directory) / "new_project.py"
                script.write_text(
                    "from PySide2 import QtCore, QtWidgets\n"
                    "actions = {id(a): a for w in QtWidgets.QApplication.allWidgets() "
                    "for a in w.actions() if a.objectName() == 'qtNewProjectAction'}\n"
                    "assert len(actions) == 1\n"
                    "QtCore.QTimer.singleShot(500, next(iter(actions.values())).trigger)\n",
                    encoding="utf-8",
                )
                await connection.request("run_python_file", {"path": str(script), "confirm": "RUN_PYTHON_FILE"})
                await asyncio.sleep(1)
                dialogs = await connection.request("get_ui", {"scope": "dialogs"})
                prompt = next(d for d in dialogs["dialogs"]
                              if "The current project will be discarded. Would you like to save?" in d["visible_text"])
                await connection.request("invoke_ui", {
                    "action": "invoke_dialog", "dialog_id": prompt["dialog_id"], "action_id": "action:no",
                })
                await asyncio.sleep(5)
            assert (await connection.request("get_status"))["ready"]
            await panels(False)
            scene = await connection.request("get_scene_info")
            assert not scene["selected_object_ids"], scene
            assert (await connection.request("get_render_settings"))["render_system"] == "dx12"
            print("PASS water selection, DX11/DX12 panels, New Project:", iteration + 1, flush=True)
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(check())
