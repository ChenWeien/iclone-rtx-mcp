import os
import runpy

import RLPy


def _api_version(_args):
    return {"server": "mc-iclone8-mcp", "api": "iClone 8 RLPy", "python": "3.8+"}


def _ping(_args):
    return {"status": "ok"}


def _runtime_diagnostics(_args):
    time = RLPy.RGlobal.GetTime()
    fps = RLPy.RGlobal.GetFps()
    public = lambda value: sorted(name for name in dir(value) if not name.startswith("_"))
    return {
        "rtime_class_members": public(RLPy.RTime),
        "current_time_members": public(time),
        "fps_repr": repr(fps),
        "fps_members": public(fps),
        "time_repr": repr(time),
    }


def _run_python_file(args):
    if args.get("confirm") != "RUN_PYTHON_FILE":
        raise ValueError("Set confirm to RUN_PYTHON_FILE to execute a Python file")

    path = args.get("path")
    if not isinstance(path, str) or not path:
        raise ValueError("path must be a non-empty string.")
    path = os.path.normpath(path)
    if not os.path.isabs(path):
        raise ValueError("path must be an absolute path.")
    if os.path.splitext(path)[1].lower() != ".py":
        raise ValueError("path must point to a .py file.")
    if not os.path.isfile(path):
        raise ValueError("Python file does not exist: {0}".format(path))

    try:
        runpy.run_path(path, run_name="__main__")
    except SystemExit as error:
        raise RuntimeError("Python file exited with code {0}.".format(error.code))
    except Exception as error:
        raise RuntimeError(
            "Python file failed with {0}: {1}".format(type(error).__name__, error)
        )
    return {"status": "completed", "path": path}


def register(registry):
    registry["run_python_file"] = {
        "handler": _run_python_file,
        "main_thread": True,
        "destructive": True,
        "description": "Execute a local Python file in iClone's embedded Python. Requires confirm RUN_PYTHON_FILE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to a .py file."},
                "confirm": {"type": "string", "description": "Exact value: RUN_PYTHON_FILE"},
            },
            "required": ["path", "confirm"],
        },
    }

    _hidden = {"advertise": False}
    registry["get_api_version"] = dict(
        _hidden,
        handler=_api_version,
        read_only=True,
        description="Return server version and iClone 8 API target.",
        inputSchema={"type": "object", "properties": {}},
    )
    registry["ping_iclone"] = dict(
        _hidden,
        handler=_ping,
        read_only=True,
        description="Check that the MCP bridge is responding.",
        inputSchema={"type": "object", "properties": {}},
    )
    registry["get_runtime_diagnostics"] = dict(
        _hidden,
        handler=_runtime_diagnostics,
        main_thread=True,
        read_only=True,
        description="Return RLPy capability diagnostics without modifying the scene.",
        inputSchema={"type": "object", "properties": {}},
    )
