"""Validate mutation targets before native handle conversion and verify tool wiring."""
import importlib
import types

import pytest

from test_mesh_sharing import host


@pytest.fixture
def mutations(host, monkeypatch):
    commands = importlib.import_module("iclone_mcp_commands")
    host.calls = []
    host.resources = {i: host.IMesh.GetObject(i).GetResourceIds() for i in (1, 2, 3)}
    class NativeHandles(list):
        def Add(self, handle):
            self.append(handle)
            return True
    host.RArrayListHandle = NativeHandles
    for i in (1, 2, 3):
        obj = commands._require_object(str(i))
        obj.GetMeshNames = lambda: ["Mesh"]
        obj.GetMaterialComponent = lambda: types.SimpleNamespace(GetMaterialNames=lambda mesh: ["First", "Second"])

    def share(handles):
        assert type(handles) is NativeHandles
        host.calls.append(("share", handles))
        return ["changed", "already_shared"]

    def unique(handles):
        assert type(handles) is NativeHandles
        host.calls.append(("unique", handles))
        for handle in handles:
            host.resources[handle]["geometry_data_ids"] = [str(1000 + handle)]
        return ["changed"] * len(handles)

    def material(*args):
        host.calls.append(("material", args))
        host.resources[args[2]]["material_ids"][args[3]] = host.resources[args[0]]["material_ids"][args[1]]
        return True

    host.edit = types.SimpleNamespace(ShareMeshGeometry=share, MakeMeshGeometryUnique=unique, ShareMaterial=material)
    host.Edit = types.SimpleNamespace(GetInterface=lambda: host.edit)
    host.material_tool = importlib.import_module("iclone_mcp_tool_materials")
    return host


def test_geometry_forwarding_and_changed_report(mutations):
    result = mutations.tool.share_mesh_geometry({"object_ids": ["1", "2", "1"]})
    assert mutations.calls == [("share", [1, 2])]
    assert result["changed_object_ids"] == ["1"]
    assert result["skipped_objects"] == [{"object_id": "2", "reason": "already_shared"}]
    assert result["sharing"]["identity_scope"] == "resource_lifetime"


def test_unique_readback_preserves_materials(mutations):
    before = list(mutations.resources[1]["material_ids"])
    result = mutations.tool.make_mesh_geometry_unique({"object_ids": ["1", "1"]})
    assert mutations.calls == [("unique", [1])]
    mesh = result["sharing"]["objects"][0]["meshes"][0]
    assert mesh["geometry_data_ids"] == ["1001"]
    assert mesh["material_ids"] == before


@pytest.mark.parametrize("ids", [[], ["1"], ["1", "1"], ["1", "unknown"], [1, "2"], "1", None])
def test_share_validates_all_ids_before_mutation(mutations, ids):
    with pytest.raises((ValueError, RuntimeError)):
        mutations.tool.share_mesh_geometry({"object_ids": ids})
    assert mutations.calls == []


def test_blocked_geometry_reports_reasons(mutations):
    mutations.edit.ShareMeshGeometry = lambda handles: ["dynamic_or_unsupported_mesh", "no_matching_geometry"]
    result = mutations.tool.share_mesh_geometry({"object_ids": ["1", "2"]})
    assert result["changed_object_ids"] == []
    assert [o["reason"] for o in result["skipped_objects"]] == ["dynamic_or_unsupported_mesh", "no_matching_geometry"]


def test_material_uses_ids_and_exact_slots(mutations):
    before_geometry = list(mutations.resources[2]["geometry_data_ids"])
    before_other_material = mutations.resources[2]["material_ids"][0]
    result = mutations.material_tool.share_material({
        "source_object_id": "1", "source_material_index": 0,
        "target_object_id": "2", "target_material_index": 1,
    })
    assert mutations.calls == [("material", (1, 0, 2, 1))]
    assert result["changed"] is True
    assert mutations.resources[2]["material_ids"][1] == mutations.resources[1]["material_ids"][0]
    assert mutations.resources[2]["material_ids"][0] == before_other_material
    assert mutations.resources[2]["geometry_data_ids"] == before_geometry


@pytest.mark.parametrize("index", [-1, 2, True, 0.5, "0", None])
def test_material_rejects_invalid_indices_before_mutation(mutations, index):
    with pytest.raises(ValueError):
        mutations.material_tool.share_material({
            "source_object_id": "1", "source_material_index": 0,
            "target_object_id": "2", "target_material_index": index,
        })
    assert mutations.calls == []


def test_material_rejects_missing_object(mutations):
    with pytest.raises(ValueError):
        mutations.material_tool.share_material({
            "source_object_id": "1", "source_material_index": 0,
            "target_object_id": "unknown", "target_material_index": 0,
        })
    assert mutations.calls == []


def test_material_same_object_uses_current_indices(mutations):
    result = mutations.material_tool.share_material({
        "source_object_id": "1", "source_material_index": 0,
        "target_object_id": "1", "target_material_index": 1,
    })
    assert mutations.calls == [("material", (1, 0, 1, 1))]
    assert len(result["sharing"]["objects"]) == 1


def test_material_rejects_missing_component(mutations):
    commands = importlib.import_module("iclone_mcp_commands")
    commands._require_object("2").GetMaterialComponent = lambda: None
    with pytest.raises(ValueError, match="target object has no material component"):
        mutations.material_tool.share_material({
            "source_object_id": "1", "source_material_index": 0,
            "target_object_id": "2", "target_material_index": 0,
        })
    assert mutations.calls == []


def test_incomplete_geometry_report_is_not_success(mutations):
    mutations.edit.ShareMeshGeometry = lambda handles: []
    with pytest.raises(RuntimeError, match="incomplete operation report"):
        mutations.tool.share_mesh_geometry({"object_ids": ["1", "2"]})


def test_missing_native_mutation_api(mutations):
    del mutations.edit.ShareMeshGeometry
    with pytest.raises(RuntimeError, match="rebuild and restart"):
        mutations.tool.share_mesh_geometry({"object_ids": ["1", "2"]})
    assert mutations.calls == []


def test_mutation_catalog_matches_registration(mutations):
    from iclone_mcp.upstream_catalog import UPSTREAM_TOOL_CATALOG
    registry = {}
    mutations.tool.register(registry)
    mutations.material_tool.register(registry)
    for name in ("share_mesh_geometry", "make_mesh_geometry_unique", "share_material"):
        assert registry[name]["main_thread"] is True
        for field in ("description", "inputSchema"):
            assert registry[name][field] == UPSTREAM_TOOL_CATALOG[name][field]
        assert not registry[name].get("read_only", False)
