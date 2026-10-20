import json
import os
import platform
import re
import shutil
import subprocess
import sys

import RLPy


def _call(name, default=None):
    method = getattr(RLPy.RApplication, name, None)
    if method is None:
        return default
    try:
        value = method()
        return value.ToString() if hasattr(value, "ToString") else str(value)
    except Exception as error:
        return {"error": str(error)}


def _call_value(name, *args):
    method = getattr(RLPy.RApplication, name, None)
    if method is None:
        return None
    try:
        value = method(*args)
        return value.ToString() if hasattr(value, "ToString") else value
    except Exception as error:
        return {"error": str(error)}


def get_application_info(_args):
    """Return read-only host information, without relying on iClone 7 APIs."""
    return {
        "application": "iClone",
        "supported_api": "iClone 8 Python API",
        "api_version": _call("GetApiVersion"),
        "api_major_version": _call_value("GetApiMajorVersion"),
        "api_minor_version": _call_value("GetApiMinorVersion"),
        "product_name": _call("GetProductName"),
        "product_edition": _call("GetProductEdition"),
        "product_version": _call("GetProductVersion"),
        "product_major_version": _call_value("GetProductMajorVersion"),
        "product_minor_version": _call_value("GetProductMinorVersion"),
        "program_path": _call("GetProgramPath"),
        "current_project_path": _call("GetCurrentProjectPath"),
        "template_data_path": _call("GetTemplateDataPath"),
        "custom_data_path": _call("GetCustomDataPath"),
        "custom_content_folder": _call("GetCustomContentFolder"),
        "default_content_folder": _call("GetDefaultContentFolder"),
        "default_project_path": _call("GetDefaultProjectPath"),
    }


def _license_field(state, name, getters=()):
    if isinstance(state, dict):
        return state.get(name)
    for getter in getters or ("Get" + "".join(part.title() for part in name.split("_")),):
        method = getattr(state, getter, None)
        if method is not None:
            try:
                value = method() if callable(method) else method
                return value.ToString() if hasattr(value, "ToString") else value
            except Exception:
                return None
    return getattr(state, name, None)


def get_license_state(_args):
    get_state = getattr(RLPy.RApplication, "GetLicenseState", None)
    state = None
    if get_state is not None:
        try:
            state = get_state()
        except Exception:
            state = None

    edition = _call("GetProductEdition")
    if state is not None:
        edition = _license_field(state, "product_edition", ("GetProductEdition", "GetEdition")) or edition
    entitlement_type = _license_field(state, "entitlement_type", ("GetEntitlementType",))
    identity_category = _license_field(state, "identity_category", ("GetIdentityCategory",))
    rtx_entitlement = _license_field(state, "rtx_entitlement", ("GetRtxEntitlement", "GetRTXEntitlement"))
    unavailable = _license_field(state, "unavailable", ("IsUnavailable",))
    unavailable_reason = _license_field(state, "unavailable_reason", ("GetUnavailableReason",))

    if isinstance(state, dict):
        result = dict(state)
    else:
        result = {}
    result.update(
        {
            "product_edition": edition,
            "entitlement_type": entitlement_type or "unknown",
            "identity_category": identity_category or "unknown",
            "rtx_entitlement": rtx_entitlement or "unknown",
            "unavailable": bool(unavailable) if unavailable is not None else state is None,
            "unavailable_reason": unavailable_reason
            or ("The running iClone build does not expose license entitlement details." if state is None else None),
        }
    )
    return result


def list_content_folders(args):
    parent = args.get("parent") or _call("GetDefaultContentFolder")
    if not parent or not isinstance(parent, str) or not os.path.isdir(parent):
        raise FileNotFoundError("Content folder not found: %s" % parent)
    method = getattr(RLPy.RApplication, "GetContentFoldersInFolder", None)
    if method is None:
        raise RuntimeError("GetContentFoldersInFolder is not exposed by this iClone 8 build")
    values = method(parent)
    return {"parent": parent, "folders": [str(value) for value in values]}


