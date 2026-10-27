import asyncio
from unittest.mock import patch

from mcp import Client

from iclone_mcp import server
from iclone_mcp.connection import ICloneBridgeError


class FakeConnection:
    def __init__(self):
        self.calls = []
        self.failure = None

    async def request(self, command_type, params=None):
        self.calls.append((command_type, params))
        if self.failure is not None:
            raise self.failure
        if command_type == "get_status":
            return {"protocol_version": 1, "application": "iClone"}
        return {"command": command_type, "params": params or {}}


def run(coroutine):
    return asyncio.run(coroutine)


BRIDGE_TOOLS = {
    "get_iclone_status",
    "get_scene_info",
    "get_object_info",
    "select_objects",
    "set_transform",
    "import_asset",
    "delete_objects",
    "undo",
    "redo",
}


def test_tools_are_discoverable_and_structured():
    async def scenario():
        fake = FakeConnection()
        original = server.connection
        server.connection = fake
        try:
            async with Client(server.mcp, raise_exceptions=True) as client:
                listed = await client.list_tools()
                tools = {tool.name: tool for tool in listed.tools}
                catalog_names = {
                    name
                    for name, metadata in server.UPSTREAM_TOOL_CATALOG.items()
                    if metadata.get("advertise", True)
                    and name not in {"import_asset", "set_transform"}
                }
                assert set(tools) == catalog_names | BRIDGE_TOOLS
                assert 70 <= len(tools) <= 90
                assert "material_texture" in tools
                assert "render_job" in tools
                assert "remove_material_texture" not in tools
                assert "set_material_glow_map" not in tools
                assert "render_video" not in tools

                assert tools["get_scene_info"].annotations.read_only_hint is True
                assert tools["delete_objects"].annotations.destructive_hint is True
                assert tools["run_python_file"].annotations.destructive_hint is True
                assert tools["render_job"].annotations.destructive_hint is True
                assert tools["get_materials"].annotations.read_only_hint is True
                assert tools["get_mesh_sharing"].annotations.read_only_hint is True
                assert tools["get_mesh_sharing"].input_schema["required"] == ["object_ids"]
                sharing = await client.call_tool("get_mesh_sharing", {"object_ids": ["123", "456"]})
                assert not sharing.is_error
                assert fake.calls[-1] == ("get_mesh_sharing", {"object_ids": ["123", "456"]})
                for tool_name, arguments in (
                    ("share_mesh_geometry", {"object_ids": ["123", "456"]}),
                    ("make_mesh_geometry_unique", {"object_ids": ["123"]}),
                    ("share_material", {"source_object_id": "123", "source_material_index": 0,
                                        "target_object_id": "456", "target_material_index": 1}),
                ):
                    assert tools[tool_name].annotations.read_only_hint is False
                    mutation = await client.call_tool(tool_name, arguments)
                    assert not mutation.is_error
                    assert fake.calls[-1] == (tool_name, arguments)


                vector_schema = tools["set_transform"].input_schema["properties"][
                    "position_cm"
                ]
                assert "anyOf" in vector_schema
                assert tools["create_primitive"].input_schema["properties"]["type"][
                    "enum"
                ] == ["box", "ball", "cone", "cylinder", "floor", "torus"]
                run_python_schema = tools["run_python_file"].input_schema
                assert run_python_schema["required"] == ["path", "confirm"]
                assert "action" in tools["material_texture"].input_schema["properties"]
                assert "action" in tools["render_job"].input_schema["properties"]
                assert "confirm" in tools["render_image"].input_schema["properties"]
                assert "confirm" in tools["render_image"].input_schema.get("required", [])
                assert tools["load_project"].input_schema["required"] == ["path"]
                assert "lens_flare" in tools["list_objects"].input_schema["properties"]["type"]["enum"]
                assert "get_material_capabilities" in tools
                assert "set_camera_settings" in tools
                assert "detach_camera_focus_target" in tools
                assert "camera_key" in tools
                assert "get_ui" in tools
                assert "invoke_ui" in tools
                assert "index" in tools["pathtracer_debug_view"].input_schema["properties"] or "action" in tools["pathtracer_debug_view"].input_schema["properties"]

                result = await client.call_tool("get_iclone_status", {})
                assert result.is_error is False
                assert result.structured_content == {
                    "protocol_version": 1,
                    "application": "iClone",
                }

                result = await client.call_tool("get_project_info", {})
                assert result.is_error is False
                assert fake.calls[-1] == ("get_project_info", {})

                await client.call_tool(
                    "run_python_file",
                    {"path": "D:\\dev\\script.py", "confirm": "RUN_PYTHON_FILE"},
                )
                assert fake.calls[-1] == (
                    "run_python_file",
                    {"path": "D:\\dev\\script.py", "confirm": "RUN_PYTHON_FILE"},
                )

                await client.call_tool(
                    "render_job",
                    {
                        "action": "start",
                        "confirm": "RENDER_VIDEO_WITH_CURRENT_SETTINGS",
                        "output_path": "D:\\dev\\1.mp4",
                    },
                )
                assert fake.calls[-1][0] == "render_job"
                assert fake.calls[-1][1]["action"] == "start"
        finally:
            server.connection = original

    run(scenario())


def test_catalog_excludes_collapsed_aliases():
    catalog = server.UPSTREAM_TOOL_CATALOG
    for hidden in (
        "remove_material_texture",
        "set_material_glow_map",
        "render_video",
        "get_system_compatibility",
        "set_ui_value",
        "ping_iclone",
        "export_fbx",
        "get_volumetric_light",
    ):
        assert hidden not in catalog
    for advertised in (
        "material_texture",
        "material_shader",
        "render_job",
        "render_system",
        "pathtracer_debug_view",
        "ibl",
        "export_object",
        "get_ui",
        "invoke_ui",
        "control_timeline",
        "transform_key",
        "camera_key",
        "detach_camera_focus_target",
        "content_paths",
    ):
        assert advertised in catalog
        assert catalog[advertised].get("advertise", True) is True


def test_bridge_errors_become_tool_errors():
    async def scenario():
        fake = FakeConnection()
        fake.failure = ICloneBridgeError("iClone is not listening")
        original = server.connection
        server.connection = fake
        try:
            async with Client(server.mcp, raise_exceptions=True) as client:
                result = await client.call_tool("undo", {})
                assert result.is_error is True
                assert "iClone is not listening" in result.content[0].text
        finally:
            server.connection = original

    run(scenario())


def test_capture_window_uses_application_for_custom_port():
    async def scenario():
        class FakeCaptureConnection:
            port = 9882

            async def request(self, command_type, params=None):
                assert command_type == "get_status"
                return {"application": "Character Creator 5"}

        captured = []

        def capture(executable_name):
            captured.append(executable_name)
            return b"png", {}

        with patch.object(server, "connection", FakeCaptureConnection()), patch.object(
            server, "capture_window_png", capture
        ):
            result = await server.capture_window()

        assert captured == ["CharacterCreator.exe"]
        assert result.content[0].mime_type == "image/png"

    run(scenario())
