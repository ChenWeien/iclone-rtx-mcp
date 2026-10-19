"""Run via MCP run_python_file on a disposable, fully loaded RTX scene.
Configure different Preview/Final sample counts first. Calls the same preview
renderer as Current Frame Preview and saves evidence without opening a viewer.
"""
import json
from pathlib import Path

import RLPy
from PySide2 import QtGui
import iclone_mcp_tool_render as render

settings = render.get_render_settings({})
assert settings['render_system'] == 'dx12', settings
assert settings['preview']['accumulation_target'] != settings['final']['accumulation_target'], settings
output = Path(__file__).resolve().parents[3] / 'diagnostics' / 'mantis-100292'
output.mkdir(parents=True, exist_ok=True)
image_path = output / 'regression-preview.png'
old_timestamp = image_path.stat().st_mtime_ns if image_path.exists() else 0
assert RLPy.RGlobal.RenderPreview(str(image_path)) == RLPy.RStatus.Success
progress = render.get_render_progress({'include_statistics': True})
after = render.get_render_settings({})
assert progress['current_sample'] == settings['preview']['accumulation_target'], progress
assert progress['target_sample'] == settings['preview']['accumulation_target'], progress
for mode in ('preview', 'final'):
    assert after[mode] == settings[mode], (mode, settings[mode], after[mode])
assert image_path.exists() and image_path.stat().st_mtime_ns > old_timestamp, image_path
assert not QtGui.QImage(str(image_path)).isNull(), 'Preview PNG is unreadable'
(output / 'regression-preview.json').write_text(
    json.dumps({'before': settings, 'after': after, 'progress': progress}, indent=2),
    encoding='utf-8')
print('PASS: preview renderer uses Preview samples and preserves both setting banks')