def list_content_files(args):
    parent = args.get("parent") or _call("GetDefaultContentFolder")
    if not parent or not isinstance(parent, str) or not os.path.isdir(parent):
        raise FileNotFoundError("Content folder not found: %s" % parent)
    method = getattr(RLPy.RApplication, "GetContentFilesInFolder", None)
    if method is None:
        raise RuntimeError("GetContentFilesInFolder is not exposed by this iClone 8 build")
    values = method(parent)
    return {"parent": parent, "files": [str(value) for value in values]}


def _run_command(command):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"error": str(error)}
    return {
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _nvidia_smi():
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"status": "unavailable", "gpus": []}
    response = _run_command(
        [
            executable,
            "--query-gpu=name,driver_version,memory.total,memory.used,uuid",
            "--format=csv,noheader,nounits",
        ]
    )
    if "error" in response or response["returncode"] != 0:
        return {"status": "error", "detail": response, "gpus": []}
    gpus = []
    for line in response["stdout"].splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 5:
            continue
        gpus.append(
            {
                "name": fields[0],
                "driver_version": fields[1],
                "vram_total_mb": int(fields[2]) if fields[2].isdigit() else None,
                "vram_used_mb": int(fields[3]) if fields[3].isdigit() else None,
                "uuid": fields[4],
            }
        )
    return {"status": "ok", "gpus": gpus}


def _windows_video_controllers():
    executable = shutil.which("powershell.exe") or shutil.which("pwsh")
    if not executable:
        return {"status": "unavailable", "adapters": []}
    response = _run_command(
        [
            executable,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-CimInstance Win32_VideoController | "
            "Select-Object Name,DriverVersion,DriverDate,AdapterRAM,PNPDeviceID | "
            "ConvertTo-Json -Compress",
        ]
    )
    if "error" in response or response["returncode"] != 0:
        return {"status": "error", "detail": response, "adapters": []}
    try:
        values = json.loads(response["stdout"]) if response["stdout"] else []
    except ValueError as error:
        return {"status": "error", "detail": str(error), "adapters": []}
    if isinstance(values, dict):
        values = [values]
    adapters = []
    for value in values:
        if not isinstance(value, dict):
            continue
        adapter_ram = value.get("AdapterRAM")
        try:
            adapter_ram = int(adapter_ram) if adapter_ram is not None else None
        except (TypeError, ValueError):
            adapter_ram = None
        adapters.append(
            {
                "name": value.get("Name"),
                "driver_version": value.get("DriverVersion"),
                "driver_date": value.get("DriverDate"),
                "vram_bytes": adapter_ram,
                "pnp_device_id": value.get("PNPDeviceID"),
            }
        )
    return {"status": "ok", "adapters": adapters}


def get_system_compatibility(_args):
    """Return a best-effort host snapshot for compatibility test evidence."""
    win32_version = platform.win32_ver()
    return {
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "win32_version": {
                "release": win32_version[0],
                "version": win32_version[1],
                "csd": win32_version[2],
                "ptype": win32_version[3],
            },
            "machine": platform.machine(),
        },
        "python_version": sys.version.split()[0],
        "wmi_video_controllers": _windows_video_controllers(),
        "nvidia_smi": _nvidia_smi(),
        "paths": {
            "program": _call("GetProgramPath"),
            "current_project": _call("GetCurrentProjectPath"),
            "default_project": _call("GetDefaultProjectPath"),
        },
        "capabilities": {
            "d3d12_raytracing": "not_exposed_by_public_RLPy",
            "ray_query": "not_exposed_by_public_RLPy",
            "cuda_oidn_device": "not_exposed_by_public_RLPy",
        },
    }


def _main_window():
    from shiboken2 import wrapInstance
    from PySide2 import QtWidgets

    address = RLPy.RUi.GetMainWindow()
    if address is None:
        raise RuntimeError("iClone's main window is not available")
    return wrapInstance(int(address), QtWidgets.QMainWindow)


def _json_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "toPyObject"):
        return _json_value(value.toPyObject())
    return str(value)


def _property_is_writable(widget, name):
    meta_object = widget.metaObject()
    index = meta_object.indexOfProperty(name)
    return index >= 0 and bool(meta_object.property(index).isWritable())


