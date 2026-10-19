import os
import sys
import types


PLUGIN_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "plugin")
)
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

sys.modules.setdefault("RLPy", types.ModuleType("RLPy"))


class _QtWidgets:
    QAction = object
    QWidget = type("QWidget", (), {})
    QGroupBox = type("QGroupBox", (), {})
    QMenu = type("QMenu", (), {})
    QComboBox = type("QComboBox", (), {})
    QSpinBox = type("QSpinBox", (), {})
    QDoubleSpinBox = type("QDoubleSpinBox", (), {})
    QSlider = type("QSlider", (), {})
    QLineEdit = type("QLineEdit", (), {})
    QAbstractButton = type("QAbstractButton", (), {})
    QLabel = type("QLabel", (), {})

    class QApplication:
        @staticmethod
        def allWidgets():
            return []

        @staticmethod
        def topLevelWidgets():
            return []

        @staticmethod
        def processEvents():
            pass


sys.modules.setdefault("PySide2", types.ModuleType("PySide2")).QtWidgets = _QtWidgets
shiboken2 = sys.modules.setdefault("shiboken2", types.ModuleType("shiboken2"))
shiboken2.isValid = lambda unused_object: True
shiboken2.getCppPointer = lambda obj: (id(obj),)

import iclone_mcp_tool_diagnostics as diagnostics


class _MetaObject:
    def className(self):
        return "QUnlistedWidget"

    def indexOfProperty(self, name):
        return 0 if name in {"value", "minimum"} else -1

    def property(self, unused_index):
        return _MetaProperty()


class _MetaProperty:
    def isWritable(self):
        return True


class _ComboDoubleSpinBox:
    def __init__(self):
        self._properties = {"value": 0.25, "minimum": 0.0}

    def metaObject(self):
        return _MetaObject()

    def objectName(self):
        return "qtTestComboDoubleSpinBox"

    def isVisible(self):
        return True

    def isEnabled(self):
        return True

    def property(self, name):
        return self._properties.get(name)

    def setProperty(self, name, value):
        if name not in self._properties:
            return False
        self._properties[name] = value
        return True


def test_combo_double_spin_box_is_writable():
    widget = _ComboDoubleSpinBox()
    original_all_widgets = diagnostics._all_widgets
    diagnostics._all_widgets = lambda: [widget]
    try:
        result = diagnostics.set_ui_value(
            {"object_name": widget.objectName(), "value": 0.75}
        )
        assert widget._properties["value"] == 0.75
        assert result["value"] == 0.75

        result = diagnostics.set_ui_value(
            {"object_name": widget.objectName(), "property": "minimum", "value": 0.1}
        )
    finally:
        diagnostics._all_widgets = original_all_widgets

    assert widget._properties["minimum"] == 0.1
    assert result["value"] == 0.75


def test_find_widget_skips_deleted_widgets():
    class _DeletedWidget:
        def objectName(self):
            raise RuntimeError("Internal C++ object already deleted.")

    widget = _ComboDoubleSpinBox()
    original_all_widgets = diagnostics._all_widgets
    diagnostics._all_widgets = lambda: [_DeletedWidget(), widget]
    try:
        assert diagnostics._find_widget(diagnostics._all_widgets(), widget.objectName()) is widget
        assert diagnostics._find_widget(diagnostics._all_widgets(), widget.objectName() + "#0") is widget
        result = diagnostics.invoke_ui(
            {"action": "set_value", "object_name": widget.objectName(), "value": 0.75}
        )
        assert result["value"] == 0.75
        try:
            diagnostics._find_widget(diagnostics._all_widgets(), "missing")
        except ValueError as error:
            assert "No Qt widget" in str(error)
        else:
            raise AssertionError("Missing widgets must still fail lookup")
    finally:
        diagnostics._all_widgets = original_all_widgets


def test_set_ui_value_keeps_widget_tree_alive():
    class _Widget(_ComboDoubleSpinBox):
        deleted = False

        def setProperty(self, name, value):
            if self.deleted:
                raise RuntimeError("Internal C++ object already deleted.")
            return super().setProperty(name, value)

    widget = _Widget()

    class _Window:
        def objectName(self):
            return "window"

        def __del__(self):
            widget.deleted = True

    original_all_widgets = diagnostics._all_widgets
    diagnostics._all_widgets = lambda: [_Window(), widget]
    try:
        result = diagnostics.invoke_ui(
            {"action": "set_value", "object_name": widget.objectName(), "value": 0.75}
        )
        assert result["value"] == 0.75
    finally:
        diagnostics._all_widgets = original_all_widgets


