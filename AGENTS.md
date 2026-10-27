# iClone and Character Creator MCP client setup

The host plugin runs inside iClone or Character Creator. Codex or Cursor launches the external
Python 3.12 stdio server with `uv`; do not launch that server manually.

## Before connecting

1. Build the application so the post-build step copies `plugin/` into
   `OpenPlugin/ICMCP` for iClone and Character Creator.
2. Start the application and confirm **Enable Listener** is checked under
   **Plugins > iClone MCP** or **Plugins > Character Creator MCP**.
3. Wait 90 seconds, then require `get_iclone_status()` to return
   `"ready": true` before using scene tools.

The iClone listener uses `127.0.0.1:9880` and the Character Creator listener
uses `127.0.0.1:9881` by default. If either port is changed in the application,
set `ICLONE_MCP_PORT` to the same value in that application's client
configuration.

## Codex

Add this to `%USERPROFILE%\.codex\config.toml`:

```toml
[mcp_servers.iclone]
command = 'C:\Users\weienchen\.local\bin\uv.exe'
args = ["run", "iclone-mcp"]
cwd = 'D:\dev\Easter2023\iCloneR2\ICMCP\server'
startup_timeout_sec = 20
tool_timeout_sec = 200
enabled = true

[mcp_servers.iclone.env]
ICLONE_MCP_PORT = "9880"

[mcp_servers.cc]
command = 'C:\Users\weienchen\.local\bin\uv.exe'
args = ["run", "iclone-mcp"]
cwd = 'D:\dev\Easter2023\iCloneR2\ICMCP\server'
startup_timeout_sec = 20
tool_timeout_sec = 200
enabled = true

[mcp_servers.cc.env]
ICLONE_MCP_PORT = "9881"
```

Restart Codex, use `/mcp` to verify that `iclone` is connected, then ask:

```text
Use the iClone MCP to call get_iclone_status.
```

Codex CLI, the Codex IDE extension, and the Codex desktop app share this
configuration.

## Cursor

Add this to the project `.cursor/mcp.json`, or to
`%USERPROFILE%\.cursor\mcp.json` for global use:

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
      ],
      "env": {
        "ICLONE_MCP_PORT": "9880"
      }
    }
  }
}
```

Restart Cursor, open **Settings > Tools & MCP**, and verify that `iclone` and
its tools are enabled.

## Runtime notes

- Create or refresh the external environment from `ICMCP/server` with
  `uv sync --python C:\dev\Python312\python.exe`.
- The MCP catalog advertises about **80** resource tools (not one tool per
  RLPy verb). Plugin handlers may still accept older command names for
  bridge compatibility; those aliases are **not** listed to MCP clients.
- `render_image` renders an image with iClone's current output settings.
  For video or image-sequence jobs use `render_job` with the matching
  confirm token.
- `delete_objects` uses iClone's `RLPy2.Edit.DeleteSceneObjects` API with
  undo recording enabled; do not switch it back to `RScene.RemoveObject()`.
- `get_iclone_status(include=[...])` can attach optional sections:
  `application`, `api`, `license`, `system`, `runtime`, `network`, `mocap`,
  `ping`. Keep the default call lightweight.

## Tool catalog convention

When adding a capability:

1. Prefer a new **parameter** / `action` on an existing resource tool
   (`material_texture`, `render_job`, `camera_key`, `export_object`, …).
2. Only add a new advertised tool name when it is a new resource or a
   first-class session verb (`list_objects`, `set_transform`, `undo`, …).
3. Keep the old handler registered with `advertise: False` so plugin
   `dispatch` still works during transition.
4. Update `server/src/iclone_mcp/upstream_catalog.py` to match advertised
   plugin tools (`description`, `inputSchema`, optional `read_only` /
   `destructive`). Catalog and advertised plugin names must stay in sync.

## Material and environment coverage

- `get_materials` reports the optional `RIMaterialComponent` PBR/RTX,
  transmission, hair, reflection, two-sided, shader, texture-weight,
  tessellation, Glow Color mode, and Glow Color values when the running iClone
  build exposes them.
- `set_material_property` is the property bag for scalars, vectors, domain,
  glow mode/color (`property=glow_color`), tessellation attributes, and
  slider enablement shortcuts.
- `material_texture` with `action=load|remove|load_video|set_weight|set_uv|remove_uv`
  covers texture channels; use `channel="glow"` for Glow Map.
- `material_shader` with `action=get|list|set|convert|get_parameters|set_parameter|list_textures`
  covers shader selection and declared parameters.
- `set_metal_mirror_material` enables the metalness and roughness sliders, then
  sets metalness to `1` and roughness to `0`.
- IBL is exposed as `ibl` with `action=get|set` through
  `RLPy.RGlobal.GetVisualSettingComponent()`. Procedural-sky enablement is
  present only in internal C++ interfaces, not in the public `RLPy` wrapper.

## Geometry sharing verification

- `get_mesh_sharing(object_ids=[...])` reports per-mesh geometry-data and material
  identities through the read-only `RLPy2.IMesh.GetResourceIds` API.
- Equal non-null resource IDs mean shared storage. IDs last only for the resource
  lifetime; never persist them or use them as scene object IDs.
- `LoadPropsDone` shares matching static geometry with `bInstanceMaterial=false`.
  Materials already shared inside a saved asset remain shared until made unique.
- Use `tests/manual_mesh_sharing.py OUTPUT_DIR --port 9880` in a disposable
  debug session for repeated-load, Make Material Unique, material-edit, and
  save/reopen checks. It creates test props and saves/reopens a test project.

- Add `--render` to check DX11/DX12 output and then import Room in DX12.
  This covers generic PBR materials without custom shader texture data; missing
  shader texture slots must return `RL_ILLEGAL_DATA` without asserting.

- Mutations: `share_mesh_geometry`, `make_mesh_geometry_unique`, and `share_material`
  use validated scene object IDs and native undoable edit commands. Geometry sharing
  preserves materials and is limited to matching static geometry within the selected
  objects. Material sharing assigns one target slot without merging slots or changing
  geometry. Material indices follow the current `get_materials` list.
- Inspect `changed_object_ids` / `skipped_objects` (geometry) or `changed` (material),
  then compare `sharing` readback. Do not infer a mutation from a successful return alone.
