from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .model import KeymapperModel
from .runtime_identity import host_token_to_sdl_scancode, sdl_scancode_to_host_token

try:
    from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
    from PySide6.QtGui import QAction, QColor, QKeyEvent, QPainter, QPalette, QPen, QPixmap, QTransform
    from PySide6.QtWidgets import (
        QAbstractSpinBox,
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFormLayout,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsView,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMenu,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QScrollArea,
        QSpinBox,
        QSplitter,
        QSlider,
        QSizePolicy,
        QStatusBar,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "PySide6 is required for keymapper UI. Install with: uv pip install PySide6"
    ) from exc


def _qt_key_to_host_key(event: QKeyEvent) -> Optional[str]:
    sc = int(event.nativeScanCode() or 0)
    key = event.key()
    # For alphanumerics, prefer Qt's logical key value. On some stacks the
    # reported native scancode can be offset/translated in ways that would map
    # digits to unrelated tokens (e.g. BACKSPACE/F-keys), which then makes the
    # UI select the wrong binding/matrix entry.
    if Qt.Key_A <= key <= Qt.Key_Z:
        return chr(ord("A") + (key - Qt.Key_A))
    if Qt.Key_0 <= key <= Qt.Key_9:
        return str(key - Qt.Key_0)

    x11_sc_map = {
        9: "ESCAPE",
        10: "1",
        11: "2",
        12: "3",
        13: "4",
        14: "5",
        15: "6",
        16: "7",
        17: "8",
        18: "9",
        19: "0",
        20: "MINUS",
        21: "EQUALS",
        22: "BACKSPACE",
        23: "TAB",
        24: "Q",
        25: "W",
        26: "E",
        27: "R",
        28: "T",
        29: "Y",
        30: "U",
        31: "I",
        32: "O",
        33: "P",
        34: "LEFTBRACKET",
        35: "RIGHTBRACKET",
        36: "RETURN",
        37: "LCTRL",
        38: "A",
        39: "S",
        40: "D",
        41: "F",
        42: "G",
        43: "H",
        44: "J",
        45: "K",
        46: "L",
        47: "SEMICOLON",
        48: "APOSTROPHE",
        49: "GRAVE",
        50: "LSHIFT",
        51: "BACKSLASH",
        52: "Z",
        53: "X",
        54: "C",
        55: "V",
        56: "B",
        57: "N",
        58: "M",
        59: "COMMA",
        60: "PERIOD",
        61: "SLASH",
        62: "RSHIFT",
        64: "LALT",
        65: "SPACE",
        66: "CAPSLOCK",
        67: "F1",
        68: "F2",
        69: "F3",
        70: "F4",
        71: "F5",
        72: "F6",
        73: "F7",
        74: "F8",
        75: "F9",
        76: "F10",
        79: "KP_7",
        80: "KP_8",
        81: "KP_9",
        82: "KP_MINUS",
        83: "KP_4",
        84: "KP_5",
        85: "KP_6",
        86: "KP_PLUS",
        87: "KP_1",
        88: "KP_2",
        89: "KP_3",
        90: "KP_0",
        91: "KP_PERIOD",
        94: "NONUSBACKSLASH",
        104: "KP_ENTER",
        105: "RCTRL",
        107: "PRINTSCREEN",
        108: "RALT",
        110: "HOME",
        111: "UP",
        112: "PAGEUP",
        113: "LEFT",
        114: "RIGHT",
        115: "END",
        116: "DOWN",
        117: "PAGEDOWN",
        118: "INSERT",
        119: "DELETE",
    }
    pc_sc_map = {
        1: "ESCAPE",
        2: "1",
        3: "2",
        4: "3",
        5: "4",
        6: "5",
        7: "6",
        8: "7",
        9: "8",
        10: "9",
        11: "0",
        12: "MINUS",
        13: "EQUALS",
        14: "BACKSPACE",
        15: "TAB",
        16: "Q",
        17: "W",
        18: "E",
        19: "R",
        20: "T",
        21: "Y",
        22: "U",
        23: "I",
        24: "O",
        25: "P",
        26: "LEFTBRACKET",
        27: "RIGHTBRACKET",
        28: "RETURN",
        29: "LCTRL",
        30: "A",
        31: "S",
        32: "D",
        33: "F",
        34: "G",
        35: "H",
        36: "J",
        37: "K",
        38: "L",
        39: "SEMICOLON",
        40: "APOSTROPHE",
        41: "GRAVE",
        42: "LSHIFT",
        43: "BACKSLASH",
        44: "Z",
        45: "X",
        46: "C",
        47: "V",
        48: "B",
        49: "N",
        50: "M",
        51: "COMMA",
        52: "PERIOD",
        53: "SLASH",
        54: "RSHIFT",
        56: "LALT",
        57: "SPACE",
        58: "CAPSLOCK",
        59: "F1",
        60: "F2",
        61: "F3",
        62: "F4",
        63: "F5",
        64: "F6",
        65: "F7",
        66: "F8",
        67: "F9",
        68: "F10",
        79: "KP_1",
        80: "KP_2",
        81: "KP_3",
        82: "KP_0",
        83: "KP_PERIOD",
        96: "KP_ENTER",
        97: "RCTRL",
        100: "RALT",
        102: "HOME",
        103: "UP",
        104: "PAGEUP",
        105: "LEFT",
        106: "RIGHT",
        107: "END",
        108: "DOWN",
        109: "PAGEDOWN",
        110: "INSERT",
        111: "DELETE",
        119: "PAUSE",
    }
    # Primary path: resolve by raw native scancode so UI and emulator use the
    # same physical key identity independent of layout/text composition.
    if sys.platform.startswith("linux"):
        for cand in (
            x11_sc_map.get(sc),
            pc_sc_map.get(sc),
            pc_sc_map.get(sc - 8),
            x11_sc_map.get(sc + 8),
        ):
            if cand:
                return cand
    else:
        cand = pc_sc_map.get(sc)
        if cand:
            return cand

    # Some layouts emit dead-key symbols for the physical 6 key (e.g. Shift+6).
    # If scancode mapping above could not resolve, fall back to host "6".
    dead_diaeresis = getattr(Qt, "Key_Dead_Diaeresis", None)
    dead_circumflex = getattr(Qt, "Key_Dead_Circumflex", None)
    if (dead_diaeresis is not None and key == dead_diaeresis) or (
        dead_circumflex is not None and key == dead_circumflex
    ):
        return "6"

    # Distinguish left/right modifier keys when the platform reports side info.
    # Fallback remains left-side for compatibility.
    if key == Qt.Key_Shift:
        sc = int(event.nativeScanCode() or 0)
        vk = int(event.nativeVirtualKey() or 0)
        if vk == 0xA1 or sc in (54, 62):
            return "RSHIFT"
        return "LSHIFT"
    if key == Qt.Key_Control:
        sc = int(event.nativeScanCode() or 0)
        vk = int(event.nativeVirtualKey() or 0)
        if vk == 0xA3 or sc in (97,):
            return "RCTRL"
        return "LCTRL"
    if key == Qt.Key_Alt:
        sc = int(event.nativeScanCode() or 0)
        vk = int(event.nativeVirtualKey() or 0)
        if vk == 0xA5 or sc in (100,):
            return "RALT"
        return "LALT"
    if key == Qt.Key_AltGr:
        return "RALT"

    special = {
        Qt.Key_Escape: "ESCAPE",
        Qt.Key_Tab: "TAB",
        Qt.Key_Backspace: "BACKSPACE",
        Qt.Key_Return: "RETURN",
        Qt.Key_Enter: "KP_ENTER",
        Qt.Key_Space: "SPACE",
        Qt.Key_Minus: "MINUS",
        Qt.Key_Equal: "EQUALS",
        Qt.Key_BracketLeft: "LEFTBRACKET",
        Qt.Key_BracketRight: "RIGHTBRACKET",
        Qt.Key_Backslash: "BACKSLASH",
        Qt.Key_Semicolon: "SEMICOLON",
        Qt.Key_Colon: "NONUSBACKSLASH",
        Qt.Key_Apostrophe: "APOSTROPHE",
        Qt.Key_Asterisk: "NONUSBACKSLASH",
        Qt.Key_Comma: "COMMA",
        Qt.Key_Period: "PERIOD",
        Qt.Key_Slash: "SLASH",
        Qt.Key_QuoteLeft: "GRAVE",
        Qt.Key_Left: "LEFT",
        Qt.Key_Right: "RIGHT",
        Qt.Key_Up: "UP",
        Qt.Key_Down: "DOWN",
        Qt.Key_Home: "HOME",
        Qt.Key_End: "END",
        Qt.Key_Delete: "DELETE",
        Qt.Key_Print: "PRINTSCREEN",
        Qt.Key_SysReq: "SYSREQ",
        Qt.Key_CapsLock: "CAPSLOCK",
        Qt.Key_F1: "F1",
        Qt.Key_F2: "F2",
        Qt.Key_F3: "F3",
        Qt.Key_F4: "F4",
        Qt.Key_F5: "F5",
        Qt.Key_F6: "F6",
        Qt.Key_F7: "F7",
        Qt.Key_F8: "F8",
        Qt.Key_F9: "F9",
    }
    # Locale/layout variants that should still map to host physical keys.
    if key in (Qt.Key_Question,):
        return "SLASH"
    if key in (Qt.Key_AsciiTilde,):
        return "GRAVE"
    if key in (Qt.Key_QuoteDbl,):
        return "APOSTROPHE"
    ccedilla_key = getattr(Qt, "Key_Ccedilla", None)
    if ccedilla_key is not None and key == ccedilla_key:
        return "NONUSBACKSLASH"
    dead_tilde = getattr(Qt, "Key_Dead_Tilde", None)
    if dead_tilde is not None and key == dead_tilde:
        return "GRAVE"
    dead_grave = getattr(Qt, "Key_Dead_Grave", None)
    if dead_grave is not None and key == dead_grave:
        return "GRAVE"
    dead_acute = getattr(Qt, "Key_Dead_Acute", None)
    if dead_acute is not None and key == dead_acute:
        return "APOSTROPHE"
    acute = getattr(Qt, "Key_Acute", None)
    if acute is not None and key == acute:
        return "APOSTROPHE"
    if key in special:
        return special[key]

    keypad = {
        Qt.KeypadModifier: None,
    }
    if event.modifiers() & Qt.KeypadModifier:
        k = {
            Qt.Key_0: "KP_0",
            Qt.Key_1: "KP_1",
            Qt.Key_2: "KP_2",
            Qt.Key_3: "KP_3",
            Qt.Key_4: "KP_4",
            Qt.Key_5: "KP_5",
            Qt.Key_6: "KP_6",
            Qt.Key_7: "KP_7",
            Qt.Key_8: "KP_8",
            Qt.Key_9: "KP_9",
            Qt.Key_Period: "KP_PERIOD",
        }.get(key)
        if k:
            return k

    _ = keypad
    return None


def _qt_event_host_candidates(event: QKeyEvent) -> List[str]:
    out: List[str] = []
    # Primary: use our canonical host token resolution (based on native scancode
    # mapping tables + Qt key fallbacks). Do not treat Qt nativeScanCode as an
    # SDL scancode; that caused wrong tokens (notably digits on X11).
    primary = _qt_key_to_host_key(event)
    if primary:
        out.append(primary)
    text = event.text() or ""
    # For digits, prefer the produced text when available; this helps when some
    # platforms/layout stacks report a surprising key() or native scancode for
    # number row / keypad digits.
    if len(text) == 1 and text.isdigit():
        if text not in out:
            out.append(text)
    # Text-based fallback helps when Qt key identity drifts (e.g. ABNT2 Intl1
    # key reported as a modifier by some stacks). Keep physical-intent first.
    text_map = {
        "/": ["INTERNATIONAL1", "SLASH"],
        "?": ["INTERNATIONAL1", "SLASH"],
        ";": ["SEMICOLON"],
        ":": ["SEMICOLON"],
        "'": ["APOSTROPHE"],
        "\"": ["APOSTROPHE"],
        "[": ["LEFTBRACKET"],
        "{": ["LEFTBRACKET"],
        "]": ["RIGHTBRACKET"],
        "}": ["RIGHTBRACKET"],
        "\\": ["BACKSLASH"],
        "|": ["BACKSLASH"],
        ",": ["COMMA"],
        "<": ["COMMA"],
        ".": ["PERIOD"],
        ">": ["PERIOD"],
        "-": ["MINUS"],
        "_": ["MINUS"],
        "=": ["EQUALS"],
        "+": ["EQUALS"],
        "`": ["GRAVE"],
        "~": ["GRAVE"],
    }
    for cand in text_map.get(text, []):
        if cand and cand not in out:
            out.append(cand)
    return out


def _sdl_scancode_to_host_token(sc: int) -> Optional[str]:
    return sdl_scancode_to_host_token(sc)


def _host_token_to_sdl_scancode(host_key: str) -> Optional[int]:
    return host_token_to_sdl_scancode(host_key)