class _Action:
    def __init__(self, text, checked=False):
        self._text = text
        self._checked = checked

    def objectName(self):
        return ""

    def text(self):
        return self._text

    def parent(self):
        return None

    def menu(self):
        return None

    def isEnabled(self):
        return True

    def isCheckable(self):
        return True

    def isChecked(self):
        return self._checked

    def trigger(self):
        self._checked = True


def test_widget_discovery_uses_all_top_level_trees():
    child_widget = _QtWidgets.QWidget()
    floating_child = _QtWidgets.QWidget()

    class _Window:
        def __init__(self, *children):
            self._children = children

        def findChildren(self, child_type):
            return list(self._children) if child_type is _QtWidgets.QWidget else []

    floating_window = _Window(floating_child)
    main_window = _Window(child_widget, floating_window)
    original_main_window = diagnostics._main_window
    original_all_widgets = _QtWidgets.QApplication.allWidgets
    original_top_level_widgets = _QtWidgets.QApplication.topLevelWidgets
    diagnostics._main_window = lambda: main_window
    _QtWidgets.QApplication.allWidgets = staticmethod(
        lambda: (_ for _ in ()).throw(AssertionError("global Qt sweep used"))
    )
    _QtWidgets.QApplication.topLevelWidgets = staticmethod(
        lambda: [main_window, floating_window]
    )
    try:
        assert diagnostics._all_widgets() == [
            main_window,
            child_widget,
            floating_window,
            floating_child,
        ]
    finally:
        diagnostics._main_window = original_main_window
        _QtWidgets.QApplication.allWidgets = staticmethod(original_all_widgets)
        _QtWidgets.QApplication.topLevelWidgets = staticmethod(
            original_top_level_widgets
        )


def test_trigger_ui_action_uses_exact_text():
    action = _Action("Progressive")

    class MenuBar:
        def actions(self):
            return [action]

    class MainWindow:
        def menuBar(self):
            return MenuBar()

        def findChildren(self, child_type):
            return [action] if child_type is _QtWidgets.QAction else []

    original_main_window = diagnostics._main_window
    original_all_widgets = _QtWidgets.QApplication.allWidgets
    diagnostics._main_window = lambda: MainWindow()
    _QtWidgets.QApplication.allWidgets = staticmethod(
        lambda: (_ for _ in ()).throw(AssertionError("global Qt sweep used"))
    )
    try:
        result = diagnostics.trigger_ui_action({"text": "Progressive"})
    finally:
        diagnostics._main_window = original_main_window
        _QtWidgets.QApplication.allWidgets = staticmethod(original_all_widgets)

    assert result["text"] == "Progressive"
    assert action.isChecked()


class _Color:
    def red(self):
        return 255

    def green(self):
        return 127

    def blue(self):
        return 0

    def alpha(self):
        return 255


class _Image:
    def pixelColor(self, unused_x, unused_y):
        return _Color()


class _Pixmap:
    def isNull(self):
        return False

    def width(self):
        return 16

    def height(self):
        return 16

    def toImage(self):
        return _Image()


class _ColorButton:
    def metaObject(self):
        return self

    def className(self):
        return "QColorButton"

    def objectName(self):
        return "qtColorButton"

    def isVisible(self):
        return True

    def isEnabled(self):
        return True

    def icon(self):
        return self

    def pixmap(self, unused_width, unused_height):
        return _Pixmap()


def test_color_button_summary_reads_swatch_color():
    result = diagnostics._widget_summary(_ColorButton())
    assert result["value"] == {"r": 1.0, "g": 0.498039, "b": 0.0, "a": 1.0}


class _DialogMetaObject:
    def className(self):
        return "QDialog"


class _Dialog:
    def objectName(self):
        return "qtRtxScenePreparationDialog"

    def metaObject(self):
        return _DialogMetaObject()

    def windowTitle(self):
        return "RTX Conversion"

    def findChildren(self, unused_type):
        return []

    def isVisible(self):
        return True


class _DialogButton:
    def __init__(self, name, text):
        self._name = name
        self._text = text
        self.clicked = False

    def objectName(self):
        return self._name

    def text(self):
        return self._text

    def isEnabled(self):
        return True

    def isVisible(self):
        return True

    def isCheckable(self):
        return False

    def isChecked(self):
        return False

    def click(self):
        self.clicked = True