def _all_widgets():
    from PySide2 import QtWidgets
    from shiboken2 import getCppPointer, isValid

    try:
        windows = QtWidgets.QApplication.topLevelWidgets() or [_main_window()]
    except (AttributeError, RuntimeError):
        windows = [_main_window()]
    widgets = []
    seen = set()
    for window in windows:
        try:
            candidates = [window] + window.findChildren(QtWidgets.QWidget)
        except (AttributeError, RuntimeError):
            continue
        for widget in candidates:
            try:
                if not isValid(widget):
                    continue
                try:
                    identity = int(getCppPointer(widget)[0])
                except (IndexError, TypeError, ValueError):
                    identity = id(widget)
                if identity not in seen:
                    seen.add(identity)
                    widgets.append(widget)
            except RuntimeError:
                continue
    return widgets


def _dialog_slug(value):
    value = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return value or "dialog"


def _dialog_id(dialog):
    object_name = str(dialog.objectName()) if hasattr(dialog, "objectName") else ""
    if object_name:
        return object_name
    class_name = str(dialog.metaObject().className())
    title = str(dialog.windowTitle()) if hasattr(dialog, "windowTitle") else ""
    return "modal:{0}:{1}".format(_dialog_slug(class_name), _dialog_slug(title))


def _visible_dialogs():
    from shiboken2 import isValid
    from PySide2 import QtWidgets

    dialog_type = getattr(QtWidgets, "QDialog", None)
    try:
        candidates = QtWidgets.QApplication.topLevelWidgets()
    except (AttributeError, RuntimeError):
        candidates = _all_widgets()
    dialogs = []
    for dialog in candidates:
        try:
            if not isValid(dialog) or not dialog.isVisible():
                continue
            class_name = str(dialog.metaObject().className())
            if dialog_type is not None:
                is_dialog = isinstance(dialog, dialog_type)
            else:
                is_dialog = class_name.endswith("Dialog") or class_name == "QMessageBox"
            if is_dialog:
                dialogs.append(dialog)
        except (AttributeError, RuntimeError):
            continue
    return dialogs


def _find_dialog(dialog_id):
    if not isinstance(dialog_id, str) or not dialog_id:
        raise ValueError("dialog_id must be a non-empty string")
    matches = [dialog for dialog in _visible_dialogs() if _dialog_id(dialog) == dialog_id]
    if not matches:
        raise ValueError("No visible Qt dialog has id '{0}'".format(dialog_id))
    if len(matches) > 1:
        raise ValueError("More than one visible Qt dialog has id '{0}'".format(dialog_id))
    return matches[0]


def _dialog_role(text):
    normalized = str(text).strip().lower()
    for role, words in (
        ("cancel", ("cancel", "no")),
        ("ok", ("ok", "okay", "continue", "yes")),
        ("more", ("more", "details")),
        ("clamp", ("clamp",)),
    ):
        if any(word in normalized for word in words):
            return role
    return "custom"


def _dialog_buttons(dialog):
    from PySide2 import QtWidgets

    button_type = getattr(QtWidgets, "QAbstractButton", None)
    if button_type is None or not hasattr(dialog, "findChildren"):
        return []
    try:
        return list(dialog.findChildren(button_type))
    except (AttributeError, RuntimeError):
        return []


def _dialog_action_summaries(dialog):
    summaries = []
    used_ids = {}
    for button in _dialog_buttons(dialog):
        try:
            text = str(button.text()) if hasattr(button, "text") else ""
            object_name = str(button.objectName()) if hasattr(button, "objectName") else ""
            base_id = object_name or "action:{0}".format(_dialog_slug(text))
            used_ids[base_id] = used_ids.get(base_id, 0) + 1
            action_id = base_id
            if used_ids[base_id] > 1:
                action_id = "{0}:{1}".format(base_id, used_ids[base_id])
            summaries.append(
                {
                    "action_id": action_id,
                    "object_name": object_name,
                    "text": text,
                    "role": _dialog_role(text),
                    "enabled": bool(button.isEnabled()),
                    "visible": bool(button.isVisible()),
                    "checkable": bool(button.isCheckable()),
                    "checked": bool(button.isChecked()) if button.isCheckable() else False,
                }
            )
        except (AttributeError, RuntimeError):
            continue
    return summaries


