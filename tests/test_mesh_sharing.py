"""The inspection must expose storage identity, not infer it from mesh contents."""
import importlib
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin"))
sys.modules.setdefault("RLPy", types.ModuleType("RLPy"))
commands = importlib.import_module("iclone_mcp_commands")

@pytest.fixture
def host(monkeypatch):
    objects = {
        key: types.SimpleNamespace(
            GetID=lambda key=key: int(key), GetName=lambda: "Same name", GetType=lambda: 1
        ) for key in ("1", "2", "3")
    }
    monkeypatch.setattr(commands, "RLPy", types.SimpleNamespace(
        EObjectType_Prop=1, RScene=types.SimpleNamespace(QueryObjectByID=objects.get)
    ))
    # Objects 1 and 2 share geometry, but have independent materials.
    # Object 3 has equal geometry contents in different storage and a shared material.
    resources = {
        1: {"geometry_data_ids": ["900", None], "material_ids": ["100", "101"]},
        2: {"geometry_data_ids": ["900", None], "material_ids": ["200", "201"]},
        3: {"geometry_data_ids": ["901"], "material_ids": ["100"]},
    }
    fake = types.SimpleNamespace(
        Query=types.SimpleNamespace(GetInterface=lambda: types.SimpleNamespace(
            GetObjectMeshes=lambda handle: [handle], HandleName=lambda handle: "mesh"
        )),
        System=types.SimpleNamespace(GetInterface=lambda: types.SimpleNamespace(ToHandle=lambda x: x)),
        IMesh=types.SimpleNamespace(GetObject=lambda handle: types.SimpleNamespace(
            GetResourceIds=lambda: resources[handle]
        )),
    )
    monkeypatch.setitem(sys.modules, "RLPy2", fake)
    rlpy = types.ModuleType("RLPy")
    for name in ("Object", "Avatar", "Prop", "Camera", "Light", "Particle"):
        setattr(rlpy, "EObjectType_" + name, 1)
    monkeypatch.setitem(sys.modules, "RLPy", rlpy)
    fake.tool = importlib.import_module("iclone_mcp_tool_scene")
    return fake


def test_shared_geometry_and_independent_materials(host):
    result = host.tool.get_mesh_sharing({"object_ids": ["1", "2", "3", "1"]})
    assert result["identity_scope"] == "resource_lifetime"
    assert [obj["id"] for obj in result["objects"]] == ["1", "2", "3"]
    first, second, third = [obj["meshes"][0] for obj in result["objects"]]
    assert first["geometry_data_ids"] == second["geometry_data_ids"]
    assert set(first["material_ids"]).isdisjoint(second["material_ids"])
    assert third["geometry_data_ids"] != first["geometry_data_ids"]
    assert third["material_ids"][0] == first["material_ids"][0]


@pytest.mark.parametrize("ids", [[], ["unknown"], [1], "1", None])
def test_reject_invalid_ids_before_handle_conversion(host, ids):
    def fail_if_called(value):
        pytest.fail("Invalid scene ID reached handle conversion")
    host.System.GetInterface = lambda: types.SimpleNamespace(ToHandle=fail_if_called)
    with pytest.raises(commands.CommandError):
        host.tool.get_mesh_sharing({"object_ids": ids})


def test_old_build_reports_missing_api(host):
    host.IMesh.GetObject = lambda handle: object()
    with pytest.raises(RuntimeError, match="IMesh.GetResourceIds"):
        host.tool.get_mesh_sharing({"object_ids": ["1"]})


def test_objects_without_meshes(host):
    host.Query.GetInterface = lambda: types.SimpleNamespace(GetObjectMeshes=lambda handle: [])
    assert host.tool.get_mesh_sharing({"object_ids": ["1"]})["objects"][0]["meshes"] == []


def test_catalog_matches_plugin_registration(host):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server" / "src"))
    from iclone_mcp.upstream_catalog import UPSTREAM_TOOL_CATALOG
    registry = {}
    host.tool.register(registry)
    for field in ("description", "inputSchema", "read_only"):
        assert registry["get_mesh_sharing"][field] == UPSTREAM_TOOL_CATALOG["get_mesh_sharing"][field]