class KeyboardGraphicsView(QGraphicsView):
    def __init__(self, owner: "MainWindow"):
        super().__init__()
        self.owner = owner
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        if self.owner.consume_image_eyedropper_click(scene_pos, event.button()):
            event.accept()
            return
        # Let key-box item handlers own selection; all other clicks are treated
        # as canvas clicks (including image/background areas) so selection can clear.
        item = self.itemAt(event.position().toPoint())
        if not isinstance(item, MapperRectItem):
            self.owner.select_key_at(scene_pos, event.modifiers())
        super().mousePressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.owner.schedule_fit_scene_to_view()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        factor = 1.15 if delta > 0 else (1.0 / 1.15)
        self.owner.adjust_zoom_by_factor(factor)
        event.accept()

    def contextMenuEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        self.owner.show_canvas_context_menu(event.globalPos(), scene_pos)
        event.accept()


class MapperRectItem(QGraphicsRectItem):
    HANDLE_SIZE = 10.0

    def __init__(self, owner: "MainWindow", key_id: str, rect: QRectF):
        super().__init__(rect)
        self.owner = owner
        self.key_id = key_id
        self._mode: Optional[str] = None
        self._drag_start_scene = QPointF()
        self._start_rect = QRectF()
        self._group_start_rects: Dict[str, QRectF] = {}
        self.setAcceptHoverEvents(True)

    def _is_in_resize_handle(self, local_pos: QPointF) -> bool:
        r = self.rect()
        handle = QRectF(
            r.right() - self.HANDLE_SIZE,
            r.bottom() - self.HANDLE_SIZE,
            self.HANDLE_SIZE,
            self.HANDLE_SIZE,
        )
        return handle.contains(local_pos)

    def hoverMoveEvent(self, event):
        if self._is_in_resize_handle(event.pos()):
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            self.setCursor(Qt.SizeAllCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            mods = event.modifiers()
            preserve_multi = (
                not bool(mods & (Qt.ControlModifier | Qt.ShiftModifier))
                and self.key_id in self.owner.selected_mapper_key_ids
                and len(self.owner.selected_mapper_key_ids) > 1
            )
            if preserve_multi:
                self.owner.selected_mapper_key_id = self.key_id
                self.owner._load_selected_key_fields(self.key_id)
                self.owner._refresh_alias_bindings()
            else:
                self.owner.select_mapper_key(self.key_id, mods)
            self.owner._begin_bbox_interaction()
            self._drag_start_scene = event.scenePos()
            self._start_rect = QRectF(self.rect())
            self._mode = "resize" if self._is_in_resize_handle(event.pos()) else "move"
            self._group_start_rects = {}
            if self._mode == "move":
                selected_ids = set(self.owner.selected_mapper_key_ids)
                if self.key_id in selected_ids and len(selected_ids) > 1:
                    for sid in selected_ids:
                        item = self.owner.rect_items.get(sid)
                        if item is not None:
                            self._group_start_rects[sid] = QRectF(item.rect())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._mode in ("move", "resize"):
            self.owner._auto_scroll_view_for_scene_pos(event.scenePos())
            delta = event.scenePos() - self._drag_start_scene
            if self._mode == "move":
                if self._group_start_rects:
                    for sid, sr in self._group_start_rects.items():
                        item = self.owner.rect_items.get(sid)
                        if item is None:
                            continue
                        nr = QRectF(
                            sr.x() + delta.x(),
                            sr.y() + delta.y(),
                            sr.width(),
                            sr.height(),
                        )
                        item.setRect(nr)
                        try:
                            self.owner.model.set_mapper_bbox(
                                sid,
                                int(round(nr.x())),
                                int(round(nr.y())),
                                max(1, int(round(nr.width()))),
                                max(1, int(round(nr.height()))),
                            )
                        except Exception:
                            continue
                    active = self.owner.rect_items.get(self.key_id)
                    if active is not None:
                        ar = active.rect()
                        self.owner.bbox_x.setValue(int(round(ar.x())))
                        self.owner.bbox_y.setValue(int(round(ar.y())))
                        self.owner.bbox_w.setValue(max(1, int(round(ar.width()))))
                        self.owner.bbox_h.setValue(max(1, int(round(ar.height()))))
                    event.accept()
                    return
                nr = QRectF(
                    self._start_rect.x() + delta.x(),
                    self._start_rect.y() + delta.y(),
                    self._start_rect.width(),
                    self._start_rect.height(),
                )
            else:
                nw = max(1.0, self._start_rect.width() + delta.x())
                nh = max(1.0, self._start_rect.height() + delta.y())
                nr = QRectF(
                    self._start_rect.x(),
                    self._start_rect.y(),
                    nw,
                    nh,
                )
            self.setRect(nr)
            self.owner._live_bbox_from_item(self.key_id, nr)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._mode in ("move", "resize"):
            if self._group_start_rects and self._mode == "move":
                self.owner._bbox_interaction_active = False
                self.owner.refresh_canvas()
                self.owner.statusBar().showMessage(
                    f"Moved {len(self._group_start_rects)} boxes",
                    1500,
                )
            else:
                r = self.rect()
                self.owner._commit_bbox_from_item(self.key_id, r)
            self._group_start_rects = {}
            self._mode = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        r = self.rect()
        painter.setPen(QPen(QColor(20, 20, 20, 220), 1))
        painter.setBrush(QColor(240, 240, 240, 220))
        painter.drawRect(
            QRectF(
                r.right() - self.HANDLE_SIZE,
                r.bottom() - self.HANDLE_SIZE,
                self.HANDLE_SIZE,
                self.HANDLE_SIZE,
            )
        )


class MainWindow(QMainWindow):
    def __init__(self, model: KeymapperModel):
        super().__init__()
        self.model = model
        self.undo_stack: List = []
        self.redo_stack: List = []
        self.selected_mapper_key_id: Optional[str] = None
        self.selected_mapper_key_ids: set[str] = set()
        self.selected_host_key: Optional[str] = None
        self.selected_alias_host_key: Optional[str] = None
        self.pending_alias_capture_mapper_key_id: Optional[str] = None
        self.selected_system_key_id: Optional[str] = None
        self.edit_mode = False
        self.pressed_mapper_key_ids: set[str] = set()
        self.pressed_system_key_ids: set[str] = set()
        self.manual_zoom = False
        self._bbox_interaction_active = False
        self._image_eyedropper_active = False
        self._image_pixmap: Optional[QPixmap] = None
        self.zoom_percent = 100
        self._zoom_signal_guard = False
        self._base_transform: Optional[QTransform] = None
        self._fit_scheduled = False
        self._keyboard_inspector_enabled = True

        self.scene = QGraphicsScene(self)
        self.view = KeyboardGraphicsView(self)
        self.view.setScene(self.scene)
        self.view.setRenderHint(QPainter.SmoothPixmapTransform, True)

        self.rect_items: Dict[str, QGraphicsRectItem] = {}
        self.add_alias_btn: Optional[QPushButton] = None

        self.bindings_list = QListWidget()
        self.bindings_list.currentItemChanged.connect(self._on_binding_item_changed)
        self.alias_bindings_list = QListWidget()
        self.alias_bindings_list.currentItemChanged.connect(self._on_alias_binding_item_changed)
        self.system_keys_list = QListWidget()
        self.system_keys_list.currentItemChanged.connect(self._on_system_key_selected)

        self.key_id_label = QLabel("-")
        self.legend_edit = QLineEdit()
        self.bbox_x = QSpinBox(); self.bbox_x.setRange(0, 10000)
        self.bbox_y = QSpinBox(); self.bbox_y.setRange(0, 10000)
        self.bbox_w = QSpinBox(); self.bbox_w.setRange(1, 10000)
        self.bbox_h = QSpinBox(); self.bbox_h.setRange(1, 10000)
        self.color_r = QSpinBox(); self.color_r.setRange(0, 255)
        self.color_g = QSpinBox(); self.color_g.setRange(0, 255)
        self.color_b = QSpinBox(); self.color_b.setRange(0, 255)
        self.pick_color_btn = QPushButton("Pick Color")
        self.pick_color_btn.clicked.connect(self._pick_overlay_color)
        self.system_key_id_edit = QLineEdit()
        self.system_key_id_edit.textChanged.connect(self._update_system_key_action_enabled_state)
        self.system_key_feedback_checkbox = QCheckBox("Visual feedback")
        self.system_key_feedback_checkbox.stateChanged.connect(self._on_system_key_feedback_toggled)
        self._system_key_signal_guard = False
        # Use -1 as "N/A" so multi-press bindings don't misleadingly show presses[0].
        self.row_spin = QSpinBox(); self.row_spin.setRange(-1, 31)
        self.row_spin.setSpecialValueText("-")
        self.bit_spin = QSpinBox(); self.bit_spin.setRange(-1, 7)
        self.bit_spin.setSpecialValueText("-")
        self.matrix_presses_edit = QLineEdit()
        self.matrix_presses_edit.setReadOnly(True)
        self.matrix_presses_edit.setPlaceholderText("rX/bY (+ rX/bY ...)")
        self.edit_matrix_presses_btn = QPushButton("Edit Presses...")
        self.edit_matrix_presses_btn.clicked.connect(self._edit_matrix_presses_dialog)
        self.ascii_edit = QLineEdit()
        self.ascii_shift_edit = QLineEdit()
        self.ascii_ctrl_edit = QLineEdit()
        self.target_kind_combo = QComboBox()
        self.target_kind_combo.addItems(["mapper", "emulator", "system"])
        self.target_kind_combo.currentTextChanged.connect(self._on_target_kind_changed)
        self.target_id_combo = QComboBox()
        self.target_id_combo.setEditable(True)
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(25, 400)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(220)
        self.zoom_slider.valueChanged.connect(self._on_zoom_slider_changed)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(52)
        self.edit_mode_checkbox = QCheckBox("Edit mode (click key + press host key)")
        self.edit_mode_checkbox.stateChanged.connect(self._toggle_edit_mode)

        self._build_layout()
        self._build_menu()
        self._wire_auto_apply()
        self.setStatusBar(QStatusBar())
        self._update_window_title()

        self.refresh_all()
        self._saved_mapper_state = copy.deepcopy(self.model.mapper)
        self._saved_host_map_state = copy.deepcopy(self.model.host_map)
        QApplication.instance().installEventFilter(self)

    def _build_layout(self):
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        grp_bindings = QGroupBox("Host Bindings")
        gb_layout = QVBoxLayout(grp_bindings)
        gb_layout.addWidget(self.bindings_list)
        right_layout.addWidget(grp_bindings)

        grp_aliases = QGroupBox("Bindings for Selected Key")
        ga_layout = QVBoxLayout(grp_aliases)
        ga_layout.addWidget(self.alias_bindings_list)
        alias_buttons = QWidget()
        alias_buttons_layout = QHBoxLayout(alias_buttons)
        alias_buttons_layout.setContentsMargins(0, 0, 0, 0)
        add_alias_btn = QPushButton("Add Host Alias")
        self.add_alias_btn = add_alias_btn
        add_alias_btn.clicked.connect(self._add_alias_dialog)
        remove_alias_btn = QPushButton("Remove Selected Alias")
        remove_alias_btn.clicked.connect(self._remove_selected_alias)
        alias_buttons_layout.addWidget(add_alias_btn)
        alias_buttons_layout.addWidget(remove_alias_btn)
        ga_layout.addWidget(alias_buttons)
        right_layout.addWidget(grp_aliases)

        grp_system_keys = QGroupBox("System Keys")
        gsys_layout = QVBoxLayout(grp_system_keys)
        gsys_layout.addWidget(self.system_keys_list)
        gsys_controls = QWidget()
        gsys_controls_layout = QFormLayout(gsys_controls)
        gsys_controls_layout.setContentsMargins(0, 0, 0, 0)
        gsys_controls_layout.addRow("System key id", self.system_key_id_edit)
        gsys_controls_layout.addRow("", self.system_key_feedback_checkbox)
        gsys_btns = QWidget()
        gsys_btns_layout = QHBoxLayout(gsys_btns)
        gsys_btns_layout.setContentsMargins(0, 0, 0, 0)
        add_system_key_btn = QPushButton("Add/Update")
        add_system_key_btn.clicked.connect(self._add_or_update_system_key)
        self.create_system_bbox_btn = QPushButton("Create BBox")
        self.create_system_bbox_btn.clicked.connect(self._create_bbox_for_selected_system_key)
        remove_system_key_btn = QPushButton("Remove Selected")
        remove_system_key_btn.clicked.connect(self._remove_selected_system_key)
        gsys_btns_layout.addWidget(add_system_key_btn)
        gsys_btns_layout.addWidget(self.create_system_bbox_btn)
        gsys_btns_layout.addWidget(remove_system_key_btn)
        gsys_controls_layout.addRow(gsys_btns)
        gsys_layout.addWidget(gsys_controls)
        right_layout.addWidget(grp_system_keys)

        grp_selection = QGroupBox("Selection")
        gs_layout = QFormLayout(grp_selection)
        gs_layout.addRow("Mapper key", self.key_id_label)
        gs_layout.addRow("Legends (comma)", self.legend_edit)
        gs_layout.addRow("BBox X", self.bbox_x)
        gs_layout.addRow("BBox Y", self.bbox_y)
        gs_layout.addRow("BBox W", self.bbox_w)
        gs_layout.addRow("BBox H", self.bbox_h)
        gs_layout.addRow("Overlay R", self.color_r)
        gs_layout.addRow("Overlay G", self.color_g)
        gs_layout.addRow("Overlay B", self.color_b)
        gs_layout.addRow(self.pick_color_btn)
        self.apply_key_fields_btn = QPushButton("Apply key fields")
        self.apply_key_fields_btn.clicked.connect(self._apply_key_fields)
        gs_layout.addRow(self.apply_key_fields_btn)
        right_layout.addWidget(grp_selection)

        grp_mapping = QGroupBox("Mapping Key Definition")
        gm_layout = QFormLayout(grp_mapping)
        gm_layout.addRow("Target kind", self.target_kind_combo)
        gm_layout.addRow("Target id", self.target_id_combo)
        apply_target = QPushButton("Set Target For Selected Host")
        apply_target.clicked.connect(self._apply_binding_target)
        gm_layout.addRow(apply_target)
        gm_layout.addRow("Matrix row", self.row_spin)
        gm_layout.addRow("Matrix bit", self.bit_spin)
        gm_layout.addRow("Matrix presses", self.matrix_presses_edit)
        gm_layout.addRow("", self.edit_matrix_presses_btn)
        apply_matrix = QPushButton("Set Matrix For Selected Host")
        apply_matrix.clicked.connect(self._apply_matrix)
        gm_layout.addRow(apply_matrix)
        gm_layout.addRow("ASCII", self.ascii_edit)
        gm_layout.addRow("ASCII Shift", self.ascii_shift_edit)
        gm_layout.addRow("ASCII Ctrl", self.ascii_ctrl_edit)
        apply_ascii = QPushButton("Set ASCII For Selected Host")
        apply_ascii.clicked.connect(self._apply_ascii)
        gm_layout.addRow(apply_ascii)
        right_layout.addWidget(grp_mapping)

        right_layout.addWidget(self.edit_mode_checkbox)

        main = QWidget()
        main_layout = QHBoxLayout(main)
        splitter = QSplitter()
        image_pane = QWidget()
        image_pane.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        image_pane_layout = QVBoxLayout(image_pane)
        image_pane_layout.setContentsMargins(0, 0, 0, 0)
        image_pane_layout.addWidget(self.view)
        zoom_bar = QWidget()
        zoom_bar_layout = QHBoxLayout(zoom_bar)
        zoom_bar_layout.setContentsMargins(8, 2, 8, 2)
        zoom_bar_layout.addStretch(1)
        zoom_bar_layout.addWidget(QLabel("Zoom"))
        zoom_bar_layout.addWidget(self.zoom_slider)
        zoom_bar_layout.addWidget(self.zoom_label)
        image_pane_layout.addWidget(zoom_bar)
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_scroll.setWidget(right_panel)
        splitter.addWidget(image_pane)
        splitter.addWidget(right_scroll)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter)
        self.setCentralWidget(main)

    @staticmethod
    def _presses_as_text(presses: object) -> str:
        if not isinstance(presses, list) or not presses:
            return ""
        parts: List[str] = []
        for p in presses:
            if not isinstance(p, dict):
                continue
            parts.append(f"r{int(p.get('row', 0))}/b{int(p.get('bit', 0))}")
        return " + ".join(parts)

    def _binding_payload_detail(self, binding: dict) -> str:
        presses = binding.get("presses")
        if isinstance(presses, list) and presses:
            return self._presses_as_text(presses)
        if any(k in binding for k in ("ascii", "ascii_shift", "ascii_ctrl")):
            return "ascii"
        mid = self.model.binding_mapper_key_id(binding)
        eid = str(binding.get("emulator_key_id", "")).strip()
        sid = str(binding.get("system_key_id", "")).strip()
        if mid:
            return "mapper target (no payload)"
        if eid:
            return f"emulator:{eid}"
        if sid:
            return f"system:{sid}"
        return "unmapped"

    def _set_alias_capture_ui(self, active: bool):
        btn = self.add_alias_btn
        if btn is None:
            return
        if active and self.pending_alias_capture_mapper_key_id:
            btn.setText(f"Waiting Key ({self.pending_alias_capture_mapper_key_id})")
            btn.setStyleSheet("QPushButton { background-color: #7a5a00; border: 1px solid #c59a2a; }")
            self.view.viewport().setCursor(Qt.IBeamCursor)
        else:
            btn.setText("Add Host Alias")
            btn.setStyleSheet("")
            if not self._image_eyedropper_active:
                self.view.viewport().unsetCursor()

    def _build_menu(self):
        menu = self.menuBar()
        file_menu = menu.addMenu("File")
        act_restore = QAction("Restore", self)
        act_restore.triggered.connect(self.restore)
        act_save_mapper = QAction("Save Mapper", self)
        act_save_mapper.setShortcut("Ctrl+B")
        act_save_mapper.triggered.connect(self.save_mapper)
        act_save_mapping = QAction("Save Mapping", self)
        act_save_mapping.setShortcut("Ctrl+S")
        act_save_mapping.triggered.connect(self.save_mapping)
        act_change_image = QAction("Change Image", self)
        act_change_image.triggered.connect(self.change_image)
        act_exit = QAction("Exit", self)
        act_exit.setShortcut("Ctrl+Q")
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_restore)
        file_menu.addAction(act_save_mapper)
        file_menu.addAction(act_save_mapping)
        file_menu.addAction(act_change_image)
        file_menu.addSeparator()
        file_menu.addAction(act_exit)

        edit_menu = menu.addMenu("Edit")
        act_undo = QAction("Undo", self)
        act_undo.triggered.connect(self.undo)
        act_redo = QAction("Redo", self)
        act_redo.triggered.connect(self.redo)
        act_mapper_fields = QAction("Adjust Mapper Fields", self)
        act_mapper_fields.triggered.connect(self.adjust_mapper_fields)
        act_fit = QAction("Fit to View", self)
        act_fit.setShortcut("Ctrl+0")
        act_fit.triggered.connect(self.reset_zoom_to_fit)
        self.act_keyboard_inspector = QAction("Keyboard Event Inspector", self)
        self.act_keyboard_inspector.setCheckable(True)
        self.act_keyboard_inspector.setChecked(self._keyboard_inspector_enabled)
        self.act_keyboard_inspector.toggled.connect(self._set_keyboard_inspector_enabled)
        edit_menu.addAction(act_undo)
        edit_menu.addAction(act_redo)
        edit_menu.addAction(act_mapper_fields)
        edit_menu.addAction(act_fit)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_keyboard_inspector)

    def _set_keyboard_inspector_enabled(self, enabled: bool):
        self._keyboard_inspector_enabled = bool(enabled)
        state = "enabled" if self._keyboard_inspector_enabled else "disabled"
        self.statusBar().showMessage(f"Keyboard event inspector {state}", 1800)

    def _event_modifiers_text(self, modifiers: Qt.KeyboardModifiers) -> str:
        names: List[str] = []
        if modifiers & Qt.ShiftModifier:
            names.append("Shift")
        if modifiers & Qt.ControlModifier:
            names.append("Ctrl")
        if modifiers & Qt.AltModifier:
            names.append("Alt")
        if modifiers & Qt.MetaModifier:
            names.append("Meta")
        if modifiers & Qt.KeypadModifier:
            names.append("Keypad")
        return "+".join(names) if names else "-"

    def _show_keyboard_event_debug(self, event: QKeyEvent, kind: str):
        if not self._keyboard_inspector_enabled:
            return
        txt = event.text() or ""
        txt_disp = txt.encode("unicode_escape").decode("ascii") if txt else "-"
        candidates = _qt_event_host_candidates(event)
        host_key = (candidates[0] if candidates else None) or _qt_key_to_host_key(event) or "-"
        sdl_sc = _host_token_to_sdl_scancode(host_key) if host_key != "-" else None
        vk = int(event.nativeVirtualKey() or 0)
        nsc = int(event.nativeScanCode() or 0)
        nmods = int(event.nativeModifiers() or 0)
        qt_key = int(event.key())
        mods = self._event_modifiers_text(event.modifiers())
        sdl_sc_text = str(sdl_sc) if sdl_sc is not None else "-"
        cand_txt = ",".join(candidates[:5]) if candidates else "-"
        self.statusBar().showMessage(
            f"KB {kind} host={host_key} cand=[{cand_txt}] scancode={sdl_sc_text} nsc={nsc} qt={qt_key} vk={vk} mods={mods} nmods=0x{nmods:x} text={txt_disp}"
        )

    def _wire_auto_apply(self):
        # Key fields
        self.legend_edit.returnPressed.connect(self._auto_apply_legend_field)
        self.bbox_x.editingFinished.connect(lambda: self._auto_apply_bbox_field("x"))
        self.bbox_y.editingFinished.connect(lambda: self._auto_apply_bbox_field("y"))
        self.bbox_w.editingFinished.connect(lambda: self._auto_apply_bbox_field("width"))
        self.bbox_h.editingFinished.connect(lambda: self._auto_apply_bbox_field("height"))
        self.color_r.editingFinished.connect(lambda: self._auto_apply_overlay_component(0))
        self.color_g.editingFinished.connect(lambda: self._auto_apply_overlay_component(1))
        self.color_b.editingFinished.connect(lambda: self._auto_apply_overlay_component(2))
        # Mapping fields
        self.row_spin.editingFinished.connect(self._auto_apply_matrix)
        self.bit_spin.editingFinished.connect(self._auto_apply_matrix)
        self.ascii_edit.returnPressed.connect(self._auto_apply_ascii)
        self.ascii_shift_edit.returnPressed.connect(self._auto_apply_ascii)
        self.ascii_ctrl_edit.returnPressed.connect(self._auto_apply_ascii)

    def _update_selection_field_enabled_state(self):
        has_selection = bool(self.selected_mapper_key_id or self.selected_mapper_key_ids)
        self.legend_edit.setEnabled(has_selection)
        self.bbox_x.setEnabled(has_selection)
        self.bbox_y.setEnabled(has_selection)
        self.bbox_w.setEnabled(has_selection)
        self.bbox_h.setEnabled(has_selection)
        self.color_r.setEnabled(has_selection)
        self.color_g.setEnabled(has_selection)
        self.color_b.setEnabled(has_selection)
        self.pick_color_btn.setEnabled(has_selection)
        self.apply_key_fields_btn.setEnabled(has_selection)

    def _refresh_system_keys(self):
        prev = self.selected_system_key_id
        self.system_keys_list.clear()
        self.selected_system_key_id = None
        for entry in self.model.host_system_keys():
            sid = str(entry.get("id", "")).strip()
            if not sid:
                continue
            vf = bool(entry.get("visual_feedback", False))
            item = QListWidgetItem(f"{sid} [{'on' if vf else 'off'}]")
            item.setData(Qt.UserRole, sid)
            self.system_keys_list.addItem(item)
        if prev:
            for i in range(self.system_keys_list.count()):
                it = self.system_keys_list.item(i)
                if not it:
                    continue
                if str(it.data(Qt.UserRole) or "") == prev:
                    self.system_keys_list.setCurrentRow(i)
                    break
        if self.system_keys_list.currentItem() is None:
            self._system_key_signal_guard = True
            self.system_key_id_edit.setText("")
            self.system_key_feedback_checkbox.setChecked(False)
            self._system_key_signal_guard = False

    def _on_system_key_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]):
        _ = previous
        sid = str(current.data(Qt.UserRole) or "").strip() if current else ""
        self.selected_system_key_id = sid or None
        self._system_key_signal_guard = True
        self.system_key_id_edit.setText(sid)
        self.system_key_feedback_checkbox.setChecked(self.model.system_key_visual_feedback(sid) if sid else False)
        self._system_key_signal_guard = False
        mid = self._mapper_key_id_for_system_key(sid) if sid else None
        if mid:
            self.selected_mapper_key_id = mid
            self.selected_mapper_key_ids = {mid}
            self._load_selected_key_fields(mid)
        else:
            self.selected_mapper_key_id = None
            self.selected_mapper_key_ids.clear()
            self.key_id_label.setText("-")
        self._update_system_key_action_enabled_state()
        self._refresh_alias_bindings()
        self._update_selection_field_enabled_state()
        self.refresh_canvas()

    def _normalized_system_key_id_input(self) -> str:
        raw = self.system_key_id_edit.text().strip()
        if not raw:
            return ""
        return raw.replace(" ", "_").upper()

    def _update_system_key_action_enabled_state(self):
        sid = self.selected_system_key_id or self._normalized_system_key_id_input()
        can_create = bool(sid) and sid not in self.model.mapper_key_ids()
        self.create_system_bbox_btn.setEnabled(can_create)

    def _add_or_update_system_key(self):
        sid = self._normalized_system_key_id_input()
        if not sid:
            QMessageBox.warning(self, "Invalid system key", "System key id cannot be empty.")
            return
        desired_vf = bool(self.system_key_feedback_checkbox.isChecked())
        prev_sid = self.selected_system_key_id
        if prev_sid and sid != prev_sid:
            self._push_undo()
            try:
                self.model.rename_host_system_key(prev_sid, sid)
                self.model.upsert_host_system_key(sid, desired_vf)
            except Exception as exc:
                QMessageBox.warning(self, "Rename failed", str(exc))
                return
            self.selected_system_key_id = sid
            self._refresh_system_keys()
            self._update_system_key_action_enabled_state()
            self._refresh_target_id_choices()
            self.refresh_bindings()
            self.refresh_canvas()
            self.statusBar().showMessage(f"System key renamed: {prev_sid} -> {sid}", 2200)
            return
        existing_vf = None
        for entry in self.model.host_system_keys():
            if str(entry.get("id", "")).strip() == sid:
                existing_vf = bool(entry.get("visual_feedback", False))
                break
        if existing_vf is not None and existing_vf == desired_vf:
            return
        self._push_undo()
        self.model.upsert_host_system_key(sid, desired_vf)
        self.selected_system_key_id = sid
        self._refresh_system_keys()
        self._update_system_key_action_enabled_state()
        self._refresh_target_id_choices()
        self.refresh_bindings()
        self.statusBar().showMessage(f"System key saved: {sid}", 2000)

    def _remove_selected_system_key(self):
        sid = self.selected_system_key_id or self._normalized_system_key_id_input()
        if not sid:
            QMessageBox.warning(self, "No system key selected", "Select a system key first.")
            return
        self._push_undo()
        if not self.model.remove_host_system_key(sid):
            QMessageBox.warning(self, "Remove failed", f"System key '{sid}' not found.")
            return
        if sid in self.pressed_system_key_ids:
            self.pressed_system_key_ids.discard(sid)
        self.selected_system_key_id = None
        self._refresh_system_keys()
        self._update_system_key_action_enabled_state()
        self._refresh_target_id_choices()
        self.refresh_bindings()
        self.refresh_canvas()
        self.statusBar().showMessage(f"System key removed: {sid}", 2000)

    def _default_bbox_for_new_key(self) -> Dict[str, int]:
        r = self.scene.sceneRect()
        w = 88
        h = 34
        if not r.isNull():
            cx = int(round(r.x() + (r.width() / 2.0)))
            cy = int(round(r.y() + (r.height() / 2.0)))
            x = max(0, cx - (w // 2))
            y = max(0, cy - (h // 2))
            return {"x": x, "y": y, "width": w, "height": h}
        return {"x": 0, "y": 0, "width": w, "height": h}

    def _create_mapper_key_for_system_key(self, sid: str) -> Optional[str]:
        kid = str(sid).strip()
        if not kid:
            return None
        if kid in self.model.mapper_key_ids():
            return kid
        keys = self.model.mapper.setdefault("keys", [])
        max_row = 0
        for k in keys:
            try:
                max_row = max(max_row, int(k.get("row", 0)))
            except Exception:
                continue
        bbox = self._default_bbox_for_new_key()
        new_key = {
            "id": kid,
            "section": "system",
            "row": max(1, max_row + 1),
            "column": 1,
            "multi_legend": False,
            "legend": [kid],
            "legend_combos": {kid: [kid]},
            "bbox": bbox,
        }
        keys.append(new_key)
        return kid

    def _create_bbox_for_selected_system_key(self):
        sid = self.selected_system_key_id or self._normalized_system_key_id_input()
        if not sid:
            QMessageBox.warning(self, "No system key", "Select or enter a system key first.")
            return
        if sid in self.model.mapper_key_ids():
            self.selected_mapper_key_id = sid
            self.selected_mapper_key_ids = {sid}
            self._load_selected_key_fields(sid)
            self._update_selection_field_enabled_state()
            self.refresh_canvas()
            self.statusBar().showMessage(f"BBox already exists for {sid}", 1500)
            return
        self._push_undo()
        created = self._create_mapper_key_for_system_key(sid)
        if not created:
            return
        self.selected_mapper_key_id = created
        self.selected_mapper_key_ids = {created}
        self._load_selected_key_fields(created)
        self._update_selection_field_enabled_state()
        self._update_system_key_action_enabled_state()
        self.refresh_canvas()
        self.statusBar().showMessage(f"Created bbox for system key: {created}", 2000)

    def _on_system_key_feedback_toggled(self, state: int):
        if self._system_key_signal_guard:
            return
        sid = self.selected_system_key_id
        if not sid:
            return
        _ = state
        desired = bool(self.system_key_feedback_checkbox.isChecked())
        current = self.model.system_key_visual_feedback(sid)
        if current == desired:
            return
        self._push_undo()
        self.model.upsert_host_system_key(sid, desired)
        self._refresh_system_keys()
        self._update_system_key_action_enabled_state()
        self._refresh_target_id_choices()
        self.refresh_bindings()
        self.refresh_canvas()
        self.statusBar().showMessage(f"System key feedback {'enabled' if desired else 'disabled'}: {sid}", 2000)

    def _auto_apply_key_fields(self):
        ids = self._selected_key_ids_in_order()
        if not ids:
            return
        legends = [x.strip() for x in self.legend_edit.text().split(",") if x.strip()]
        if not legends:
            return
        changed = False
        for key_id in ids:
            b = self.model.key_bbox(key_id)
            if not b:
                continue
            if (
                b["x"] != self.bbox_x.value()
                or b["y"] != self.bbox_y.value()
                or b["width"] != self.bbox_w.value()
                or b["height"] != self.bbox_h.value()
            ):
                changed = True
                break
            for key in self.model.mapper_keys():
                if str(key.get("id", "")) == key_id:
                    if [str(v) for v in key.get("legend", [])] != legends:
                        changed = True
                    break
            if changed:
                break
        if not changed:
            return
        self._push_undo()
        for key_id in ids:
            self.model.set_mapper_bbox(
                key_id,
                self.bbox_x.value(),
                self.bbox_y.value(),
                self.bbox_w.value(),
                self.bbox_h.value(),
            )
            self.model.set_mapper_legend(key_id, legends)
        self.refresh_canvas()
        self.statusBar().showMessage(f"Key fields applied to {len(ids)} key(s)", 1200)

    def _auto_apply_legend_field(self):
        ids = self._selected_key_ids_in_order()
        if not ids:
            return
        legends = [x.strip() for x in self.legend_edit.text().split(",") if x.strip()]
        if not legends:
            return
        changed = False
        for key_id in ids:
            for key in self.model.mapper_keys():
                if str(key.get("id", "")) == key_id:
                    if [str(v) for v in key.get("legend", [])] != legends:
                        changed = True
                    break
            if changed:
                break
        if not changed:
            return
        self._push_undo()
        for key_id in ids:
            self.model.set_mapper_legend(key_id, legends)
        self.refresh_canvas()
        self.statusBar().showMessage(f"Legend applied to {len(ids)} key(s)", 1200)

    def _auto_apply_bbox_field(self, field: str):
        ids = self._selected_key_ids_in_order()
        if not ids:
            return
        field_value = {
            "x": self.bbox_x.value(),
            "y": self.bbox_y.value(),
            "width": self.bbox_w.value(),
            "height": self.bbox_h.value(),
        }[field]
        changed = False
        for key_id in ids:
            b = self.model.key_bbox(key_id)
            if not b:
                continue
            target = field_value
            if field in ("x", "y"):
                target = max(0, target)
            elif field in ("width", "height"):
                target = max(1, target)
            if b[field] != target:
                changed = True
                break
        if not changed:
            return
        self._push_undo()
        for key_id in ids:
            b = self.model.key_bbox(key_id)
            if not b:
                continue
            target = field_value
            if field in ("x", "y"):
                target = max(0, target)
            elif field in ("width", "height"):
                target = max(1, target)
            b[field] = target
            self.model.set_mapper_bbox(key_id, b["x"], b["y"], b["width"], b["height"])
        self.refresh_canvas()
        self.statusBar().showMessage(f"BBox {field} applied to {len(ids)} key(s)", 1200)

    def _auto_apply_overlay_color(self):
        ids = self._selected_key_ids_in_order()
        if not ids:
            return
        changed = False
        for key_id in ids:
            c = self.model.key_overlay_color(key_id)
            cur = c if c is not None else (80, 160, 255)
            if (
                cur[0] != self.color_r.value()
                or cur[1] != self.color_g.value()
                or cur[2] != self.color_b.value()
            ):
                changed = True
                break
        if not changed:
            return
        self._push_undo()
        for key_id in ids:
            self.model.set_mapper_overlay_color(
                key_id,
                self.color_r.value(),
                self.color_g.value(),
                self.color_b.value(),
            )
        self.refresh_canvas()
        self.statusBar().showMessage(f"Overlay color applied to {len(ids)} key(s)", 1200)

    def _auto_apply_overlay_component(self, component: int):
        ids = self._selected_key_ids_in_order()
        if not ids:
            return
        target = [self.color_r.value(), self.color_g.value(), self.color_b.value()][component]
        changed = False
        for key_id in ids:
            c = self.model.key_overlay_color(key_id)
            cur = list(c) if c is not None else [80, 160, 255]
            if cur[component] != target:
                changed = True
                break
        if not changed:
            return
        self._push_undo()
        for key_id in ids:
            c = self.model.key_overlay_color(key_id)
            cur = list(c) if c is not None else [80, 160, 255]
            cur[component] = target
            self.model.set_mapper_overlay_color(key_id, cur[0], cur[1], cur[2])
        self.refresh_canvas()
        cname = ("R", "G", "B")[component]
        self.statusBar().showMessage(f"Overlay {cname} applied to {len(ids)} key(s)", 1200)

    def _pick_overlay_color(self):
        ids = self._selected_key_ids_in_order()
        if not ids:
            QMessageBox.warning(self, "No key selected", "Select a mapper key on the image first.")
            return
        if self._image_pixmap is None or self._image_pixmap.isNull():
            QMessageBox.warning(self, "No image", "Load a keyboard image first to use eyedropper.")
            return
        self._image_eyedropper_active = True
        self.view.viewport().setCursor(Qt.CrossCursor)
        self.statusBar().showMessage(
            "Eyedropper active: click image to sample color (Esc or right-click to cancel).",
            6000,
        )

    def consume_image_eyedropper_click(self, scene_pos: QPointF, button: Qt.MouseButton) -> bool:
        if not self._image_eyedropper_active:
            return False
        if button == Qt.RightButton:
            self._image_eyedropper_active = False
            self.view.viewport().unsetCursor()
            self.statusBar().showMessage("Eyedropper canceled", 1500)
            return True
        if button != Qt.LeftButton:
            return True
        if self._image_pixmap is None or self._image_pixmap.isNull():
            self._image_eyedropper_active = False
            self.view.viewport().unsetCursor()
            self.statusBar().showMessage("Eyedropper canceled (no image loaded)", 2000)
            return True
        x = int(round(scene_pos.x()))
        y = int(round(scene_pos.y()))
        if x < 0 or y < 0 or x >= self._image_pixmap.width() or y >= self._image_pixmap.height():
            self.statusBar().showMessage("Click inside the loaded image to sample color", 1500)
            return True
        sampled = self._image_pixmap.toImage().pixelColor(x, y)
        self.color_r.setValue(int(sampled.red()))
        self.color_g.setValue(int(sampled.green()))
        self.color_b.setValue(int(sampled.blue()))
        self._image_eyedropper_active = False
        self.view.viewport().unsetCursor()
        self._auto_apply_overlay_color()
        return True

    def _make_selected_same_color(self):
        ids = self._selected_key_ids_in_order()
        if len(ids) < 2:
            QMessageBox.information(self, "Selection required", "Select at least 2 keys (Ctrl/Shift+click).")
            return
        source = self._effective_overlay_color(ids[0])
        self._push_undo()
        for key_id in ids[1:]:
            self.model.set_mapper_overlay_color(key_id, source[0], source[1], source[2])
        self.color_r.setValue(int(source[0]))
        self.color_g.setValue(int(source[1]))
        self.color_b.setValue(int(source[2]))
        self.refresh_canvas()
        self.statusBar().showMessage(f"Matched overlay color across {len(ids)} key(s)", 1500)

    def _auto_apply_matrix(self):
        if not self.selected_host_key:
            return
        if self.row_spin.value() < 0 or self.bit_spin.value() < 0:
            return
        self._push_undo()
        self.model.set_binding_matrix(self.selected_host_key, self.row_spin.value(), self.bit_spin.value())
        self.refresh_bindings()
        self.statusBar().showMessage("Matrix mapping applied", 1200)

    def _on_target_kind_changed(self, _text: str):
        self._refresh_target_id_choices()

    def _refresh_target_id_choices(self):
        current = self.target_id_combo.currentText().strip()
        kind = self.target_kind_combo.currentText().strip().lower()
        choices: List[str]
        if kind == "mapper":
            choices = sorted(self.model.mapper_key_ids())
        elif kind == "emulator":
            choices = sorted(self.model.FIXED_EMULATOR_KEY_IDS)
        else:
            choices = sorted(self.model.defined_system_key_ids())
        self.target_id_combo.blockSignals(True)
        self.target_id_combo.clear()
        for c in choices:
            self.target_id_combo.addItem(c)
        if current:
            self.target_id_combo.setEditText(current)
        self.target_id_combo.blockSignals(False)

    def _apply_binding_target(self):
        if not self.selected_host_key:
            QMessageBox.warning(self, "No host key", "Select a host binding first.")
            return
        kind = self.target_kind_combo.currentText().strip().lower()
        target_id = self.target_id_combo.currentText().strip()
        if not target_id:
            QMessageBox.warning(self, "No target id", "Enter a target id.")
            return
        self._push_undo()
        try:
            self.model.set_binding_target(self.selected_host_key, kind, target_id)
        except Exception as exc:
            QMessageBox.warning(self, "Set target failed", str(exc))
            return
        self.refresh_bindings()
        self._select_binding_item(self.selected_host_key)
        self._select_host_binding(self.selected_host_key)
        self.statusBar().showMessage(
            f"Target set: {self.selected_host_key} -> {kind}:{target_id}",
            2000,
        )

    def _auto_apply_ascii(self):
        if not self.selected_host_key:
            return
        try:
            self._push_undo()
            self.model.set_binding_ascii(
                self.selected_host_key,
                self._parse_opt_int(self.ascii_edit.text()),
                self._parse_opt_int(self.ascii_shift_edit.text()),
                self._parse_opt_int(self.ascii_ctrl_edit.text()),
            )
            self.refresh_bindings()
            self.statusBar().showMessage("ASCII mapping applied", 1200)
        except Exception:
            # Keep manual Apply button + warning path for explicit validation feedback.
            return

    def _push_undo(self):
        self.undo_stack.append(self.model.snapshot())
        self.redo_stack.clear()

    def _begin_bbox_interaction(self):
        if self._bbox_interaction_active:
            return
        self._push_undo()
        self._bbox_interaction_active = True

    def _live_bbox_from_item(self, key_id: str, rect: QRectF):
        x = int(round(rect.x()))
        y = int(round(rect.y()))
        w = max(1, int(round(rect.width())))
        h = max(1, int(round(rect.height())))
        try:
            self.model.set_mapper_bbox(key_id, x, y, w, h)
        except Exception:
            return
        if self.selected_mapper_key_id != key_id:
            self.selected_mapper_key_id = key_id
            self._load_selected_key_fields(key_id)
        else:
            self.bbox_x.setValue(x)
            self.bbox_y.setValue(y)
            self.bbox_w.setValue(w)
            self.bbox_h.setValue(h)

    def _commit_bbox_from_item(self, key_id: str, rect: QRectF):
        self._live_bbox_from_item(key_id, rect)
        self._bbox_interaction_active = False
        self.refresh_canvas()
        self.statusBar().showMessage(f"BBox updated for {key_id}", 1500)

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(self.model.snapshot())
        self.model.restore_snapshot(self.undo_stack.pop())
        self.refresh_all()

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self.model.snapshot())
        self.model.restore_snapshot(self.redo_stack.pop())
        self.refresh_all()

    def restore(self):
        self.model = KeymapperModel.load(
            mapper_path=self.model.docs.mapper_path,
            host_map_path=self.model.docs.host_map_path,
            keymapper_schema_path=Path("schemas/keyboard-keymapper.schema.json"),
            runtime_map_schema_path=Path("schemas/runtime_keyboard_map_schema.json"),
            device_path=self.model.docs.device_path,
        )
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._saved_mapper_state = copy.deepcopy(self.model.mapper)
        self._saved_host_map_state = copy.deepcopy(self.model.host_map)
        self._update_window_title()
        self.refresh_all()

    def save_mapper(self) -> bool:
        try:
            self.model.save_mapper()
            self._saved_mapper_state = copy.deepcopy(self.model.mapper)
            self.statusBar().showMessage("Mapper saved", 3000)
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Save Mapper failed", str(exc))
            return False

    def save_mapping(self) -> bool:
        errs = self.model.validate_links()
        if errs:
            QMessageBox.warning(self, "Invalid links", "\n".join(errs[:15]))
            return False
        try:
            self.model.save_mapping()
            self._saved_host_map_state = copy.deepcopy(self.model.host_map)
            self.statusBar().showMessage("Mapping saved", 3000)
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Save Mapping failed", str(exc))
            return False

    def change_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose keyboard image", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        self._push_undo()
        rel = Path(path)
        try:
            rel = Path(path).relative_to(self.model.docs.mapper_path.parent)
        except Exception:
            pass
        img = self.model.mapper.setdefault("image", {})
        img["file"] = str(rel)
        pix = QPixmap(path)
        if not pix.isNull():
            img["width_px"] = int(pix.width())
            img["height_px"] = int(pix.height())
        self.manual_zoom = False
        self.refresh_canvas()

    def adjust_mapper_fields(self):
        img = self.model.mapper.setdefault("image", {})
        txt, ok = QFileDialog.getOpenFileName(self, "Set image file", str(self.model.docs.mapper_path.parent), "Images (*.png *.jpg *.jpeg *.bmp)")
        if not ok or not txt:
            return
        self._push_undo()
        img["file"] = str(Path(txt).name)
        self.manual_zoom = False
        self.refresh_canvas()

    def reset_zoom_to_fit(self):
        self.manual_zoom = False
        self.fit_scene_to_view(force=True)

    def _system_name(self) -> str:
        return str(self.model.mapper.get("system_name", "")).strip()

    def _update_window_title(self):
        self.setWindowTitle(f"PASM Keyboard Mapper - {self._system_name()}")

    def _is_mapper_dirty(self) -> bool:
        return self.model.mapper != self._saved_mapper_state

    def _is_mapping_dirty(self) -> bool:
        return self.model.host_map != self._saved_host_map_state

    def closeEvent(self, event):
        if self._is_mapper_dirty():
            ans = QMessageBox.question(
                self,
                "Unsaved Mapper Changes",
                "Mapper has unsaved changes. Save before closing?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if ans == QMessageBox.Cancel:
                event.ignore()
                return
            if ans == QMessageBox.Yes and not self.save_mapper():
                event.ignore()
                return

        if self._is_mapping_dirty():
            ans = QMessageBox.question(
                self,
                "Unsaved Mapping Changes",
                "Mapping has unsaved changes. Save before closing?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if ans == QMessageBox.Cancel:
                event.ignore()
                return
            if ans == QMessageBox.Yes and not self.save_mapping():
                event.ignore()
                return

        sure = QMessageBox.question(
            self,
            "Confirm Exit",
            "Are you sure you want to close PASM Keyboard Mapper?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if sure != QMessageBox.Yes:
            event.ignore()
            return
        event.accept()

    def _set_zoom_percent(self, percent: int):
        p = max(25, min(400, int(percent)))
        self.zoom_percent = p
        self.zoom_label.setText(f"{p}%")
        self._zoom_signal_guard = True
        self.zoom_slider.setValue(p)
        self._zoom_signal_guard = False
        if self._base_transform is None:
            self.fit_scene_to_view(force=True)
            return
        t = QTransform(self._base_transform)
        z = p / 100.0
        t.scale(z, z)
        self.view.setTransform(t)
        self.manual_zoom = p != 100

    def _auto_scroll_view_for_scene_pos(self, scene_pos: QPointF):
        # While dragging/resizing, gently auto-scroll when cursor nears viewport edge.
        vp_rect = self.view.viewport().rect()
        vp_pos = self.view.mapFromScene(scene_pos)
        margin = 28
        step = 22

        dx = 0
        dy = 0
        if vp_pos.x() < margin:
            dx = -step
        elif vp_pos.x() > (vp_rect.width() - margin):
            dx = step
        if vp_pos.y() < margin:
            dy = -step
        elif vp_pos.y() > (vp_rect.height() - margin):
            dy = step

        if dx:
            hbar = self.view.horizontalScrollBar()
            hbar.setValue(hbar.value() + dx)
        if dy:
            vbar = self.view.verticalScrollBar()
            vbar.setValue(vbar.value() + dy)

    def _on_zoom_slider_changed(self, value: int):
        if self._zoom_signal_guard:
            return
        self._set_zoom_percent(value)

    def _norm_host_id(self, host_key: str) -> str:
        return self.model.normalize_host_binding_id(host_key)

    def _binding_host_id(self, binding: Dict[str, object]) -> str:
        return self.model.binding_host_id(binding)

    def _binding_host_label(self, binding: Dict[str, object]) -> str:
        return self.model.binding_host_label(binding)

    def adjust_zoom_by_factor(self, factor: float):
        target = int(round(self.zoom_percent * factor))
        self._set_zoom_percent(target)

    def _toggle_edit_mode(self, state: int):
        self.edit_mode = state == int(Qt.Checked)

    def select_mapper_key(self, key_id: str, modifiers: Qt.KeyboardModifiers = Qt.NoModifier):
        if not key_id:
            return
        toggle = bool(modifiers & Qt.ControlModifier)
        additive = bool(modifiers & Qt.ShiftModifier)

        if toggle:
            if key_id in self.selected_mapper_key_ids:
                self.selected_mapper_key_ids.remove(key_id)
                if self.selected_mapper_key_id == key_id:
                    self.selected_mapper_key_id = next(iter(self.selected_mapper_key_ids), None)
            else:
                self.selected_mapper_key_ids.add(key_id)
                self.selected_mapper_key_id = key_id
        elif additive:
            if key_id in self.selected_mapper_key_ids and len(self.selected_mapper_key_ids) > 1:
                self.selected_mapper_key_ids.remove(key_id)
                if self.selected_mapper_key_id == key_id:
                    self.selected_mapper_key_id = next(iter(self.selected_mapper_key_ids), None)
            else:
                self.selected_mapper_key_ids.add(key_id)
                self.selected_mapper_key_id = key_id
        else:
            self.selected_mapper_key_ids = {key_id}
            self.selected_mapper_key_id = key_id

        if self.selected_mapper_key_id:
            self._load_selected_key_fields(self.selected_mapper_key_id)
        self._refresh_alias_bindings()
        self._update_selection_field_enabled_state()
        self.statusBar().showMessage(
            f"Selected keys: {len(self.selected_mapper_key_ids)} (Shift=add, Ctrl=toggle)",
            2000,
        )

    def _selected_key_ids_in_order(self) -> List[str]:
        if not self.selected_mapper_key_id:
            return []
        out = [self.selected_mapper_key_id]
        for k in sorted(self.selected_mapper_key_ids):
            if k != self.selected_mapper_key_id:
                out.append(k)
        return out

    def _align_selected(self, mode: str):
        ids = self._selected_key_ids_in_order()
        if len(ids) < 2:
            QMessageBox.information(self, "Selection required", "Select at least 2 keys (Ctrl/Shift+click).")
            return
        anchor = self.model.key_bbox(ids[0])
        if not anchor:
            return
        self._push_undo()
        ax, ay, aw, ah = anchor["x"], anchor["y"], anchor["width"], anchor["height"]
        for key_id in ids[1:]:
            b = self.model.key_bbox(key_id)
            if not b:
                continue
            x, y, w, h = b["x"], b["y"], b["width"], b["height"]
            if mode == "left":
                x = ax
            elif mode == "right":
                x = ax + aw - w
            elif mode == "top":
                y = ay
            elif mode == "bottom":
                y = ay + ah - h
            elif mode == "hcenter":
                x = ax + (aw - w) // 2
            elif mode == "vcenter":
                y = ay + (ah - h) // 2
            self.model.set_mapper_bbox(key_id, max(0, x), max(0, y), w, h)
        self.refresh_canvas()
        self.statusBar().showMessage(f"Aligned {len(ids)} keys ({mode})", 1500)

    def _size_selected(self, mode: str):
        ids = self._selected_key_ids_in_order()
        if len(ids) < 2:
            QMessageBox.information(self, "Selection required", "Select at least 2 keys (Ctrl/Shift+click).")
            return
        anchor = self.model.key_bbox(ids[0])
        if not anchor:
            return
        self._push_undo()
        aw, ah = anchor["width"], anchor["height"]
        for key_id in ids[1:]:
            b = self.model.key_bbox(key_id)
            if not b:
                continue
            w, h = b["width"], b["height"]
            if mode in ("width", "both"):
                w = aw
            if mode in ("height", "both"):
                h = ah
            self.model.set_mapper_bbox(key_id, b["x"], b["y"], max(1, w), max(1, h))
        self.refresh_canvas()
        self.statusBar().showMessage(f"Resized {len(ids)} keys ({mode})", 1500)

    def _distribute_selected(self, mode: str):
        ids = self._selected_key_ids_in_order()
        if len(ids) < 3:
            QMessageBox.information(self, "Selection required", "Select at least 3 keys (Ctrl/Shift+click).")
            return

        boxes = []
        for key_id in ids:
            b = self.model.key_bbox(key_id)
            if not b:
                continue
            boxes.append((key_id, b))
        if len(boxes) < 3:
            return

        self._push_undo()
        if mode == "horizontal":
            boxes.sort(key=lambda it: it[1]["x"] + (it[1]["width"] / 2.0))
            start = boxes[0][1]["x"] + (boxes[0][1]["width"] / 2.0)
            end = boxes[-1][1]["x"] + (boxes[-1][1]["width"] / 2.0)
            step = (end - start) / float(len(boxes) - 1)
            for i, (key_id, b) in enumerate(boxes[1:-1], start=1):
                center = start + (step * i)
                nx = int(round(center - (b["width"] / 2.0)))
                self.model.set_mapper_bbox(key_id, max(0, nx), b["y"], b["width"], b["height"])
        elif mode == "vertical":
            boxes.sort(key=lambda it: it[1]["y"] + (it[1]["height"] / 2.0))
            start = boxes[0][1]["y"] + (boxes[0][1]["height"] / 2.0)
            end = boxes[-1][1]["y"] + (boxes[-1][1]["height"] / 2.0)
            step = (end - start) / float(len(boxes) - 1)
            for i, (key_id, b) in enumerate(boxes[1:-1], start=1):
                center = start + (step * i)
                ny = int(round(center - (b["height"] / 2.0)))
                self.model.set_mapper_bbox(key_id, b["x"], max(0, ny), b["width"], b["height"])
        else:
            return

        self.refresh_canvas()
        self.statusBar().showMessage(f"Distributed {len(boxes)} keys ({mode})", 1500)

    def _key_id_at_scene_pos(self, scene_pos: QPointF) -> Optional[str]:
        x = int(scene_pos.x())
        y = int(scene_pos.y())
        for key in self.model.mapper_keys():
            bbox = key.get("bbox") or {}
            bx, by = int(bbox.get("x", 0)), int(bbox.get("y", 0))
            bw, bh = int(bbox.get("width", 0)), int(bbox.get("height", 0))
            if bx <= x <= bx + bw and by <= y <= by + bh:
                return str(key.get("id", ""))
        return None

    def show_canvas_context_menu(self, global_pos, scene_pos: QPointF):
        key_id = self._key_id_at_scene_pos(scene_pos)
        # Source-key rule:
        # - Right-click on an already-selected key => that key becomes source.
        # - Otherwise keep current source (last selected).
        # - If there is no selection yet and a key is clicked, select it.
        if key_id and key_id in self.selected_mapper_key_ids:
            if self.selected_mapper_key_id != key_id:
                self.selected_mapper_key_id = key_id
                self._load_selected_key_fields(key_id)
                self._refresh_alias_bindings()
                self.refresh_canvas()
        elif key_id and not self.selected_mapper_key_ids:
            self.select_mapper_key(key_id, Qt.NoModifier)
            self.refresh_canvas()

        menu = QMenu(self)
        align_menu = menu.addMenu("Align")
        act_align_left = align_menu.addAction("Left")
        act_align_right = align_menu.addAction("Right")
        act_align_top = align_menu.addAction("Top")
        act_align_bottom = align_menu.addAction("Bottom")
        act_align_hc = align_menu.addAction("Horizontal Center")
        act_align_vc = align_menu.addAction("Vertical Center")

        size_menu = menu.addMenu("Size")
        act_size_w = size_menu.addAction("Match Width")
        act_size_h = size_menu.addAction("Match Height")
        act_size_both = size_menu.addAction("Match Size")

        distribute_menu = menu.addMenu("Distribute")
        act_dist_h = distribute_menu.addAction("Horizontal")
        act_dist_v = distribute_menu.addAction("Vertical")
        color_menu = menu.addMenu("Color")
        act_color_pick = color_menu.addAction("Pick Color...")
        act_color_apply_rgb = color_menu.addAction("Apply RGB To Selected")
        act_color_same = color_menu.addAction("Make Same Color")

        sel_count = len(self._selected_key_ids_in_order())
        enabled = sel_count >= 2
        for act in (
            act_align_left,
            act_align_right,
            act_align_top,
            act_align_bottom,
            act_align_hc,
            act_align_vc,
            act_size_w,
            act_size_h,
            act_size_both,
        ):
            act.setEnabled(enabled)
        for act in (act_dist_h, act_dist_v):
            act.setEnabled(sel_count >= 3)
        act_color_pick.setEnabled(sel_count >= 1)
        act_color_apply_rgb.setEnabled(sel_count >= 1)
        act_color_same.setEnabled(sel_count >= 2)

        chosen = menu.exec(global_pos)
        if chosen == act_align_left:
            self._align_selected("left")
        elif chosen == act_align_right:
            self._align_selected("right")
        elif chosen == act_align_top:
            self._align_selected("top")
        elif chosen == act_align_bottom:
            self._align_selected("bottom")
        elif chosen == act_align_hc:
            self._align_selected("hcenter")
        elif chosen == act_align_vc:
            self._align_selected("vcenter")
        elif chosen == act_size_w:
            self._size_selected("width")
        elif chosen == act_size_h:
            self._size_selected("height")
        elif chosen == act_size_both:
            self._size_selected("both")
        elif chosen == act_dist_h:
            self._distribute_selected("horizontal")
        elif chosen == act_dist_v:
            self._distribute_selected("vertical")
        elif chosen == act_color_pick:
            self._pick_overlay_color()
        elif chosen == act_color_apply_rgb:
            self._auto_apply_overlay_color()
        elif chosen == act_color_same:
            self._make_selected_same_color()

    def eventFilter(self, obj, event):
        et = event.type()
        if et == QEvent.KeyPress:
            self._show_keyboard_event_debug(event, "down")
            if self._image_eyedropper_active and event.key() == Qt.Key_Escape:
                self._image_eyedropper_active = False
                self.view.viewport().unsetCursor()
                self.statusBar().showMessage("Eyedropper canceled", 1500)
                event.accept()
                return True
            if (
                self.pending_alias_capture_mapper_key_id
                and event.key() == Qt.Key_Escape
                and (event.modifiers() & Qt.ControlModifier)
            ):
                self.pending_alias_capture_mapper_key_id = None
                self._set_alias_capture_ui(False)
                self.statusBar().showMessage("Alias capture canceled", 2000)
                event.accept()
                return True
            host_candidates = _qt_event_host_candidates(event)
            if self.pending_alias_capture_mapper_key_id and host_candidates:
                self._complete_alias_capture(host_candidates[0])
                event.accept()
                return True
            if self._is_edit_widget_focused():
                return super().eventFilter(obj, event)
            if host_candidates:
                self._handle_host_key_press(host_candidates)
                # In edit mode, key presses are command input for mapping.
                if self.edit_mode:
                    event.accept()
                    return True
        elif et == QEvent.KeyRelease:
            self._show_keyboard_event_debug(event, "up")
            if self._is_edit_widget_focused():
                return super().eventFilter(obj, event)
            host_candidates = _qt_event_host_candidates(event)
            if host_candidates:
                self._handle_host_key_release(host_candidates)
                if self.edit_mode:
                    event.accept()
                    return True
        return super().eventFilter(obj, event)

    def _complete_alias_capture(self, host_key: str):
        mapper_key_id = self.pending_alias_capture_mapper_key_id
        self.pending_alias_capture_mapper_key_id = None
        self._set_alias_capture_ui(False)
        if not mapper_key_id:
            return
        hk = self._norm_host_id(host_key)
        if not hk:
            return
        self._push_undo()
        try:
            self.model.add_host_alias(
                mapper_key_id,
                hk,
                source_host_key=self.selected_alias_host_key or self.selected_host_key,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Add alias failed", str(exc))
            return
        self.selected_mapper_key_id = mapper_key_id
        self.selected_alias_host_key = hk
        self.selected_host_key = hk
        self.refresh_all()
        self._select_binding_item(hk)
        self._select_alias_binding_item(hk)
        self.statusBar().showMessage(f"Alias added: {hk} -> {mapper_key_id}", 2500)

    def _is_edit_widget_focused(self) -> bool:
        fw = QApplication.focusWidget()
        if fw is None:
            return False
        return isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox))

    def _resolve_binding_for_host_candidates(self, host_candidates: List[str]) -> tuple[Optional[str], Optional[Dict[str, object]]]:
        # Primary path: emulate runtime map resolution by SDL scancode identity.
        candidate_sdl: List[int] = []
        for host_key in host_candidates:
            sc = _host_token_to_sdl_scancode(host_key)
            if sc is not None and sc not in candidate_sdl:
                candidate_sdl.append(sc)
        if candidate_sdl:
            for target_sc in candidate_sdl:
                for binding in self.model.host_bindings():
                    hid = self._binding_host_id(binding)
                    b_sc = _host_token_to_sdl_scancode(hid)
                    if b_sc is None:
                        continue
                    if b_sc == target_sc:
                        return hid, binding
        # Fallback: exact host token match.
        for host_key in host_candidates:
            binding = self.model.binding_for_host_key(host_key)
            if binding is not None:
                return host_key, binding
        return None, None

    def _handle_host_key_press(self, host_candidates: List[str]):
        if not host_candidates:
            return
        host_key, binding = self._resolve_binding_for_host_candidates(host_candidates)
        capture_host_key = host_candidates[0]
        if self.edit_mode and self.selected_mapper_key_id:
            self._push_undo()
            try:
                self.model.add_host_alias(
                    self.selected_mapper_key_id,
                    capture_host_key,
                    source_host_key=self.selected_alias_host_key or self.selected_host_key,
                )
            except Exception as exc:
                QMessageBox.warning(self, "Alias mapping failed", str(exc))
                return
            self.selected_host_key = capture_host_key
            self.selected_alias_host_key = capture_host_key
            self._select_binding_item(capture_host_key)
            self._select_alias_binding_item(capture_host_key)
            self._select_host_binding(capture_host_key)
            self.pressed_mapper_key_ids = {self.selected_mapper_key_id}
            self.refresh_all()
            self.statusBar().showMessage(f"Assigned {capture_host_key} -> {self.selected_mapper_key_id}", 3000)
            return

        if not binding:
            return
        sid = str(binding.get("system_key_id", "")).strip()
        sid_mid = self._mapper_key_id_for_system_key(sid) if sid else None
        if sid and self.model.system_key_visual_feedback(sid):
            self.pressed_system_key_ids.add(sid)
            if sid_mid:
                self.pressed_mapper_key_ids.add(sid_mid)
        mid = str(binding.get("mapper_key_id", "")).strip()
        if mid:
            self.pressed_mapper_key_ids.add(mid)
        mapped_ids = self._mapped_ids()
        if sid_mid:
            self._refresh_rect_item_style(sid_mid, mapped_ids)
        if mid:
            self._refresh_rect_item_style(mid, mapped_ids)
        non_selecting_mods = {"LSHIFT", "RSHIFT", "LCTRL", "RCTRL", "LALT", "RALT"}
        # Modifiers should still produce visual pressed feedback, but must not
        # drive bbox selection changes.
        if (host_key or "") in non_selecting_mods and not self.edit_mode:
            return
        if host_key:
            self._select_binding_item(host_key)
            self._select_alias_binding_item(host_key)
            self._select_host_binding(host_key)

    def _handle_host_key_release(self, host_candidates: List[str]):
        if not host_candidates:
            return
        _host_key, binding = self._resolve_binding_for_host_candidates(host_candidates)
        if not binding:
            return
        sid = str(binding.get("system_key_id", "")).strip()
        sid_mid = self._mapper_key_id_for_system_key(sid) if sid else None
        if sid and sid in self.pressed_system_key_ids:
            self.pressed_system_key_ids.remove(sid)
            if sid_mid and sid_mid in self.pressed_mapper_key_ids:
                self.pressed_mapper_key_ids.remove(sid_mid)
        mid = str(binding.get("mapper_key_id", "")).strip()
        if mid and mid in self.pressed_mapper_key_ids:
            self.pressed_mapper_key_ids.remove(mid)
        if sid or mid:
            mapped_ids = self._mapped_ids()
            if sid_mid:
                self._refresh_rect_item_style(sid_mid, mapped_ids)
            if mid:
                self._refresh_rect_item_style(mid, mapped_ids)

    def keyPressEvent(self, event: QKeyEvent):
        if self.edit_mode and self.selected_mapper_key_id:
            host_candidates = _qt_event_host_candidates(event)
            if host_candidates:
                self._handle_host_key_press(host_candidates)
                return
        super().keyPressEvent(event)

    def _on_binding_item_changed(self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem]):
        if current is None:
            self._clear_mapping_fields()
            return
        host_key = str(current.data(Qt.UserRole) or "").strip()
        if not host_key:
            # Fallback for any legacy items.
            text = current.text() or ""
            host_key = text.split(" -> ", 1)[0].strip() if text else ""
        if not host_key:
            self._clear_mapping_fields()
            return
        self._select_host_binding(host_key)

    def _on_alias_binding_item_changed(self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem]):
        if current is None:
            return
        host_key = str(current.data(Qt.UserRole) or "").strip()
        if not host_key:
            text = current.text() or ""
            host_key = text.split(" -> ", 1)[0].strip() if text else ""
        if not host_key:
            return
        self.selected_alias_host_key = self._norm_host_id(host_key)
        self._select_binding_item(host_key)
        self._select_host_binding(host_key)

    def _apply_matrix(self):
        if not self.selected_host_key:
            QMessageBox.warning(self, "No host key", "Select a host binding first.")
            return
        if self.row_spin.value() < 0 or self.bit_spin.value() < 0:
            QMessageBox.warning(self, "Invalid matrix", "Matrix row/bit must be set (not '-').")
            return
        self._push_undo()
        self.model.set_binding_matrix(self.selected_host_key, self.row_spin.value(), self.bit_spin.value())
        self.refresh_bindings()

    def _parse_opt_int(self, text: str) -> Optional[int]:
        t = text.strip()
        if not t:
            return None
        return int(t, 0)

    def _apply_ascii(self):
        if not self.selected_host_key:
            QMessageBox.warning(self, "No host key", "Select a host binding first.")
            return
        try:
            self._push_undo()
            self.model.set_binding_ascii(
                self.selected_host_key,
                self._parse_opt_int(self.ascii_edit.text()),
                self._parse_opt_int(self.ascii_shift_edit.text()),
                self._parse_opt_int(self.ascii_ctrl_edit.text()),
            )
            self.refresh_bindings()
        except Exception as exc:
            QMessageBox.warning(self, "Invalid ASCII values", str(exc))

    def _apply_key_fields(self):
        ids = self._selected_key_ids_in_order()
        if not ids:
            QMessageBox.warning(self, "No key selected", "Select a mapper key on the image first.")
            return
        legends = [x.strip() for x in self.legend_edit.text().split(",") if x.strip()]
        if not legends:
            QMessageBox.warning(self, "Invalid legends", "Legend list cannot be empty.")
            return
        self._push_undo()
        for key_id in ids:
            self.model.set_mapper_bbox(
                key_id,
                self.bbox_x.value(),
                self.bbox_y.value(),
                self.bbox_w.value(),
                self.bbox_h.value(),
            )
            self.model.set_mapper_legend(key_id, legends)
        self.refresh_canvas()
        self.statusBar().showMessage(f"Key fields applied to {len(ids)} key(s)", 1500)

    def select_key_at(self, scene_pos: QPointF, modifiers: Qt.KeyboardModifiers = Qt.NoModifier):
        x = int(scene_pos.x())
        y = int(scene_pos.y())
        for key in self.model.mapper_keys():
            bbox = key.get("bbox") or {}
            bx, by = int(bbox.get("x", 0)), int(bbox.get("y", 0))
            bw, bh = int(bbox.get("width", 0)), int(bbox.get("height", 0))
            if bx <= x <= bx + bw and by <= y <= by + bh:
                self.select_mapper_key(str(key.get("id", "")), modifiers)
                self._load_selected_key_fields(self.selected_mapper_key_id)
                # When building a multi-selection, don't force host-binding reselection,
                # otherwise _select_host_binding collapses selection back to one key.
                if (modifiers & Qt.ShiftModifier) or (modifiers & Qt.ControlModifier):
                    self.refresh_canvas()
                    return
                binds = self.model.bindings_for_mapper_key(self.selected_mapper_key_id)
                if binds:
                    preferred = self.selected_alias_host_key or self.selected_host_key
                    hk = ""
                    if preferred:
                        pnorm = self._norm_host_id(preferred)
                        for b in binds:
                            if self._binding_host_id(b) == pnorm:
                                hk = self._binding_host_label(b)
                                break
                    if not hk:
                        hk = self._binding_host_label(binds[0])
                    if hk:
                        self._select_binding_item(hk)
                        self._select_alias_binding_item(hk)
                        self._select_host_binding(hk)
                else:
                    self._clear_mapping_fields()
                    self.selected_alias_host_key = None
                    self._refresh_alias_bindings()
                self.refresh_canvas()
                return
        # Clicked empty canvas area: clear box selection.
        if self.selected_mapper_key_ids or self.selected_mapper_key_id:
            self.selected_mapper_key_id = None
            self.selected_mapper_key_ids.clear()
            self.key_id_label.setText("-")
            self._refresh_alias_bindings()
            self._update_selection_field_enabled_state()
            self.refresh_canvas()
            self.statusBar().showMessage("Selection cleared", 1200)

    def _clear_mapping_fields(self):
        self.selected_host_key = None
        self.selected_alias_host_key = None
        self.selected_mapper_key_ids.clear()
        self.selected_mapper_key_id = None
        self.key_id_label.setText("-")
        self.row_spin.setValue(-1)
        self.bit_spin.setValue(-1)
        self.matrix_presses_edit.setText("")
        self.ascii_edit.setText("")
        self.ascii_shift_edit.setText("")
        self.ascii_ctrl_edit.setText("")
        self.target_kind_combo.setCurrentText("mapper")
        self._refresh_target_id_choices()
        self.target_id_combo.setEditText("")
        self._update_selection_field_enabled_state()

    def _select_host_binding(self, host_key: str):
        host_id = self._norm_host_id(host_key)
        self.selected_host_key = host_id
        self.selected_alias_host_key = host_id
        b = self.model.binding_for_host_key(host_key)
        if not b:
            self._clear_mapping_fields()
            return
        mid = self.model.binding_mapper_key_id(b)
        sid = str(b.get("system_key_id", "")).strip()
        if not mid and sid:
            mid = self._mapper_key_id_for_system_key(sid) or ""
            if not mid:
                self._push_undo()
                mid = self._create_mapper_key_for_system_key(sid) or ""
                if mid:
                    self.statusBar().showMessage(f"Created bbox for system key: {sid}", 2000)
        if mid:
            self.selected_mapper_key_id = mid
            self.selected_mapper_key_ids = {mid}
            self._load_selected_key_fields(mid)
            self._refresh_alias_bindings()
        else:
            self.selected_mapper_key_id = None
            self.selected_mapper_key_ids.clear()
            self.key_id_label.setText("-")
            self._refresh_alias_bindings()
        presses = b.get("presses")
        multi = isinstance(presses, list) and len(presses) > 1
        if isinstance(presses, list) and presses and not multi:
            pr = presses[0]
            self.row_spin.setValue(int(pr.get("row", 0)))
            self.bit_spin.setValue(int(pr.get("bit", 0)))
        else:
            self.row_spin.setValue(-1)
            self.bit_spin.setValue(-1)
        self.matrix_presses_edit.setText(self._presses_as_text(presses))

        # For multi-press bindings, edits must go through the dialog; otherwise
        # the row/bit fields would collapse the binding to one press.
        self.row_spin.setEnabled(not multi)
        self.bit_spin.setEnabled(not multi)
        self.edit_matrix_presses_btn.setEnabled(True)
        if multi:
            self.statusBar().showMessage(
                f"Binding {self._binding_host_label(b)} has {len(presses)} matrix presses; use 'Edit Presses...'",
                3500,
            )
        self.ascii_edit.setText(str(b.get("ascii", "")))
        self.ascii_shift_edit.setText(str(b.get("ascii_shift", "")))
        self.ascii_ctrl_edit.setText(str(b.get("ascii_ctrl", "")))
        mid = self.model.binding_mapper_key_id(b)
        eid = str(b.get("emulator_key_id", "")).strip()
        sid = str(b.get("system_key_id", "")).strip()
        if mid:
            self.target_kind_combo.setCurrentText("mapper")
            self._refresh_target_id_choices()
            self.target_id_combo.setEditText(mid)
        elif eid:
            self.target_kind_combo.setCurrentText("emulator")
            self._refresh_target_id_choices()
            self.target_id_combo.setEditText(eid)
        elif sid:
            self.target_kind_combo.setCurrentText("system")
            self._refresh_target_id_choices()
            self.target_id_combo.setEditText(sid)
        else:
            self.target_kind_combo.setCurrentText("mapper")
            self._refresh_target_id_choices()
            self.target_id_combo.setEditText("")
        self._update_selection_field_enabled_state()
        self.refresh_canvas()

    def _edit_matrix_presses_dialog(self):
        if not self.selected_host_key:
            QMessageBox.warning(self, "No host binding", "Select a host binding first.")
            return
        b = self.model.binding_for_host_key(self.selected_host_key)
        if not b:
            QMessageBox.warning(self, "No host binding", "Select a host binding first.")
            return

        existing = b.get("presses")
        presses: List[Dict[str, int]] = []
        if isinstance(existing, list):
            for p in existing:
                if isinstance(p, dict) and "row" in p and "bit" in p:
                    presses.append({"row": int(p["row"]), "bit": int(p["bit"])})

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Edit Matrix Presses ({self.selected_host_key})")
        layout = QVBoxLayout(dlg)

        lst = QListWidget()
        for p in presses:
            item = QListWidgetItem(f"r{p['row']}/b{p['bit']}")
            item.setData(Qt.UserRole, (int(p["row"]), int(p["bit"])))
            lst.addItem(item)
        layout.addWidget(lst)

        controls = QWidget()
        form = QFormLayout(controls)
        form.setContentsMargins(0, 0, 0, 0)
        row = QSpinBox(); row.setRange(0, 31)
        bit = QSpinBox(); bit.setRange(0, 7)
        form.addRow("Row", row)
        form.addRow("Bit", bit)

        row_btns = QWidget()
        row_btns_layout = QHBoxLayout(row_btns)
        row_btns_layout.setContentsMargins(0, 0, 0, 0)
        add_btn = QPushButton("Add")
        remove_btn = QPushButton("Remove Selected")
        row_btns_layout.addWidget(add_btn)
        row_btns_layout.addWidget(remove_btn)
        form.addRow(row_btns)
        layout.addWidget(controls)

        def _add():
            item = QListWidgetItem(f"r{row.value()}/b{bit.value()}")
            item.setData(Qt.UserRole, (int(row.value()), int(bit.value())))
            lst.addItem(item)

        def _remove():
            r = lst.currentRow()
            if r >= 0:
                lst.takeItem(r)

        add_btn.clicked.connect(_add)
        remove_btn.clicked.connect(_remove)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)

        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            return

        new_presses: List[Dict[str, int]] = []
        for i in range(lst.count()):
            it = lst.item(i)
            if not it:
                continue
            data = it.data(Qt.UserRole)
            if isinstance(data, tuple) and len(data) == 2:
                new_presses.append({"row": int(data[0]), "bit": int(data[1])})
        if not new_presses:
            QMessageBox.warning(self, "Invalid presses", "Matrix presses cannot be empty.")
            return

        self._push_undo()
        try:
            self.model.set_binding_presses(self.selected_host_key, new_presses)
        except Exception as exc:
            QMessageBox.warning(self, "Update failed", str(exc))
            return

        # Refresh UI selection fields without changing selected ids.
        self.refresh_bindings()
        self._refresh_alias_bindings()
        self._select_binding_item(self.selected_host_key)
        self._select_alias_binding_item(self.selected_host_key)
        self._select_host_binding(self.selected_host_key)
        self.statusBar().showMessage("Matrix presses updated", 1500)

    def _select_binding_item(self, host_key: str):
        needle = self._norm_host_id(host_key)
        for i in range(self.bindings_list.count()):
            item = self.bindings_list.item(i)
            if not item:
                continue
            hid = str(item.data(Qt.UserRole) or "").strip()
            if hid and self._norm_host_id(hid) == needle:
                self.bindings_list.blockSignals(True)
                self.bindings_list.setCurrentRow(i)
                self.bindings_list.blockSignals(False)
                return
            txt = item.text()
            lhs = txt.split(" -> ", 1)[0].strip()
            if lhs and self._norm_host_id(lhs) == needle:
                self.bindings_list.blockSignals(True)
                self.bindings_list.setCurrentRow(i)
                self.bindings_list.blockSignals(False)
                return

    def _select_alias_binding_item(self, host_key: str):
        needle = self._norm_host_id(host_key)
        for i in range(self.alias_bindings_list.count()):
            item = self.alias_bindings_list.item(i)
            if not item:
                continue
            hid = str(item.data(Qt.UserRole) or "").strip()
            if hid and self._norm_host_id(hid) == needle:
                self.alias_bindings_list.blockSignals(True)
                self.alias_bindings_list.setCurrentRow(i)
                self.alias_bindings_list.blockSignals(False)
                return
            txt = item.text()
            lhs = txt.split(" -> ", 1)[0].strip()
            if lhs and self._norm_host_id(lhs) == needle:
                self.alias_bindings_list.blockSignals(True)
                self.alias_bindings_list.setCurrentRow(i)
                self.alias_bindings_list.blockSignals(False)
                return

    def _refresh_alias_bindings(self):
        self.alias_bindings_list.clear()
        if not self.selected_mapper_key_id:
            return
        binds = self.model.bindings_for_mapper_key(self.selected_mapper_key_id)
        for b in binds:
            hk = self._binding_host_label(b)
            detail = self._binding_payload_detail(b)
            it = QListWidgetItem(f"{hk} -> {self.selected_mapper_key_id} [{detail}]")
            it.setData(Qt.UserRole, hk)
            self.alias_bindings_list.addItem(it)

    def _add_alias_dialog(self):
        if not self.selected_mapper_key_id:
            QMessageBox.warning(self, "No key selected", "Select a mapper key on the image first.")
            return
        if self.pending_alias_capture_mapper_key_id:
            self.pending_alias_capture_mapper_key_id = None
            self._set_alias_capture_ui(False)
            self.statusBar().showMessage("Alias capture canceled", 2000)
            return
        self.pending_alias_capture_mapper_key_id = self.selected_mapper_key_id
        self._set_alias_capture_ui(True)
        self.statusBar().showMessage(
            f"Press host key to add alias for {self.selected_mapper_key_id} (Ctrl+Esc to cancel).",
            8000,
        )

    def _remove_selected_alias(self):
        if not self.selected_alias_host_key:
            QMessageBox.warning(self, "No alias selected", "Select an alias in 'Bindings for Selected Key'.")
            return
        hk = self.selected_alias_host_key
        self._push_undo()
        removed = self.model.remove_host_binding(hk)
        if not removed:
            QMessageBox.warning(self, "Remove alias failed", f"Alias '{hk}' not found.")
            return
        self.selected_alias_host_key = None
        if self.selected_host_key == hk:
            self.selected_host_key = None
        self.refresh_all()
        self.statusBar().showMessage(f"Alias removed: {hk}", 2500)

    def _load_selected_key_fields(self, mapper_key_id: str):
        for key in self.model.mapper_keys():
            if str(key.get("id", "")) == mapper_key_id:
                self.key_id_label.setText(mapper_key_id)
                self.legend_edit.setText(", ".join(str(x) for x in key.get("legend", [])))
                bbox = key.get("bbox") or {}
                self.bbox_x.setValue(int(bbox.get("x", 0)))
                self.bbox_y.setValue(int(bbox.get("y", 0)))
                self.bbox_w.setValue(int(bbox.get("width", 1)))
                self.bbox_h.setValue(int(bbox.get("height", 1)))
                color = self._effective_overlay_color(mapper_key_id)
                self.color_r.setValue(int(color[0]))
                self.color_g.setValue(int(color[1]))
                self.color_b.setValue(int(color[2]))
                return

    def refresh_bindings(self):
        self.bindings_list.clear()
        for b in self.model.host_bindings():
            hk = self._binding_host_label(b)
            mid = self.model.binding_mapper_key_id(b)
            eid = str(b.get("emulator_key_id", "")).strip()
            sid = str(b.get("system_key_id", "")).strip()
            target = mid or eid or sid
            detail = self._binding_payload_detail(b)
            if sid:
                vf = "vf:on" if self.model.system_key_visual_feedback(sid) else "vf:off"
                detail = f"{detail},{vf}"
            it = QListWidgetItem(f"{hk} -> {target} [{detail}]")
            it.setData(Qt.UserRole, hk)
            self.bindings_list.addItem(it)

    def _effective_overlay_color(self, key_id: str) -> tuple[int, int, int]:
        custom = self.model.key_overlay_color(key_id)
        if custom is not None:
            return int(custom[0]), int(custom[1]), int(custom[2])
        mapped_ids = self._mapped_ids()
        if key_id in mapped_ids:
            return 0, 180, 120
        return 80, 160, 255

    def _mapper_key_id_for_system_key(self, system_key_id: str) -> Optional[str]:
        sid = str(system_key_id).strip()
        if not sid:
            return None
        # Convention: if a mapper key shares the same id as the system key, use it
        # as the visual/editable bbox anchor.
        if sid in self.model.mapper_key_ids():
            return sid
        return None

    def _mapped_ids(self) -> set[str]:
        mids = {self.model.binding_mapper_key_id(b) for b in self.model.host_bindings()}
        mids.discard("")
        return mids

    def _apply_rect_style(self, rect: QGraphicsRectItem, key_id: str, mapped_ids: set[str]):
        rect.setPen(QPen(QColor(20, 20, 20, 200), 1))
        effective = self._effective_overlay_color(key_id)
        base_color = QColor(int(effective[0]), int(effective[1]), int(effective[2]))
        if key_id in self.pressed_mapper_key_ids:
            rect.setBrush(QColor(255, 90, 90, 140))
            rect.setPen(QPen(QColor(255, 120, 120, 255), 2))
        elif key_id == self.selected_mapper_key_id:
            rect.setBrush(QColor(255, 230, 80, 110))
            rect.setPen(QPen(QColor(255, 180, 20, 255), 2))
        elif key_id in self.selected_mapper_key_ids:
            rect.setBrush(QColor(255, 210, 120, 85))
            rect.setPen(QPen(QColor(255, 170, 80, 240), 2))
        else:
            alpha = 90 if key_id in mapped_ids else 60
            rect.setBrush(QColor(base_color.red(), base_color.green(), base_color.blue(), alpha))

    def _refresh_rect_item_style(self, key_id: str, mapped_ids: Optional[set[str]] = None):
        item = self.rect_items.get(key_id)
        if item is None:
            return
        if mapped_ids is None:
            mapped_ids = self._mapped_ids()
        self._apply_rect_style(item, key_id, mapped_ids)

    def refresh_canvas(self):
        self.scene.clear()
        self.rect_items.clear()
        self._bbox_interaction_active = False
        self._image_pixmap = None

        max_x = 0
        max_y = 0
        img = self.model.mapper.get("image", {})
        image_file = str(img.get("file", "")).strip()
        image_loaded = False
        if image_file:
            image_path = self._resolve_image_path(image_file)
            pix = QPixmap(str(image_path)) if image_path else QPixmap()
            if not pix.isNull():
                self._image_pixmap = QPixmap(pix)
                self.scene.addPixmap(pix)
                self.scene.setSceneRect(0, 0, pix.width(), pix.height())
                max_x = max(max_x, pix.width())
                max_y = max(max_y, pix.height())
                image_loaded = True
        if not image_loaded:
            width_px = int(img.get("width_px", 0) or 0)
            height_px = int(img.get("height_px", 0) or 0)
            if width_px > 0 and height_px > 0:
                max_x = max(max_x, width_px)
                max_y = max(max_y, height_px)
                self.scene.setSceneRect(0, 0, width_px, height_px)

        mapped_ids = self._mapped_ids()

        for key in self.model.mapper_keys():
            key_id = str(key.get("id", ""))
            bbox = key.get("bbox") or {}
            x = int(bbox.get("x", 0))
            y = int(bbox.get("y", 0))
            w = int(bbox.get("width", 1))
            h = int(bbox.get("height", 1))
            max_x = max(max_x, x + w)
            max_y = max(max_y, y + h)

            rect = MapperRectItem(self, key_id, QRectF(float(x), float(y), float(w), float(h)))
            self._apply_rect_style(rect, key_id, mapped_ids)
            binds = self.model.bindings_for_mapper_key(key_id)
            bind_txt = ", ".join(self._binding_host_label(b) for b in binds)
            legends = ", ".join(str(x) for x in key.get("legend", []))
            rect.setToolTip(f"{key_id}\nlegend: {legends}\nhost: {bind_txt}")
            self.scene.addItem(rect)
            self.rect_items[key_id] = rect

        if self.pressed_system_key_ids:
            y = 8.0
            for sid in sorted(self.pressed_system_key_ids):
                txt = self.scene.addText(f"SYSTEM: {sid}")
                txt.setDefaultTextColor(QColor(255, 200, 80))
                txt.setPos(8.0, y)
                txt.setZValue(9999.0)
                y += 18.0

        if max_x > 0 and max_y > 0:
            self.scene.setSceneRect(0, 0, max_x, max_y)
        self.fit_scene_to_view()

    def _resolve_image_path(self, image_file: str) -> Optional[Path]:
        p = Path(image_file)
        mapper_dir = self.model.docs.mapper_path.parent
        candidates: List[Path] = []

        if p.is_absolute():
            candidates.append(p)
        else:
            candidates.append((mapper_dir / p).resolve())
            candidates.append(Path.cwd() / p)

        for c in candidates:
            if c.exists():
                return c.resolve()

        # If extension is stale, try common alternatives with same stem.
        base = (mapper_dir / p).resolve()
        stem = base.stem
        parent = base.parent
        for ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
            alt = parent / f"{stem}{ext}"
            if alt.exists():
                return alt.resolve()
        return None

    def fit_scene_to_view(self, force: bool = False):
        if self.manual_zoom and not force:
            return
        rect = self.scene.itemsBoundingRect()
        if rect.isNull():
            return
        self.view.fitInView(rect, Qt.KeepAspectRatio)
        self._base_transform = QTransform(self.view.transform())
        self._set_zoom_percent(100)

    def schedule_fit_scene_to_view(self):
        if self.manual_zoom or self._fit_scheduled:
            return
        self._fit_scheduled = True

        def _run():
            self._fit_scheduled = False
            if not self.manual_zoom:
                self.fit_scene_to_view()

        QTimer.singleShot(0, _run)

    def refresh_all(self):
        self.refresh_bindings()
        self._refresh_alias_bindings()
        self._refresh_system_keys()
        self._update_system_key_action_enabled_state()
        self._refresh_target_id_choices()
        self._update_selection_field_enabled_state()
        self.refresh_canvas()
        errs = self.model.validate_links()
        if errs:
            self.statusBar().showMessage(f"Link issues: {len(errs)} (save blocked)")
        else:
            self.statusBar().showMessage("Ready")


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PASM keyboard mapper UI")
    parser.add_argument("--mapper", required=True, help="Keymapper YAML (schema keyboard-keymapper.schema.json)")
    parser.add_argument("--host-map", required=True, help="Runtime host keyboard map YAML")
    parser.add_argument("--device", help="Optional device keyboard YAML for context")
    parser.add_argument(
        "--keymapper-schema",
        default="schemas/keyboard-keymapper.schema.json",
        help="Path to keymapper schema",
    )
    parser.add_argument(
        "--runtime-map-schema",
        default="schemas/runtime_keyboard_map_schema.json",
        help="Path to runtime keyboard map schema",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    model = KeymapperModel.load(
        mapper_path=Path(args.mapper),
        host_map_path=Path(args.host_map),
        keymapper_schema_path=Path(args.keymapper_schema),
        runtime_map_schema_path=Path(args.runtime_map_schema),
        device_path=Path(args.device) if args.device else None,
    )

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    dark = QPalette()
    dark.setColor(QPalette.Window, QColor(36, 38, 41))
    dark.setColor(QPalette.WindowText, QColor(220, 220, 220))
    dark.setColor(QPalette.Base, QColor(26, 28, 31))
    dark.setColor(QPalette.AlternateBase, QColor(36, 38, 41))
    dark.setColor(QPalette.ToolTipBase, QColor(220, 220, 220))
    dark.setColor(QPalette.ToolTipText, QColor(220, 220, 220))
    dark.setColor(QPalette.Text, QColor(220, 220, 220))
    dark.setColor(QPalette.Button, QColor(46, 48, 52))
    dark.setColor(QPalette.ButtonText, QColor(220, 220, 220))
    dark.setColor(QPalette.BrightText, QColor(255, 90, 90))
    dark.setColor(QPalette.Highlight, QColor(42, 130, 218))
    dark.setColor(QPalette.HighlightedText, QColor(245, 245, 245))
    app.setPalette(dark)
    app.setStyleSheet(
        "QToolTip { color: #ddd; background-color: #2d2f33; border: 1px solid #4b4f57; }"
        "QLineEdit:disabled, QAbstractSpinBox:disabled, QComboBox:disabled, "
        "QPushButton:disabled, QCheckBox:disabled, QListWidget:disabled { "
        "color: #7b8088; background-color: #23262b; border-color: #3c4046; }"
        "QLabel:disabled { color: #6f747c; }"
    )
    win = MainWindow(model)
    # Keep a smaller normal geometry so restore/maximize has visible state transitions.
    screen = app.primaryScreen()
    if screen is not None:
        ag = screen.availableGeometry()
        w = max(900, int(ag.width() * 0.78))
        h = max(620, int(ag.height() * 0.78))
        w = min(w, ag.width() - 80) if ag.width() > 120 else ag.width()
        h = min(h, ag.height() - 80) if ag.height() > 120 else ag.height()
        x = ag.x() + max(0, (ag.width() - w) // 2)
        y = ag.y() + max(0, (ag.height() - h) // 2)
        win.setGeometry(x, y, w, h)
    else:
        win.resize(1200, 780)
    win.setMinimumSize(640, 480)
    win.setMaximumSize(16777215, 16777215)  # QWIDGETSIZE_MAX
    win.showMaximized()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