def _dialog_summary(dialog):
    from PySide2 import QtWidgets

    title = str(dialog.windowTitle()) if hasattr(dialog, "windowTitle") else ""
    visible_text = []
    if title:
        visible_text.append(title)
    if hasattr(dialog, "findChildren"):
        for widget_type, getter in (
            (getattr(QtWidgets, "QLabel", None), "text"),
            (getattr(QtWidgets, "QAbstractButton", None), "text"),
            (getattr(QtWidgets, "QLineEdit", None), "text"),
        ):
            if widget_type is None:
                continue
            try:
                children = dialog.findChildren(widget_type)
            except (AttributeError, RuntimeError):
                children = []
            for child in children:
                try:
                    if not child.isVisible():
                        continue
                    text = str(getattr(child, getter)())
                    if text and text not in visible_text:
                        visible_text.append(text)
                except (AttributeError, RuntimeError):
                    continue

    checkboxes = []
    check_box_type = getattr(QtWidgets, "QCheckBox", None)
    if check_box_type is not None and hasattr(dialog, "findChildren"):
        try:
            checkbox_widgets = dialog.findChildren(check_box_type)
        except (AttributeError, RuntimeError):
            checkbox_widgets = []
        for checkbox in checkbox_widgets:
            try:
                checkboxes.append(
                    {
                        "object_name": str(checkbox.objectName()),
                        "text": str(checkbox.text()),
                        "enabled": bool(checkbox.isEnabled()),
                        "checked": bool(checkbox.isChecked()),
                    }
                )
            except (AttributeError, RuntimeError):
                continue

    return {
        "dialog_id": _dialog_id(dialog),
        "object_name": str(dialog.objectName()) if hasattr(dialog, "objectName") else "",
        "class_name": str(dialog.metaObject().className()),
        "title": title,
        "visible_text": visible_text,
        "checkboxes": checkboxes,
        "actions": _dialog_action_summaries(dialog),
    }


def get_modal_dialogs(_args):
    dialogs = [_dialog_summary(dialog) for dialog in _visible_dialogs()]
    return {"dialogs": dialogs, "count": len(dialogs)}


def get_dialog_actions(args):
    dialog = _find_dialog(args.get("dialog_id"))
    actions = _dialog_action_summaries(dialog)
    return {"dialog_id": _dialog_id(dialog), "actions": actions, "count": len(actions)}


def invoke_dialog_action(args):
    from PySide2 import QtWidgets

    dialog = _find_dialog(args.get("dialog_id"))
    action_id = args.get("action_id")
    if not isinstance(action_id, str) or not action_id:
        raise ValueError("action_id must be a non-empty string")
    summaries = _dialog_action_summaries(dialog)
    index = next((i for i, item in enumerate(summaries) if item["action_id"] == action_id), None)
    if index is None:
        raise ValueError("No action '{0}' exists in dialog '{1}'".format(action_id, _dialog_id(dialog)))
    button = _dialog_buttons(dialog)[index]
    if not button.isEnabled():
        raise RuntimeError("Dialog action is disabled")
    button.click()
    QtWidgets.QApplication.processEvents()
    remaining = [item for item in _visible_dialogs() if _dialog_id(item) == _dialog_id(dialog)]
    return {
        "dialog_id": _dialog_id(dialog),
        "action_id": action_id,
        "invoked": True,
        "dialog_visible": bool(remaining),
        "dialog": _dialog_summary(remaining[0]) if remaining else None,
    }


