# iClone and Character Creator MCP

This project exposes a running iCloneQt or Character Creator scene to MCP clients without loading the
MCP SDK into the host application's embedded Python runtime.

## Runtime layout

- `../plugin` runs inside iClone's or Character Creator's Python 3.8.8 process and uses only `RLPy`,
  `PySide2`, and the standard library.
- This directory runs the MCP stdio server with Python 3.12 and the official MCP
  Python SDK.
- Both processes communicate with NDJSON over `127.0.0.1`. The default ports are
  `9880` for iClone and `9881` for Character Creator.

The plugin starts automatically. Use **Plugins > iClone MCP** or **Plugins >
Character Creator MCP** to inspect the listener, change its port, stop it, or
restart it.

The listener accepts status checks immediately, but scene tools report that
the host application is still initializing for the first 90 seconds. Wait until
`get_iclone_status()` returns `"ready": true`.

## Setup and run

From this directory:

```powershell
uv sync --python C:\dev\Python312\python.exe
uv run iclone-mcp
```

The second command starts a stdio server and normally should be launched by an
MCP client rather than by an interactive terminal.

Example MCP client configuration for this workspace:

```json
{
  "mcpServers": {
    "iclone": {
      "command": "C:\\Users\\weienchen\\.local\\bin\\uv.exe",
      "args": [
        "--directory",
        "D:\\dev\\Easter2023\\iCloneR2\\ICMCP\\server",
        "run",
        "iclone-mcp"
      ]
    }
  }
}
```

For Character Creator, register a second server using the same command and
working directory but port `9881`:

```json
{
  "mcpServers": {
    "cc": {
      "command": "C:\\Users\\weienchen\\.local\\bin\\uv.exe",
      "args": ["run", "iclone-mcp"],
      "cwd": "D:\\dev\\Easter2023\\iCloneR2\\ICMCP\\server",
      "env": {
        "ICLONE_MCP_PORT": "9881"
      }
    }
  }
}
```

If the plugin port is changed, set the same port for the stdio server:

```json
{
  "env": {
    "ICLONE_MCP_PORT": "9881"
  }
}
```

Use absolute executable and project paths because MCP hosts do not necessarily
inherit an interactive shell's working directory or `PATH`.

## Supported operations

The bridge exposes the original stable-ID bridge tools plus the catalog ported from
[`gorbabor/mc-iclone8-mcp`](https://github.com/gorbabor/mc-iclone8-mcp/tree/165038296181b1c9d587ac5a8eb0da5ab9c94b97/tools).
The catalog covers:

- scene objects, transforms, selection, visibility, linking, alignment, and paths;
- project loading/saving, primitives, import/export, motions, thumbnails, and render settings;
- materials, textures, UVs, lights, cameras, timeline playback, morphs, avatars, facial controls, and mocap diagnostics.
- RTX render-system/debug-view control, single-frame image output, and safe Qt widget inspection/value updates.
- Compatibility snapshots for OS/GPU/driver/VRAM evidence and explicit project loading.

The MCP server advertises about **80** resource-oriented tools. Sibling verbs
are folded into `action` / `include` parameters (for example `material_texture`,
`render_job`, `camera_key`, `export_object`). Older command names may still be
accepted by the plugin bridge but are not listed to MCP clients.

The original object tools continue to use stable `RIObject.GetID()` strings.
Catalog tools use the upstream name-based inputs where appropriate. The
existing `set_transform` accepts either a stable `object_id` with centimeter
vectors or a scene `name` with XYZ objects and an optional frame.

`delete_objects` uses iClone's `RLPy2.Edit`
`DeleteSceneObjects(..., RecordUndo=True)` API so deletions can be undone.
`RScene.RemoveObject()` remains a non-undoable low-level API and is not used by
the MCP plugin.

`render_image` saves an image using iClone's current output settings. Use
`render_job` for video / image-sequence jobs with the matching confirm token.

`import_asset` accepts:

`.iavatar`, `.ccavatar`, `.iacc`, `.ccacc`, `.iprop`, `.imdprop`,
`.iimglayer`, `.ilight`, `.icam`, `.cccam`, `.iparticle`, `.ipkfx`,
`.iLflare`, and `.fbx`.

It intentionally does not expose arbitrary Python execution or remote network
access. Optional RLPy APIs such as experimental GLB/OBJ/Alembic export and
Smart Content enumeration return a structured capability error when the
running iClone build does not provide them. The listener has no authentication
and therefore never binds outside loopback.

The ported upstream source is retained under the Apache-2.0 terms in
`UPSTREAM_MCP_LICENSE.txt`.
