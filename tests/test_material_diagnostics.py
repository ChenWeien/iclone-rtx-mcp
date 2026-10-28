"""Native binding inspection must bypass expensive per-property material queries."""
import importlib
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin'))
sys.modules.setdefault('RLPy', types.ModuleType('RLPy'))
materials = importlib.import_module('iclone_mcp_tool_materials')
commands = importlib.import_module('iclone_mcp_commands')

@pytest.fixture
def native(monkeypatch):
    obj = types.SimpleNamespace(GetID=lambda: 42, GetName=lambda: 'Repeated name',
                                GetMaterialComponent=lambda: pytest.fail('Native view enumerated legacy properties'))
    def require(identifier):
        if identifier != '42':
            raise commands.CommandError('Object not found')
        return obj
    monkeypatch.setattr(commands, '_require_object', require)
    payload = {'supported': True, 'imported': True, 'bindings': [{'material_index': 7}]}
    mesh = types.SimpleNamespace(GetRenderMaterialDiagnostics=lambda: payload)
    host = types.SimpleNamespace(
        Query=types.SimpleNamespace(GetInterface=lambda: types.SimpleNamespace(
            GetObjectMeshes=lambda handle: [handle], HandleName=lambda handle: 'Door')),
        System=types.SimpleNamespace(GetInterface=lambda: types.SimpleNamespace(ToHandle=lambda value: value)),
        IMesh=types.SimpleNamespace(GetObject=lambda handle: mesh))
    monkeypatch.setitem(sys.modules, 'RLPy2', host)
    return host, mesh, payload

def test_native_view_uses_validated_identity_and_no_property_scan(native):
    result = materials.get_materials({'object_id': '42', 'name': 'Wrong name', 'view': 'render_bindings'})
    assert result['object_id'] == '42'
    assert result['meshes'] == [{'name': 'Door', 'render_bindings': native[2]}]

def test_native_view_reports_unsupported_renderer(native):
    native[1].GetRenderMaterialDiagnostics = lambda: {'supported': False, 'reason': 'Unsupported renderer'}
    result = materials.get_materials({'object_id': '42', 'view': 'render_bindings'})
    assert result['meshes'][0]['render_bindings']['supported'] is False

def test_native_view_requires_rebuilt_api(native):
    native[0].IMesh.GetObject = lambda handle: object()
    with pytest.raises(RuntimeError, match='IMesh.GetRenderMaterialDiagnostics'):
        materials.get_materials({'object_id': '42', 'view': 'render_bindings'})

def test_invalid_scene_id_never_reaches_native_lookup(native):
    native[0].System.GetInterface = lambda: pytest.fail('Invalid identity reached handle conversion')
    with pytest.raises(commands.CommandError):
        materials.get_materials({'object_id': 'missing', 'view': 'render_bindings'})

@pytest.mark.parametrize('index', [-1, True, 2, '1'])
def test_property_slot_validation_precedes_getters(monkeypatch, index):
    component = types.SimpleNamespace(GetMaterialNames=lambda mesh: ['first', 'chosen'],
                                      GetDiffuseColor=lambda *args: pytest.fail('Invalid slot reached getter'))
    monkeypatch.setattr(materials, '_find', lambda name: types.SimpleNamespace(
        GetMeshNames=lambda: ['mesh'], GetMaterialComponent=lambda: component))
    with pytest.raises(ValueError, match='Material index'):
        materials.get_materials({'name': 'Door', 'material_index': index})

def test_one_property_slot_keeps_original_index_and_skips_other_getters(monkeypatch):
    calls = []
    color = types.SimpleNamespace(R=lambda: 1., G=lambda: 0., B=lambda: 0.)
    component = types.SimpleNamespace(GetMaterialNames=lambda mesh: ['first', 'chosen'],
                                      GetDiffuseColor=lambda mesh, name: calls.append(name) or color)
    monkeypatch.setattr(materials, '_find', lambda name: types.SimpleNamespace(
        GetName=lambda: 'Door', GetMeshNames=lambda: ['mesh'], GetMaterialComponent=lambda: component))
    result = materials.get_materials({'name': 'Door', 'material_index': 1})
    assert calls == ['chosen']
    assert result['materials'][0]['index'] == 1

def test_material_inspection_catalog_matches_plugin():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server' / 'src'))
    from iclone_mcp.upstream_catalog import UPSTREAM_TOOL_CATALOG
    registry = {}
    materials.register(registry)
    for field in ('description', 'inputSchema', 'read_only'):
        assert registry['get_materials'][field] == UPSTREAM_TOOL_CATALOG['get_materials'][field]