def _widget_summary(widget):
    from PySide2 import QtWidgets

    class_name = widget.metaObject().className()
    result = {
        "object_name": str(widget.objectName()),
        "class_name": str(class_name),
        "visible": bool(widget.isVisible()),
        "enabled": bool(widget.isEnabled()),
    }
    if isinstance(widget, QtWidgets.QGroupBox):
        result["title"] = str(widget.title())
    if str(class_name) == "QColorButton":
        pixmap = widget.icon().pixmap(32, 16)
        if not pixmap.isNull():
            color = pixmap.toImage().pixelColor(pixmap.width() // 2, pixmap.height() // 2)
            result["value"] = {
                "r": round(float(color.red()) / 255.0, 6),
                "g": round(float(color.green()) / 255.0, 6),
                "b": round(float(color.blue()) / 255.0, 6),
                "a": round(float(color.alpha()) / 255.0, 6),
            }
    elif isinstance(widget, QtWidgets.QComboBox):
        result.update(
            {
                "value": {
                    "index": int(widget.currentIndex()),
                    "text": str(widget.currentText()),
                    "data": _json_value(widget.currentData()),
                },
                "items": [
                    {"index": i, "text": str(widget.itemText(i)), "data": _json_value(widget.itemData(i))}
                    for i in range(widget.count())
                ],
            }
        )
    elif isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox, QtWidgets.QSlider)):
        result["value"] = _json_value(widget.value())
        result["minimum"] = _json_value(widget.minimum())
        result["maximum"] = _json_value(widget.maximum())
    elif _property_is_writable(widget, "value"):
        result["value"] = _json_value(widget.property("value"))
    elif isinstance(widget, QtWidgets.QLineEdit):
        result["value"] = str(widget.text())
    elif isinstance(widget, QtWidgets.QAbstractButton):
        result["text"] = str(widget.text())
        result["value"] = bool(widget.isChecked()) if widget.isCheckable() else str(widget.text())
    elif isinstance(widget, QtWidgets.QLabel):
        result["value"] = str(widget.text())
    for name in ("minimum", "maximum"):
        getter = getattr(widget, name, None)
        if callable(getter):
            try:
                result[name] = _json_value(getter())
            except Exception:
                pass
    return result


def get_ui_widgets(args):
    from PySide2 import QtWidgets
    from shiboken2 import isValid

    contains = args.get("contains") or ""
    class_name = args.get("class_name") or ""
    limit = args.get("limit", 200)
    if not isinstance(contains, str) or not isinstance(class_name, str):
        raise ValueError("contains and class_name must be strings")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")

    widgets = []
    for widget in _all_widgets():
        try:
            object_name = str(widget.objectName())
            if not object_name:
                continue
            if contains.lower() not in object_name.lower():
                continue
            actual_class = str(widget.metaObject().className())
            if class_name and class_name != actual_class:
                continue
            widgets.append(_widget_summary(widget))
            if len(widgets) >= limit:
                break
        except Exception:
            continue
    return {"widgets": widgets, "count": len(widgets), "truncated": len(widgets) >= limit}


def _action_summary(action):
    parent = action.parent()
    parent_text = str(parent.title()) if parent is not None and hasattr(parent, "title") else ""
    return {
        "text": str(action.text()),
        "object_name": str(action.objectName()),
        "parent": parent_text,
        "enabled": bool(action.isEnabled()),
        "checkable": bool(action.isCheckable()),
        "checked": bool(action.isChecked()) if action.isCheckable() else False,
    }


def _all_actions():
    from PySide2 import QtWidgets
    from shiboken2 import getCppPointer, isValid

    main_window = _main_window()
    actions = []
    seen_actions = set()
    seen_menus = set()

    def add(action):
        try:
            if not isValid(action):
                return
            try:
                identity = int(getCppPointer(action)[0])
            except (IndexError, TypeError, ValueError):
                identity = id(action)
            if identity not in seen_actions:
                seen_actions.add(identity)
                actions.append(action)
        except RuntimeError:
            pass

    def add_menu(menu):
        try:
            if not isValid(menu) or id(menu) in seen_menus:
                return
            seen_menus.add(id(menu))
            for action in menu.actions():
                try:
                    add(action)
                    submenu = action.menu()
                except RuntimeError:
                    continue
                if submenu is not None:
                    add_menu(submenu)
        except RuntimeError:
            pass

    try:
        for top_action in main_window.menuBar().actions():
            try:
                add(top_action)
                menu = top_action.menu()
            except RuntimeError:
                continue
            if menu is not None:
                add_menu(menu)
        for action in main_window.findChildren(QtWidgets.QAction):
            add(action)
        for widget in _all_widgets():
            try:
                if isinstance(widget, QtWidgets.QMenu):
                    add_menu(widget)
            except RuntimeError:
                continue
    except AttributeError:
        pass
    return actions


def get_ui_actions(args):
    contains = args.get("contains") or ""
    limit = args.get("limit", 200)
    if not isinstance(contains, str):
        raise ValueError("contains must be a string")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")

    actions = []
    for action in _all_actions():
        try:
            summary = _action_summary(action)
            if contains.lower() not in (summary["text"] + " " + summary["object_name"]).lower():
                continue
            actions.append(summary)
            if len(actions) >= limit:
                break
        except RuntimeError:
            continue
    return {"actions": actions, "count": len(actions), "truncated": len(actions) >= limit}


