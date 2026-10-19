import RLPy


def _find_object(args):
    object_id = args.get("object_id")
    name = args.get("name")
    if object_id is not None and name is not None:
        raise ValueError("Pass either object_id or name, not both.")

    if object_id is not None:
        obj = RLPy.RScene.QueryObjectByID(str(object_id))
    elif name:
        obj = RLPy.RScene.FindObject(RLPy.EObjectType_LensFlare, name)
    else:
        selected = RLPy.RScene.GetSelectedObjects()
        obj = next(
            (item for item in selected if item.GetType() == RLPy.EObjectType_LensFlare),
            None,
        )
        if obj is None:
            flares = RLPy.RScene.FindObjects(RLPy.EObjectType_LensFlare)
            obj = flares[0] if flares else None

    if obj is None or obj.GetType() != RLPy.EObjectType_LensFlare:
        raise ValueError("No lens flare was found.")
    return obj


def _find_widget(object_name, widget_type):
    from PySide2 import QtWidgets
    from shiboken2 import isValid, wrapInstance

    try:
        address = RLPy.RUi.GetMainWindow()
        if address is None:
            return None
        main_window = wrapInstance(int(address), QtWidgets.QMainWindow)
        widget = main_window.findChild(widget_type, object_name)
        return widget if widget is not None and isValid(widget) else None
    except RuntimeError:
        return None


def prepare_lens_flare_preview(args):
    from PySide2 import QtWidgets

    flare = _find_object(args)
    if RLPy.RScene.ClearSelectObjects() != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not clear the current selection.")
    if RLPy.RScene.SelectObject(flare) != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not select the lens flare.")

    view_gate = args.get("view_gate", True)
    show_region = args.get("show_region", True)
    result = {
        "object": {"id": str(flare.GetID()), "name": str(flare.GetName())},
        "view_gate": {"requested": view_gate, "found": False},
        "show_region": {"requested": show_region, "found": False},
    }

    view_gate_widget = _find_widget("qtViewGate", QtWidgets.QGroupBox)
    if view_gate_widget is not None:
        try:
            result["view_gate"].update(
                {"found": True, "checked_before": bool(view_gate_widget.isChecked())}
            )
            if view_gate_widget.isChecked() != view_gate:
                view_gate_widget.click()
            result["view_gate"]["checked"] = bool(view_gate_widget.isChecked())
        except RuntimeError:
            result["view_gate"] = {"requested": view_gate, "found": False}

    show_region_widget = _find_widget(
        "qtLensFlareShowRegionCheckBox", QtWidgets.QCheckBox
    )
    if show_region_widget is not None:
        try:
            result["show_region"].update(
                {"found": True, "checked_before": bool(show_region_widget.isChecked())}
            )
            if show_region_widget.isChecked() != show_region:
                show_region_widget.click()
            result["show_region"]["checked"] = bool(show_region_widget.isChecked())
        except RuntimeError:
            result["show_region"] = {"requested": show_region, "found": False}

    QtWidgets.QApplication.processEvents()
    return result


def register(registry):
    registry["prepare_lens_flare_preview"] = {
        "handler": prepare_lens_flare_preview,
        "main_thread": True,
        "description": (
            "Select a lens flare and prepare Show Region verification using the "
            "targeted native controls."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "name": {"type": "string"},
                "show_region": {"type": "boolean", "default": True},
                "view_gate": {"type": "boolean", "default": True},
            },
        },
    }
