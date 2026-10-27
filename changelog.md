# ICMCP Changelog

Commit summaries for changes that touched `iCloneR2/ICMCP`, newest first.

* `28cfbcd3009` (2026-10-15) — [2] Fix RTX crash when creating a new project after loading water Fix #100717 http://qa-server-2/mantisbt/view.php?id=100717
* `6375791f842` (2026-10-14) — [Easter2023] Fix ICMCP widget lifetime during UI writes
* `1936de54ac6` (2026-10-13) — [Easter2023] [1] Fix RTX Current Frame Preview using Final Render quality settings Fix #100292 http://qa-server-2/mantisbt/view.php?id=100292 [Why] - DoPreviewImage used the export panel's Final selection for RTX previews, selecting Final Render settings.
* `f4ed0a28908` (2026-10-13) — [Easter2023] Fix ICMCP Qt widget discovery crash
* `5484484bae9` (2026-10-08) — [Easter2023] Fix ICMCP socket teardown crash during plugin shutdown
* `04adc289aa8` (2026-10-05) — Revert "[Easter2023] [3] Fix Character Creator renderer switching with custom previews"
* `2030cebecfe` (2026-10-05) — [Easter2023] [3] Fix Character Creator renderer switching with custom previews Fix #100491 http://qa-server-2/mantisbt/view.php?id=100491
* `ad0cc1a4351` (2026-10-02) — [Easter2023] [0] CC may use port 988x
* `e937ba253ac` (2026-10-02) — [Easter2023] [0] handle case where mcp port is > 9881
* `a803c560b1e` (2026-10-02) — [Easter2023] [1] fix mcp capture_window crash: The new `capture_window` implementation uses Windows Graphics Capture from the external MCP server, targeting the app’s HWND. It avoids the old in-process capture path. Microsoft documents HWND-targeted capture in [CreateForWindow](https://learn.microsoft.com/en-us/windows/win32/api/windows.graphics.capture.interop/nf-windows-graphics-capture-interop-igraphicscaptureiteminterop-createforwindow); the Python wrapper supports `window_hwnd` and PNG output in its [README](https://github.com/NiiightmareXD/windows-capture/blob/main/windows-capture-python/README-Python.md). I added the Windows-only `windows-capture` dependency. I captured a **1668×1146** screenshot from the debug iClone window while it was behind Codex The updated code is in [server.py](D:/dev/Easter2023/iCloneR2/ICMCP/server/src/iclone_mcp/server.py) and [window_capture.py](D:/dev/Easter2023/iCloneR2/ICMCP/server/src/iclone_mcp/window_capture.py).
* `85ba3f36022` (2026-10-02) — [Easter2023] [1] Fix iClone MCP object deletion with RLPy2 fix #100529 http://qa-server-2/mantisbt/view.php?id=100529 [Why] - delete_objects imported a missing RLOpen module and passed a Python list where the native API expects RArrayListHandle.
* `9a3dd8b7111` (2026-10-01) — [Easter2023] [2] Recreate MiniViewport views when switching render systems [Why] - MiniViewport retained a render view belonging to the previous backend.
* `da721df67ae` (2026-09-30) — [Easter2023] because `render_image` can't see Gizmo, add `capture_window` using windows API
* `874a36f82fa` (2026-09-30) — [Easter2023] add more *.iXXX file extension
* `339cf1fea8f` (2026-09-23) — [Easter2023] [3] Fix RTX walkway path gizmos and add Mantis 99804 reproduction APIs
* `1165aaf84e7` (2026-09-22) — [Easter2023] [2] Store MCP listener ports in per-instance INI files
* `c772c3012ba` (2026-09-22) — [Easter2023] remove useless waiting time
* `c0097de144e` (2026-09-21) — [Easter2023] [2] Add iClone MCP lens flare preview support
* `7a1cab0351e` (2026-09-21) — [Easter2023] [2] Add camera DoF focus-target detach MCP tool
* `a727396296c` (2026-09-21) — [Easter2023] [2] Add numerical Walkway path setup for Mantis 99807
* `08924d7f3c3` (2026-09-21) — [Easter2023] [2] Collapse ICMCP advertised tools ~189 to ~80
* `8ec681dda7e` (2026-09-21) — [Easter2023] [0] add mcp-tool: remove_material_texture
* `a152aa23d3f` (2026-09-20) — [Easter2023] [2] Retry the iClone MCP listener after AP startup [How] - Keep the immediate listener start - Retry once after 90 seconds when the listener is still stopped
* `46542732c87` (2026-09-16) — [Easter2023] [1] Fix ICMCP menu registration in Debug full loading mode
* `587957d4427` (2026-09-08) — [Easter2023] [0]update mcp tool
* `b6b18852cff` (2026-09-03) — [Easter2023] [2] Add Character Creator MCP listener support
* `e8ef19cd98e` (2026-09-03) — [Easter2023] [1] update mcp-tool
* `01a641498a1` (2026-09-02) — [Easter2023] [0] Tu parles français?
* `b0207236071` (2026-09-02) — [Easter2023] [0] delete `capture_viewport`, this tool has bug. remove until fixed
* `c0947e4d120` (2026-08-31) — [Easter2023] [1] Fix: Render Pass
* `cd627c09413` (2026-08-31) — [Easter2023] [2] Fix .iLflare loading and lens-flare discovery through ICMCP
* `6beba80839a` (2026-08-29) — [Easter2023] [2] Add MCP volumetric light tools and object_id light lookup [How] - Add get_volumetric_light and set_volumetric_light for spot and point lights; reject falloff_power on point lights - Resolve lights by object_id via RScene.QueryObjectByID, with name fallback; nest volumetric data in get_light - Batch keyable volumetric writes through PatchVolumetricLightKey and register new tools in upstream_catalog
* `9f2b74051c7` (2026-08-28) — [Easter2023] [0] mark delete_object, delete_objects callable because record undo is fix in 9404b52dcb2 http://10.10.10.17/iClone/iCloneR2/-/commit/9404b52dcb2
* `b630ce42450` (2026-08-28) — [Easter2023] [2] Add MCP tools for iClone content search and file I/O
* `05e6768273f` (2026-08-28) — [Easter2023] [2] Fix iClone MCP runbook automation and DX12 render export compatibility
* `3e615ac4216` (2026-08-27) — [Easter2023] [1] Add IBL and multi-pass render tests
* `9a7861eb91d` (2026-08-27) — [Easter2023] [2] Add MCP render settings and asynchronous render-job controls
* `5509b3ea6d6` (2026-08-27) — [Easter2023] [2] Add missing iClone MCP camera, material, modal, and RTX APIs [How] - Add asynchronous render-system transitions, modal dialog inspection/actions, licensing state, and the complete RTX debug-view catalog - Extend RICamera, RIMaterialComponent, and RApplication adapters with typed settings, stable-ID lookup, shader/material readback, and regenerated RLPy bindings - Fix generic shader failure handling and immediate diffuse-transmission readback; add focused MCP and adapter tests
* `fdf9b56e07e` (2026-08-27) — [Easter2023] Fix lazy plugin validation and MCP render controls
* `aae339ef189` (2026-08-26) — [Easter2023] [0] Translate upstream MCP catalog descriptions to English
* `e33d44d716a` (2026-08-26) — [Easter2023] [1] iclone-mcp, add get_transform_keys
* `466dfdf841a` (2026-08-26) — [Easter2023] [2] Add Glow Color mode support to iClone material APIs
* `5a32f8d3d89` (2026-08-26) — [Easter2023] [3] Fix buggy image capture by removing capture_viewport MCP tool [Why] - The Qt viewport screen-grab path is buggy - It exposed a competing image workflow instead of the configured render API
* `0a717e6ddd6` (2026-08-26) — [Easter2023] [1] iclone-mcp: add render_multi_pass
* `fadd560b488` (2026-08-26) — [Easter2023] [1] iclone-mcp: add more tool
* `40e90d9454d` (2026-08-25) — [Easter2023] [2] Fix MCP camera Focus Method keyframing [Why] - `set_camera_dof` had no `focus_method` input - MCP could change focus distance and range but not Focus Method between frames
* `6759f7eb69f` (2026-08-25) — [Easter2023] [1] Fix MCP UI writes for all writable Qt properties [Why] - `set_ui_value` rejected custom widgets such as `QComboDoubleSpinBox` - Writable Qt properties were not recognized by the widget-type checks
* `3dd97528f11` (2026-08-24) — [Easter2023] [2] Add compatibility diagnostics and project loading to iClone MCP [How] - Collect read-only OS, GPU, driver, VRAM, and iClone path evidence via nvidia-smi and Windows video-controller APIs - Expose project loading and register both compatibility tools with MCP discovery tests and documentation - Report DXR, RayQuery, and CUDA/OIDN as explicit manual checks when unavailable through public RLPy
* `042c1a15e4f` (2026-08-24) — [Easter2023] [2] Add RTX render controls and Qt UI inspection to iClone MCP [How] - Expose render-system switching, path-tracer debug views, and single-frame image output through existing RLPy APIs - Add safe Qt widget inspection/value updates and update catalog, documentation, and tests
* `ee239611579` (2026-08-24) — [Easter2023] Fix iClone MCP video range rendering
* `6e8ac295245` (2026-08-24) — [Easter2023] [3] Add confirmed Python file execution to the iClone MCP
* `c64a4c9ebcc` (2026-08-24) — [Easter2023] [2] Add .iLflare support to MCP asset imports
* `98dbc7c18fa` (2026-08-24) — [Easter2023] [2] Add output path support to MCP video rendering
* `9404b52dcb2` (2026-08-24) — [Easter2023] [2] Fix MCP object deletion with the undo-aware Edit API
* `0f6113e4911` (2026-07-30) — [Easter2023] [Easter2023][0]  fix iclone-mcp plugin warning
* `4208f74e879` (2026-07-29) — [Easter2023] [Easter2023][1] add mirror material for iclone-mcp
* `3d2ed6e769c` (2026-07-29) — [Easter2023] [2] Extend iClone MCP support for RIMaterialComponent properties
* `58aea270310` (2026-07-29) — [Easter2023] [2] Add a local MCP bridge for iCloneQt