def trigger_ui_action(args):
    from PySide2 import QtWidgets

    text = args.get("text")
    object_name = args.get("object_name")
    occurrence = args.get("occurrence")
    if not isinstance(text, str) and not isinstance(object_name, str):
        raise ValueError("text or object_name is required")
    if occurrence is not None and (
        isinstance(occurrence, bool) or not isinstance(occurrence, int) or occurrence < 0
    ):
        raise ValueError("occurrence must be a non-negative integer")
    matches = []
    for action in _all_actions():
        try:
            if object_name is not None and str(action.objectName()) != object_name:
                continue
            if object_name is None and str(action.text()) != text:
                continue
            matches.append(action)
        except RuntimeError:
            continue
    if not matches:
        try:
            from shiboken2 import isValid

            for action in _main_window().findChildren(QtWidgets.QAction):
                if not isValid(action):
                    continue
                if object_name is not None and str(action.objectName()) == object_name:
                    matches.append(action)
                elif object_name is None and str(action.text()) == text:
                    matches.append(action)
        except (AttributeError, RuntimeError):
            pass
    if not matches:
        raise ValueError("No Qt action matched the requested text or object_name")
    if occurrence is not None:
        if occurrence >= len(matches):
            raise ValueError("occurrence is outside the matched Qt action list")
        matches = [matches[occurrence]]
    elif len(matches) > 1:
        context_matches = []
        for action in matches:
            try:
                associated_widgets = action.associatedWidgets()
                if any(
                    widget.isVisible() and widget.isEnabled()
                    for widget in associated_widgets
                ):
                    context_matches.append(action)
            except Exception:
                continue
        if len(context_matches) == 1:
            matches = context_matches
        else:
            visible_matches = [
                action for action in matches if action.isVisible() and action.isEnabled()
            ]
            if len(visible_matches) == 1:
                matches = visible_matches
            else:
                raise ValueError("More than one Qt action matched the requested text or object_name")
    action = matches[0]
    if not action.isEnabled():
        raise RuntimeError("Qt action is disabled")
    action.trigger()
    QtWidgets.QApplication.processEvents()
    return _action_summary(action)


def _find_widget(widgets, object_name, occurrence=None):
    if occurrence is None:
        base_name, separator, suffix = object_name.rpartition("#")
        if separator and suffix.isdigit():
            object_name, occurrence = base_name, int(suffix)
    matches = []
    for widget in widgets:
        try:
            if str(widget.objectName()) == object_name:
                matches.append(widget)
        except RuntimeError:
            continue
    if not matches:
        raise ValueError("No Qt widget has objectName '{0}'".format(object_name))
    if occurrence is not None:
        if (
            isinstance(occurrence, bool)
            or not isinstance(occurrence, int)
            or occurrence < 0
        ):
            raise ValueError("occurrence must be a non-negative integer")
        if occurrence >= len(matches):
            raise ValueError("occurrence is outside the matched Qt widget list")
        return matches[occurrence]
    if len(matches) > 1:
        visible_matches = [widget for widget in matches if widget.isVisible()]
        if len(visible_matches) == 1:
            return visible_matches[0]
        raise ValueError("More than one Qt widget has objectName '{0}'".format(object_name))
    return matches[0]


