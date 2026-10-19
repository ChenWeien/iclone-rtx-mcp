from __future__ import annotations

import ctypes
import os
import tempfile
import threading


_MAX_CAPTURE_PIXELS = 16_777_216
_MAX_PNG_BYTES = 32 * 1024 * 1024
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_GW_OWNER = 4


def capture_window_png(
    executable_name: str | None,
) -> tuple[bytes, dict[str, object]]:
    """Capture an app HWND from the MCP host using Windows Graphics Capture."""
    if os.name != "nt":
        raise RuntimeError("Window capture is only available on Windows.")
    if executable_name not in (None, "iClone.exe", "CharacterCreator.exe"):
        raise ValueError("Unsupported application executable name.")

    from ctypes import wintypes
    from windows_capture import WindowsCapture

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL

    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    process_paths: dict[int, str | None] = {}
    candidates: list[tuple[int, int, str, str]] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def process_path(process_id: int) -> str | None:
        if process_id in process_paths:
            return process_paths[process_id]
        handle = kernel32.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION, False, process_id
        )
        if not handle:
            process_paths[process_id] = None
            return None
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)
            ):
                process_paths[process_id] = os.path.normcase(
                    os.path.abspath(buffer.value)
                )
            else:
                process_paths[process_id] = None
        finally:
            kernel32.CloseHandle(handle)
        return process_paths[process_id]

    def visit_window(hwnd, _unused_lparam):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, _GW_OWNER):
            return True
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        path = process_path(process_id.value) if process_id.value else None
        if not path:
            return True
        actual_executable = os.path.basename(path).casefold()
        if actual_executable not in {"iclone.exe", "charactercreator.exe"}:
            return True
        if executable_name and actual_executable != executable_name.casefold():
            return True

        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        if width <= 0 or height <= 0 or width * height > _MAX_CAPTURE_PIXELS:
            return True
        title_length = user32.GetWindowTextLengthW(hwnd)
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
        candidates.append((width * height, int(hwnd), title_buffer.value, path))
        return True

    callback = callback_type(visit_window)
    if not user32.EnumWindows(callback, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    if not candidates:
        raise RuntimeError("No visible iClone or Character Creator window was found.")

    if executable_name is None and len(
        {os.path.basename(item[3]).casefold() for item in candidates}
    ) > 1:
        raise RuntimeError(
            "Both iClone and Character Creator are open; use their configured MCP port."
        )
    # ponytail: if several builds of one app are open, choose the largest window; map the MCP port to PID if that becomes common.
    _, hwnd, title, path = max(candidates, key=lambda item: item[0])
    if user32.IsIconic(wintypes.HWND(hwnd)):
        raise RuntimeError("Restore the application window before capturing it.")

    descriptor, output_path = tempfile.mkstemp(
        prefix="iclone_mcp_capture_", suffix=".png"
    )
    os.close(descriptor)
    frame_arrived = threading.Event()
    capture_result: dict[str, int] = {}
    capture_errors: list[Exception] = []
    capture = WindowsCapture(
        window_hwnd=hwnd,
        cursor_capture=False,
        draw_border=False,
    )

    @capture.event
    def on_frame_arrived(frame, capture_control):
        try:
            if not capture_result:
                capture_result["width"] = int(frame.width)
                capture_result["height"] = int(frame.height)
                frame.save_as_image(output_path)
        except Exception as error:
            capture_errors.append(error)
        finally:
            frame_arrived.set()
            capture_control.stop()

    @capture.event
    def on_closed():
        frame_arrived.set()

    try:
        control = capture.start_free_threaded()
        if not frame_arrived.wait(10):
            control.stop()
            control.wait()
            raise RuntimeError("Windows Graphics Capture did not return a frame.")
        control.wait()
        if capture_errors:
            raise RuntimeError("Windows Graphics Capture failed: {0}".format(capture_errors[0]))
        if not capture_result or not os.path.isfile(output_path):
            raise RuntimeError("Windows Graphics Capture closed before returning a frame.")
        image_size = os.path.getsize(output_path)
        if image_size <= 0 or image_size > _MAX_PNG_BYTES:
            raise RuntimeError("The captured PNG is empty or exceeds the 32 MiB limit.")
        with open(output_path, "rb") as image_file:
            image_data = image_file.read()
    finally:
        try:
            os.remove(output_path)
        except OSError:
            pass

    return image_data, {
        "width": capture_result["width"],
        "height": capture_result["height"],
        "application": os.path.basename(path),
        "window_title": title,
        "capture_method": "Windows.Graphics.Capture",
        "application_path": path,
    }