def test_modal_actions_are_stable_and_invokable():
    dialog = _Dialog()
    buttons = [
        _DialogButton("qtRtxScenePreparationMoreButton", "More"),
        _DialogButton("qtRtxScenePreparationCancelButton", "Cancel"),
        _DialogButton("qtRtxScenePreparationOkButton", "OK"),
    ]
    original_visible_dialogs = diagnostics._visible_dialogs
    original_dialog_buttons = diagnostics._dialog_buttons
    diagnostics._visible_dialogs = lambda: [dialog]
    diagnostics._dialog_buttons = lambda unused_dialog: buttons
    try:
        result = diagnostics.get_modal_dialogs({})
        assert result["dialogs"][0]["dialog_id"] == "qtRtxScenePreparationDialog"
        actions = diagnostics.get_dialog_actions(
            {"dialog_id": "qtRtxScenePreparationDialog"}
        )
        assert [item["action_id"] for item in actions["actions"]] == [
            "qtRtxScenePreparationMoreButton",
            "qtRtxScenePreparationCancelButton",
            "qtRtxScenePreparationOkButton",
        ]
        invoked = diagnostics.invoke_dialog_action(
            {
                "dialog_id": "qtRtxScenePreparationDialog",
                "action_id": "qtRtxScenePreparationOkButton",
            }
        )
    finally:
        diagnostics._visible_dialogs = original_visible_dialogs
        diagnostics._dialog_buttons = original_dialog_buttons

    assert invoked["invoked"] is True
    assert buttons[2].clicked is True


def test_license_state_reports_unavailable_entitlements_truthfully():
    diagnostics.RLPy.RApplication = types.SimpleNamespace(
        GetProductEdition=lambda: "Test Edition"
    )
    result = diagnostics.get_license_state({})
    assert result["product_edition"] == "Test Edition"
    assert result["entitlement_type"] == "unknown"
    assert result["unavailable"] is True
    assert "does not expose" in result["unavailable_reason"]


def test_debug_view_catalog_matches_rtx_indices_64_to_69():
    import iclone_mcp_tool_render as render

    render.RLPy = types.SimpleNamespace(
        RStatus=types.SimpleNamespace(Success="success"),
        ERenderSystem_DX11=11,
        ERenderSystem_DX12=12,
        RScene=types.SimpleNamespace(
            GetPathtracerDebugView=lambda: 64,
            SetPathtracerDebugView=lambda value: "success",
        ),
    )
    catalog = render.get_pathtracer_debug_views({})
    assert catalog["count"] == 70
    assert [item["name"] for item in catalog["views"][64:70]] == [
        "OnlyCoat",
        "OnlySheen",
        "OnlyEmissive",
        "OnlyTransmission",
        "OnlySSS",
        "Specular",
    ]
    assert render.set_pathtracer_debug_view({"index": 64})["name"] == "OnlyCoat"
    unsupported = next(item for item in catalog["views"] if item["name"] == "RTXShadowPass")
    assert unsupported["supported"] is False
    assert unsupported["reason"]


def test_render_system_transition_can_be_cancelled_before_switch():
    import iclone_mcp_tool_render as render

    callbacks = []
    switches = []

    class _Timer:
        @staticmethod
        def singleShot(unused_delay, callback):
            callbacks.append(callback)

    render.RLPy = types.SimpleNamespace(
        RStatus=types.SimpleNamespace(Success="success"),
        ERenderSystem_DX11=11,
        ERenderSystem_DX12=12,
        RGlobal=types.SimpleNamespace(
            GetRenderSystem=lambda: 11,
            SwitchRenderSystem=lambda value: switches.append(value) or "success",
        ),
    )
    original_jobs = render._TRANSITION_JOBS
    original_sequence = render._TRANSITION_SEQUENCE
    render._TRANSITION_JOBS = {}
    render._TRANSITION_SEQUENCE = 0
    pyside = sys.modules["PySide2"]
    original_qtcore = getattr(pyside, "QtCore", None)
    pyside.QtCore = types.SimpleNamespace(QTimer=_Timer)
    try:
        started = render.start_render_system_transition({"system": "dx12"})
        assert started["state"] == "queued"
        cancelled = render.cancel_render_system_transition({"job_id": started["job_id"]})
        assert cancelled["state"] == "cancelled"
        callbacks[0]()
    finally:
        render._TRANSITION_JOBS = original_jobs
        render._TRANSITION_SEQUENCE = original_sequence
        if original_qtcore is None:
            delattr(pyside, "QtCore")
        else:
            pyside.QtCore = original_qtcore

    assert switches == []