def set_ui_value(args):
    from PySide2 import QtWidgets

    object_name = args.get("object_name")
    if not isinstance(object_name, str) or not object_name:
        raise ValueError("object_name must be a non-empty string")
    if "value" not in args:
        raise ValueError("value is required")
    # Keep the Qt tree wrappers alive through the write and its result summary.
    widgets = _all_widgets()
    widget = _find_widget(widgets, object_name, args.get("occurrence"))
    value = args["value"]
    property_name = args.get("property")

    if property_name is not None:
        if not isinstance(property_name, str) or not property_name:
            raise ValueError("property must be a non-empty string")
        if not _property_is_writable(widget, property_name):
            raise ValueError("Qt property '{0}' on '{1}' is not writable".format(property_name, object_name))
        if widget.setProperty(property_name, value) is False:
            raise ValueError("Qt property '{0}' on '{1}' rejected the value".format(property_name, object_name))
    if property_name is None and isinstance(widget, QtWidgets.QComboBox):
        if isinstance(value, dict) and "index" in value:
            index = int(value["index"])
        elif isinstance(value, dict) and "text" in value:
            index = widget.findText(str(value["text"]))
        elif isinstance(value, dict) and "data" in value:
            index = widget.findData(value["data"])
        elif isinstance(value, bool):
            index = int(value)
        elif isinstance(value, int):
            index = value
        else:
            index = widget.findText(str(value))
        if index < 0 or index >= widget.count():
            raise ValueError("value does not identify an item in '{0}'".format(object_name))
        widget.setCurrentIndex(index)
    elif property_name is None and isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox, QtWidgets.QSlider)):
        widget.setValue(value)
    elif property_name is None and str(widget.metaObject().className()) == "QColorButton":
        from PySide2 import QtGui

        if not isinstance(value, dict):
            raise ValueError("QColorButton value must be an RGB or RGBA object")
        channels = [value.get(key) for key in ("r", "g", "b")]
        alpha = value.get("a", 1.0)
        if any(isinstance(channel, bool) or not isinstance(channel, (int, float)) for channel in channels) or isinstance(alpha, bool) or not isinstance(alpha, (int, float)):
            raise ValueError("QColorButton value channels must be numeric")
        if any(channel < 0.0 or channel > 1.0 for channel in channels + [alpha]):
            raise ValueError("QColorButton value channels must be between 0 and 1")
        color = QtGui.QColor.fromRgbF(float(channels[0]), float(channels[1]), float(channels[2]), float(alpha))
        if widget.setProperty("Color", color) is False:
            raise ValueError("Qt property 'Color' on '{0}' rejected the value".format(object_name))
    elif property_name is None and _property_is_writable(widget, "value"):
        if widget.setProperty("value", value) is False:
            raise ValueError("Qt property 'value' on '{0}' rejected the value".format(object_name))
    elif property_name is None and isinstance(widget, QtWidgets.QLineEdit):
        widget.setText(str(value))
    elif property_name is None and isinstance(widget, QtWidgets.QAbstractButton) and widget.isCheckable():
        desired = bool(value)
        if widget.isChecked() != desired:
            widget.click()
    elif property_name is None and isinstance(widget, QtWidgets.QAbstractButton) and str(value).lower() in ("click", "true", "1"):
        widget.click()
    elif property_name is None:
        raise ValueError("Qt widget type '{0}' is not writable".format(widget.metaObject().className()))

    QtWidgets.QApplication.processEvents()
    return _widget_summary(widget)


def click_ui_widget(args):
    from PySide2 import QtCore, QtTest, QtWidgets

    object_name = args.get("object_name")
    if not isinstance(object_name, str) or not object_name:
        raise ValueError("object_name must be a non-empty string")
    widgets = _all_widgets()
    widget = _find_widget(widgets, object_name, args.get("occurrence"))
    if not widget.isVisible() or not widget.isEnabled():
        raise RuntimeError("Qt widget '{0}' must be visible and enabled".format(object_name))
    QtTest.QTest.mouseClick(widget, QtCore.Qt.LeftButton)
    QtWidgets.QApplication.processEvents()
    return _widget_summary(widget)


def get_ui(args):
    scope = (args.get("scope") or "").lower()
    if scope == "widgets":
        return get_ui_widgets(args)
    if scope == "actions":
        return get_ui_actions(args)
    if scope == "dialogs":
        return get_modal_dialogs(args)
    if scope == "dialog_actions":
        return get_dialog_actions(args)
    raise ValueError("scope must be one of: widgets, actions, dialogs, dialog_actions")


def invoke_ui(args):
    action = (args.get("action") or "").lower()
    if action == "trigger":
        return trigger_ui_action(args)
    if action == "invoke_dialog":
        return invoke_dialog_action(args)
    if action == "set_value":
        return set_ui_value(args)
    if action == "click_widget":
        return click_ui_widget(args)
    raise ValueError("action must be one of: trigger, invoke_dialog, set_value, click_widget")


