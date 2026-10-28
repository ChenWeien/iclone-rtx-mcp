"""Exercise the published material-inspection tool through MCP against a live app.

Run with the ICMCP server's Python environment after starting the matching app.
This uses the SDK's in-process MCP transport, without starting another stdio host.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

SERVER_SOURCE = Path(__file__).resolve().parents[1] / 'server' / 'src'
sys.path.insert(0, str(SERVER_SOURCE))
from mcp import Client
from iclone_mcp import server
from iclone_mcp.connection import ICloneConnection

async def inspect(args):
    original = server.connection
    server.connection = ICloneConnection(port=args.port)
    try:
        async with Client(server.mcp, raise_exceptions=True) as client:
            async def call(name, arguments):
                result = await client.call_tool(name, arguments)
                assert not result.is_error, result.content
                return result.structured_content
            status = await call('get_iclone_status', {})
            assert status['ready'] and status['listener']['port'] == args.port, status
            before = await call('get_scene_info', {'limit': 1})
            args.output_dir.mkdir(parents=True, exist_ok=True)
            for object_id in args.object_id:
                result = await call('get_materials', {'object_id': object_id, 'view': 'render_bindings'})
                assert result['object_id'] == object_id and object_id.isdecimal(), result
                for mesh in result['meshes']:
                    diagnostic = mesh['render_bindings']
                    assert isinstance(diagnostic['supported'], bool), diagnostic
                    if diagnostic['supported']:
                        assert diagnostic['renderer'] == 'rtx' and isinstance(diagnostic['bindings'], list), diagnostic
                        assert isinstance(diagnostic['active_attribute_ranges'], list), diagnostic
                        assert diagnostic['active_index_count'] >= 0, diagnostic
                        indices = [binding['geometry_index'] for binding in diagnostic['bindings']]
                        assert len(indices) == len(set(indices)), indices
                        for binding in diagnostic['bindings']:
                            if not binding.get('geometry_present') or not binding.get('material_present'):
                                continue
                            assert binding['index_offset'] >= 0 and binding['index_count'] >= 0, binding
                            assert binding['material_index'] >= 0 and binding['material_id'].isdecimal(), binding
                path = args.output_dir / (object_id + '.json')
                path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                print(path)
            after = await call('get_scene_info', {'limit': 1})
            for key in ('current_time_ms', 'object_count', 'selected_object_ids'):
                assert before[key] == after[key], (key, before[key], after[key])
            print('PASS: MCP native material inspection; scene time, count and selection unchanged')
    finally:
        await server.connection.close()
        server.connection = original

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=9880)
    parser.add_argument('--object-id', action='append', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('--port must be between 1024 and 65535')
    asyncio.run(inspect(args))
