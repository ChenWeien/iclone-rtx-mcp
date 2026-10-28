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

## Project loading and RTX dialogs

- Use `load_project(action="start", path=ABSOLUTE_PATH)` and
  `render_system(action="start", system="dx12")` for interactive automation.
  Both return a `job_id` before the native operation can open a modal dialog.
- Poll the same tool with `action="get", job_id=...`. A visible dialog produces
  `state="waiting_for_dialog"` and `dialogs` containing its stable IDs, text,
  checkbox states and button actions. Native work remains on the Qt main thread;
  polling is responsive while the modal Qt event loop is running.
- Inspect with `get_ui(scope="dialogs")`, then use
  `invoke_ui(action="invoke_dialog", dialog_id=..., action_id=...)` for the
  desired choice. Use the returned IDs rather than coordinates or localized text.
- RTX switch IDs: `qtRtxScenePreparationDialog` with
  `qtRtxScenePreparationOkButton` / `qtRtxScenePreparationCancelButton`.
  RTX project-load IDs: `qtRtxProjectLoadPreparationDialog` with
  `qtRtxProjectLoadPreparationOkButton` / `qtRtxProjectLoadPreparationCancelButton`.
- Re-query the dialog list and poll the job to a terminal state after invoking
  a button. Closing a dialog alone does not prove that loading/switching finished.
  For switching, `completed` also requires the requested renderer to be active.
- Job `cancel` only stops queued work (`cancellable=true`). Once native work has
  started, handle its dialog using `invoke_ui`. The native RTX project-load
  Cancel button skips preparation and continues loading; the RTX switch Cancel
  button leaves the renderer unchanged.
- Omitted `load_project.action` retains the synchronous legacy behavior; `path`
  is needed for `load`/`start`, and `job_id` for `get`/`cancel`. Synchronous loading
  and `render_system(action="set")` hold the connection lock until they return,
  preventing dialog-control requests on that connection in the meantime.
- A load and a renderer transition cannot run concurrently. Avoid other scene
  mutations until the job finishes. Use asynchronous job polling only while the
  AP is processing Qt events; it cannot interrupt native computation that does
  not pump events.
- To exercise dialogs even after launching with `-SilentMode` or
  `SkipSwitchRenderDialog`, set `ICLONE_MCP_SHOW_RTX_DIALOGS=1` before launch.
- The external MCP client must refresh its tool catalog after updating this
  `load_project` schema. Restart the AP to load updated plugin modules.

Regression: run server tests and `tests/test_project.py`, `test_diagnostics.py`,
`test_render.py`. Run `tests/test_project_dialogs.py` and `test_listener.py`
**separately** with real PySide2 and `QT_QPA_PLATFORM=offscreen`; the other plugin
unit tests replace Qt with stubs. These tests exercise a real modal loop and the
same TCP connection without changing an AP scene.

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

## Native render-material diagnostics

Use `get_materials(object_id="<stable scene ID>", view="render_bindings")` to inspect
live renderer bindings without running the broad legacy property scan. It is read-only:
it does not change material validity, load pixels, bake textures, render or rebuild geometry.
The response lists meshes directly owned by that object. Inspect child object IDs separately.

- `source_materials`: exact native slots, names, runtime/unique IDs and diffuse/opacity image identities.
- `attribute_ranges`: source geometry attribute IDs and face ranges.
- `bindings`: the material actually selected by each RTX instance/geometry, its material-buffer
  index, source identity, base color, shader, and base-color GPU texture/descriptor state.
- `imported=false` means that native mesh has no live RTX instance. An unsupported renderer
  returns `supported=false`; neither state is evidence that a binding is correct.
- Resource identities last only for the resource lifetime. Resolve scene IDs again after loading.
  Texture cache load states are 0 NotStarted, 1 Loading, 2 ReadyForFinalize, 3 Finalized,
  4 Failed and 5 Discarded. Image async status is the native CImage enum and does not force a load.
- The Python API is `RLPy2.IMesh.GetObject(mesh_handle).GetRenderMaterialDiagnostics()`.
  Resolve mesh handles through `RLPy2.Query.GetInterface().GetObjectMeshes(...)`.
- For an individual legacy property slot, use `get_materials(object_id="...", material_index=2)`.
  The index remains the original flattened `get_materials` index used by material-edit tools.
  `material_index` applies to the properties view, not native geometry slots.

After adding this capability, rebuild Debug iClone, deploy `plugin/` to both products and
restart the tested application. Refresh only the MCP host serving that application's port.
A missing native method reports that a rebuild/restart is required.

`tests/manual_material_bindings.py --port 9884 --object-id <ID> --output-dir <folder>`
uses the published tool through the MCP SDK's in-process client and the real application
bridge. Run it with the ICMCP server's Python environment. It saves the native results and
checks that scene time, object count and selection remain unchanged. It does not launch an
extra stdio host or change the application's renderer.

`capture_window` targets the process ID supplied by its connected listener, excluding other
running builds. Its metadata includes `application_pid`, `application_path` and `hwnd`;
verify these before accepting visual evidence. Old plugins without `application_pid` fail
explicitly instead of selecting another application's window. Deploy/reload the updated
plugin status provider and refresh the server together; the tool needs no PID argument.