def register(registry):
    registry["get_ui"] = {
        "handler": get_ui,
        "main_thread": True,
        "read_only": True,
        "description": "Inspect UI widgets, actions, dialogs, or dialog actions (scope).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["widgets", "actions", "dialogs", "dialog_actions"],
                },
                "contains": {"type": "string"},
                "class_name": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
                "dialog_id": {"type": "string"},
            },
            "required": ["scope"],
        },
    }
    registry["invoke_ui"] = {
        "handler": invoke_ui,
        "main_thread": True,
        "description": "Trigger a UI action, invoke a dialog action, set a widget value, or click a widget.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["trigger", "invoke_dialog", "set_value", "click_widget"]},
                "text": {"type": "string"},
                "object_name": {"type": "string"},
                "occurrence": {"type": "integer", "minimum": 0},
                "dialog_id": {"type": "string"},
                "action_id": {"type": "string"},
                "property": {"type": "string"},
                "value": {},
            },
            "required": ["action"],
        },
    }

    _hidden = {"advertise": False, "main_thread": True}
    registry["get_application_info"] = dict(
        _hidden,
        handler=get_application_info,
        read_only=True,
        description="Return iClone version and path information.",
        inputSchema={"type": "object", "properties": {}},
    )
    registry["get_license_state"] = dict(
        _hidden,
        handler=get_license_state,
        read_only=True,
        description="Return product edition and entitlement state.",
        inputSchema={"type": "object", "properties": {}},
    )
    registry["list_content_folders"] = dict(
        _hidden,
        handler=list_content_folders,
        read_only=True,
        description="List content subfolders via Smart Content Manager API.",
        inputSchema={"type": "object", "properties": {"parent": {"type": "string"}}},
    )
    registry["list_content_files"] = dict(
        _hidden,
        handler=list_content_files,
        read_only=True,
        description="List content files via Smart Content Manager API.",
        inputSchema={"type": "object", "properties": {"parent": {"type": "string"}}},
    )
    registry["get_system_compatibility"] = dict(
        _hidden,
        handler=get_system_compatibility,
        read_only=True,
        description="Return OS/GPU/driver snapshot for compatibility tests.",
        inputSchema={"type": "object", "properties": {}},
    )
    registry["get_ui_widgets"] = dict(
        _hidden,
        handler=get_ui_widgets,
        read_only=True,
        description="Inspect visible Qt widgets by objectName.",
        inputSchema={
            "type": "object",
            "properties": {
                "contains": {"type": "string"},
                "class_name": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
        },
    )
    registry["get_ui_actions"] = dict(
        _hidden,
        handler=get_ui_actions,
        read_only=True,
        description="Inspect visible QActions by text or objectName.",
        inputSchema={
            "type": "object",
            "properties": {
                "contains": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
        },
    )
    registry["trigger_ui_action"] = dict(
        _hidden,
        handler=trigger_ui_action,
        description="Trigger a QAction by exact text or objectName.",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "object_name": {"type": "string"},
                "occurrence": {"type": "integer", "minimum": 0},
            },
            "oneOf": [{"required": ["text"]}, {"required": ["object_name"]}],
        },
    )
    registry["get_modal_dialogs"] = dict(
        _hidden,
        handler=get_modal_dialogs,
        read_only=True,
        description="Inspect visible Qt dialogs.",
        inputSchema={"type": "object", "properties": {}},
    )
    registry["get_dialog_actions"] = dict(
        _hidden,
        handler=get_dialog_actions,
        read_only=True,
        description="List stable actions on a visible Qt dialog.",
        inputSchema={
            "type": "object",
            "properties": {"dialog_id": {"type": "string"}},
            "required": ["dialog_id"],
        },
    )
    registry["invoke_dialog_action"] = dict(
        _hidden,
        handler=invoke_dialog_action,
        description="Invoke a dialog action by id.",
        inputSchema={
            "type": "object",
            "properties": {"dialog_id": {"type": "string"}, "action_id": {"type": "string"}},
            "required": ["dialog_id", "action_id"],
        },
    )
    registry["set_ui_value"] = dict(
        _hidden,
        handler=set_ui_value,
        description="Set a writable Qt widget value or property.",
        inputSchema={
            "type": "object",
            "properties": {
                "object_name": {"type": "string"},
                "occurrence": {"type": "integer", "minimum": 0},
                "property": {"type": "string"},
                "value": {},
            },
            "required": ["object_name", "value"],
        },
    )
