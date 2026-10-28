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

### Project loading and RTX conversion dialogs

For automation with dialogs, use the asynchronous forms:

```python
job = await connection.request("load_project", {"action": "start", "path": project_path})
state = await connection.request("load_project", {"action": "get", "job_id": job["job_id"]})
```

For a renderer change, use `render_system` with `action="start", system="dx12"`,
then poll `render_system` with `action="get", job_id=...`.
When `state` is `waiting_for_dialog`, `dialogs` includes visible dialog IDs,
text, checkbox states, and action IDs. Inspect them with `get_ui(scope="dialogs")`
and choose a button with `invoke_ui(action="invoke_dialog", dialog_id=...,
action_id=...)`. Poll until `completed`, `failed`, or `cancelled` after handling
the dialog. Existing modal dialogs defer the operation until dismissed.

Job `cancel` only stops work before the native call starts; check `cancellable`.
Once native loading/switching begins, respond to the dialog instead. RTX switch
Cancel leaves the current renderer unchanged; RTX project-load Cancel skips
preparation and continues loading, following the application behavior.

The legacy path-only `load_project` call remains synchronous. It and
`render_system(action="set")` hold the MCP connection until completion, so a
following dialog-control request cannot run on the same connection. Use the
asynchronous forms above when dialogs are possible. Polling can run during a
modal Qt event loop; it cannot interrupt native work that does not process events.
Restart the AP plugin and refresh the MCP client's tool catalog after updating.

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

## Mesh sharing inspection

`get_mesh_sharing(object_ids=[...])` is read-only. It reports each object's
meshes, `geometry_data_ids` (one per geometry/LOD data slot), and
`material_ids`. Equal non-null IDs mean the same resource is used, even when
object or material names differ. Different IDs may still have equal contents.
IDs are diagnostic identities valid only while the resources exist; do not
persist them or pass them to object mutation tools. An object without meshes
returns an empty `meshes` array.

After loading the same static prop twice, geometry IDs should match while
material ID sets should be disjoint. `make_material_unique` should change the
selected material identity without changing geometry identities. Dynamic
meshes retain the existing exclusion from automatic geometry sharing.

The Python API uses the same underlying identities:

```python
import RLPy
import RLPy2

obj = RLPy.RScene.QueryObjectByID(object_id)
if obj is None:
    raise ValueError("Object no longer exists")
query = RLPy2.Query.GetInterface()
handle = RLPy2.System.GetInterface().ToHandle(obj.GetID())
for mesh_handle in query.GetObjectMeshes(handle):
    mesh = RLPy2.IMesh.GetObject(mesh_handle)
    print(query.HandleName(mesh_handle), mesh.GetResourceIds())
```

Rebuild and restart the application to load the new Python bindings. Refresh
the MCP client tool catalog to discover the new tool. This inspection does not
make previously shared saved materials unique.

## Change geometry and material sharing

- `share_mesh_geometry(object_ids=[...])` shares matching static geometry among
  at least two selected scene objects. All geometry/LOD slots must match; materials
  retain their identities. Skinned, morph-controlled, and active cloth meshes are skipped.
- `make_mesh_geometry_unique(object_ids=[...])` separates the selected objects'
  shared geometry across every geometry/LOD slot. Material instances stay unchanged.
- `share_material(source_object_id=..., source_material_index=...,
  target_object_id=..., target_material_index=...)` assigns the source material
  instance to the chosen target slot. Source settings replace the target's appearance,
  and future material edits affect every user of that instance. Geometry, face
  assignments, and unrelated material slots stay unchanged.

Use the current `get_materials` indices when selecting materials. They describe the
current material list and may change after material assignment. Duplicate object
names are supported because these tools use scene object IDs. Unselected attached
objects are excluded from the geometry operations.

All three operations use native edit commands with undo/redo. Repeated operations
that have nothing to change do not add an undo step. Geometry results include
`changed_object_ids`, `skipped_objects` with reasons, and `sharing` readback. Material
sharing returns `changed` and `sharing` readback. Existing `make_material_unique`
can separate a shared material again.

The corresponding Python APIs are `RLPy2.Edit.GetInterface().ShareMeshGeometry(handles)`,
`MakeMeshGeometryUnique(handles)`, and
`ShareMaterial(source_handle, source_index, target_handle, target_index)`.
Pass geometry handles in an `RLPy2.RArrayListHandle`, adding each validated handle
with `Add`. Geometry calls return one status reason per input handle; material sharing returns
whether the target changed. Resolve scene IDs before converting them with
`RLPy2.System.GetInterface().ToHandle`.
