# pet_hud.py — Authentic Apple "Liquid Glass" HUD (macOS WindowServer Blur + Optical Lens Capsules)
# Matches Apple's official Liquid Glass design language (developer.apple.com/documentation/technologyoverviews/liquid-glass):
#   1. Real macOS WindowServer GPU background blur via CGSSetWindowBackgroundBlurRadius (blurs whatever is behind the window)
#   2. Translucent frosted glass tint (not an opaque black box) with bright 3D specular top-left refraction rims,
#      inner curved lens highlights, and pill-shaped capsule controls matching Apple's [Upload] [Close] [Search] pills.
#   3. Safe PyObjC pointer retention (.retain()) so pressing Ctrl+C never causes a segmentation fault.

import os
import re
import sys
import webbrowser
from urllib.parse import urlparse
from ctypes import cdll, c_void_p
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QFrame, QStackedWidget, QApplication
)
from PySide6.QtCore import Qt, Signal, QThread, QPoint, QPointF, QRectF
from PySide6.QtGui import (
    QColor, QKeyEvent, QMouseEvent, QPainter, QPainterPath,
    QLinearGradient, QRadialGradient, QPen, QBrush, QFont
)

import AppKit
import objc

import database
import brain_ai as ai
from brain_core import (
    handle_focus_command, ingest_drop, ask_brain_agent
)
import mac_integration as mac

APPLE_FONT = ".AppleSystemUIFont"


def enable_macos_window_blur(widget: QWidget, blur_radius: int = 36):
    """
    Uses macOS CoreGraphics / SkyLight WindowServer API (CGSSetWindowBackgroundBlurRadius)
    to apply real-time hardware backdrop blur behind a translucent Qt window without
    adding subviews that cover Qt's QNSView backing store.
    Also retains the PyObjC wrapper so Python GC never releases QNSView on exit.
    """
    try:
        wid = int(widget.winId())
        if not hasattr(widget, "_ns_view_ref") or widget._ns_view_ref is None:
            ns_view = objc.objc_object(c_void_p=wid)
            ns_view.retain()
            widget._ns_view_ref = ns_view
        else:
            ns_view = widget._ns_view_ref

        ns_window = ns_view.window()
        if ns_window:
            ns_window.setHidesOnDeactivate_(False)
            ns_window.setLevel_(AppKit.NSStatusWindowLevel)
            ns_window.setOpaque_(False)
            ns_window.setBackgroundColor_(AppKit.NSColor.clearColor())
            ns_window.setHasShadow_(True)

            win_num = int(ns_window.windowNumber())
            if win_num > 0:
                cg = cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
                cid = cg.CGSDefaultConnectionForThread()
                cg.CGSSetWindowBackgroundBlurRadius(cid, win_num, int(blur_radius))
    except Exception:
        pass


def draw_apple_liquid_glass(
    painter: QPainter,
    rect: QRectF,
    radius: float,
    kind: str = "panel",
    hovered: bool = False
):
    """
    Paints Apple's signature translucent Liquid Glass material (matching the Apple Park screenshot):
      - 'panel':   Main floating glass sheet (translucent frosted neutral slate-grey with bright specular rim)
      - 'capsule': Pill-shaped control / search bar ([Search] style with 3D curved lens sheen)
      - 'card':    Frosted glass item card inside the sheet
    """
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)

    # 1. Translucent Frosted Glass Base Fill (lets the macOS CGS blurred background shine through)
    bg_grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    if kind == "capsule":
        top_a = 135 if hovered else 112
        bot_a = 155 if hovered else 132
        bg_grad.setColorAt(0.0, QColor(138, 146, 158, top_a))
        bg_grad.setColorAt(0.48, QColor(92, 98, 108, (top_a + bot_a) // 2))
        bg_grad.setColorAt(1.0, QColor(68, 74, 84, bot_a))
    elif kind == "card":
        top_a = 118 if hovered else 92
        bot_a = 138 if hovered else 110
        bg_grad.setColorAt(0.0, QColor(125, 132, 144, top_a))
        bg_grad.setColorAt(1.0, QColor(64, 70, 80, bot_a))
    else:  # "panel"
        bg_grad.setColorAt(0.0, QColor(62, 66, 74, 168))
        bg_grad.setColorAt(0.5, QColor(42, 45, 52, 182))
        bg_grad.setColorAt(1.0, QColor(28, 30, 36, 195))

    painter.fillPath(path, QBrush(bg_grad))

    # 2. Curved Optical Lens Top Highlight (gives the thick liquid-droplet curvature)
    lens_rect = QRectF(rect.left() + 2, rect.top() + 1, rect.width() - 4, rect.height() * 0.48)
    lens_grad = QLinearGradient(lens_rect.topLeft(), lens_rect.bottomLeft())
    lens_grad.setColorAt(0.0, QColor(255, 255, 255, 68 if kind == "capsule" else 44))
    lens_grad.setColorAt(0.5, QColor(255, 255, 255, 14))
    lens_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.save()
    painter.setClipPath(path)
    painter.fillRect(lens_rect, QBrush(lens_grad))

    # 3. Subtle Bottom Inner Refraction Shadow & Edge Bounce
    bot_rect = QRectF(rect.left(), rect.bottom() - 14, rect.width(), 14)
    bot_grad = QLinearGradient(bot_rect.topLeft(), bot_rect.bottomLeft())
    bot_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
    bot_grad.setColorAt(0.7, QColor(0, 0, 0, 28))
    bot_grad.setColorAt(1.0, QColor(255, 255, 255, 24))
    painter.fillRect(bot_rect, QBrush(bot_grad))
    painter.restore()

    # 4. Crisp 3D Specular Glass Rim (bright white-silver top-left edge, subtle dark side, bright bottom-right reflection)
    rim_grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    rim_top = 210 if (hovered or kind == "capsule") else 175
    rim_grad.setColorAt(0.00, QColor(255, 255, 255, rim_top))
    rim_grad.setColorAt(0.28, QColor(255, 255, 255, 85))
    rim_grad.setColorAt(0.55, QColor(20, 22, 26, 70))
    rim_grad.setColorAt(0.82, QColor(255, 255, 255, 55))
    rim_grad.setColorAt(1.00, QColor(255, 255, 255, 130))

    painter.setPen(QPen(QBrush(rim_grad), 1.35 if kind == "capsule" else 1.25))
    painter.drawPath(path)
    painter.restore()


class SmartInputWorker(QThread):
    finished = Signal(dict)

    def __init__(self, text: str, force_mode: str = "auto"):
        super().__init__()
        self.text = text
        self.force_mode = force_mode

    def run(self):
        try:
            if self.force_mode == "question" or (self.force_mode == "auto" and ai.is_question_text(self.text)):
                res = ask_brain_agent(self.text.lstrip("?").strip())
                res["worker_mode"] = "question"
            else:
                res = ingest_drop(self.text, source_hint="HUD Input")
                res["worker_mode"] = res.get("item_kind", "idea")
            self.finished.emit(res)
        except Exception as e:
            self.finished.emit({"status": "error", "message": str(e), "worker_mode": "idea"})


class LiquidGlassFrame(QFrame):
    def __init__(self, radius: float = 28.0, kind: str = "panel", parent=None):
        super().__init__(parent)
        self.radius = radius
        self.kind = kind
        self.hovered = False

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        draw_apple_liquid_glass(painter, rect, self.radius, kind=self.kind, hovered=self.hovered)
        painter.end()


class SummaryBoxCard(QFrame):
    """
    Translucent Apple Liquid Glass card for a Task or Idea Box.
    """
    clicked = Signal(str, int)
    status_changed = Signal()
    deleted = Signal()

    def __init__(self, item: dict, kind: str = "task"):
        super().__init__()
        self.item = item
        self.kind = kind
        self.item_id = item["id"]
        self.hovered = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(7)

        top = QHBoxLayout()
        top.setSpacing(9)

        if self.kind == "task":
            status = item.get("status", "todo")
            self.chk_btn = QPushButton("x" if status == "done" else "")
            self.chk_btn.setFixedSize(20, 20)
            self.chk_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.chk_btn.clicked.connect(self._toggle_task)
            self._style_checkbox(status)
            top.addWidget(self.chk_btn)

        badge_text = "TASK" if self.kind == "task" else "IDEA"
        badge = QLabel(badge_text)
        badge.setStyleSheet(
            "color: #FFFFFF; background: rgba(255, 255, 255, 0.22); border: 1px solid rgba(255, 255, 255, 0.38); "
            "border-radius: 7px; padding: 2px 8px; font-size: 9.5px; font-weight: 700; letter-spacing: 0.5px;"
        )
        top.addWidget(badge)

        title_lbl = QLabel(item.get("title", "Untitled"))
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            f"color: #FFFFFF; font-family: '{APPLE_FONT}'; font-size: 13.5px; font-weight: 700; border: none; background: transparent;"
        )
        top.addWidget(title_lbl, 1)

        del_btn = QPushButton("x")
        del_btn.setFixedSize(22, 22)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.14);
                color: rgba(255, 255, 255, 0.80);
                border: 1px solid rgba(255, 255, 255, 0.24);
                border-radius: 11px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.28);
                color: #FFFFFF;
            }
        """)
        del_btn.clicked.connect(self._delete_item)
        top.addWidget(del_btn)
        layout.addLayout(top)

        polished_desc = (item.get("description") if self.kind == "task" else item.get("summary")) or ""
        polished_desc = polished_desc.strip()
        if polished_desc and polished_desc.lower() != item.get("title", "").strip().lower():
            desc_lbl = QLabel(polished_desc)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet(
                f"color: rgba(255, 255, 255, 0.90); font-family: '{APPLE_FONT}'; "
                "background: rgba(0, 0, 0, 0.18); border: 1px solid rgba(255, 255, 255, 0.14); "
                "border-radius: 11px; padding: 8px 10px; font-size: 12px; font-weight: 500;"
            )
            layout.addWidget(desc_lbl)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        due = item.get("due_date")
        if due:
            due_lbl = QLabel(f"Complete by {due}")
            due_lbl.setStyleSheet("color: rgba(255, 255, 255, 0.80); font-size: 10.5px; font-weight: 600; border: none; background: transparent;")
            footer.addWidget(due_lbl)

        links_cnt = len(item.get("links_list") or [])
        if links_cnt > 0:
            l_lbl = QLabel(f"{links_cnt} link{'s' if links_cnt > 1 else ''}")
            l_lbl.setStyleSheet("color: #FFFFFF; font-size: 10.5px; font-weight: 600; border: none; background: transparent;")
            footer.addWidget(l_lbl)

        footer.addStretch()
        open_hint = QLabel("Details ->")
        open_hint.setStyleSheet("color: rgba(255, 255, 255, 0.72); font-size: 10.5px; font-weight: 600; border: none; background: transparent;")
        footer.addWidget(open_hint)
        layout.addLayout(footer)

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        draw_apple_liquid_glass(painter, rect, 18.0, kind="card", hovered=self.hovered)
        painter.end()

    def enterEvent(self, event):
        self.hovered = True
        self.update()

    def leaveEvent(self, event):
        self.hovered = False
        self.update()

    def _style_checkbox(self, status: str):
        if status == "done":
            self.chk_btn.setText("x")
            self.chk_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.88);
                    color: #111114;
                    border: none;
                    border-radius: 10px;
                    font-size: 11px;
                    font-weight: bold;
                }
            """)
        else:
            self.chk_btn.setText("")
            self.chk_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.14);
                    color: transparent;
                    border: 1.5px solid rgba(255, 255, 255, 0.55);
                    border-radius: 10px;
                }
                QPushButton:hover {
                    border: 1.5px solid #FFFFFF;
                    background: rgba(255, 255, 255, 0.28);
                }
            """)

    def _toggle_task(self):
        database.toggle_task_status(self.item_id)
        self.status_changed.emit()

    def _delete_item(self):
        if self.kind == "task":
            database.delete_task(self.item_id)
        else:
            database.delete_drop(self.item_id)
        self.deleted.emit()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.kind, self.item_id)
            event.accept()
        else:
            super().mousePressEvent(event)


class DetailPageWidget(QWidget):
    """
    Liquid Glass Detail Page for any Task or Idea Box:
      1. Polished Task / Idea Overview
      2. Associated Links (+ inline glass capsule to add/open links)
      3. Completion Date ("To Be Completed By") + Date Added
      4. Original Raw Text at the bottom for future reference
    """
    back_requested = Signal()
    data_mutated = Signal()

    def __init__(self):
        super().__init__()
        self.current_kind = "task"
        self.current_id = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        top_bar = QHBoxLayout()
        self.back_btn = QPushButton("< Back")
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.setFixedHeight(28)
        self.back_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.20);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.38);
                border-radius: 14px;
                font-size: 11.5px;
                font-weight: 600;
                padding: 2px 13px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.32);
                border: 1px solid rgba(255, 255, 255, 0.55);
            }
        """)
        self.back_btn.clicked.connect(self.back_requested.emit)
        top_bar.addWidget(self.back_btn)

        self.kind_badge = QLabel("DETAILS")
        self.kind_badge.setStyleSheet("color: rgba(255, 255, 255, 0.78); font-size: 10.5px; font-weight: 700; letter-spacing: 0.6px; background: transparent;")
        top_bar.addWidget(self.kind_badge)
        top_bar.addStretch()

        self.done_btn = QPushButton("Complete")
        self.done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.done_btn.setFixedHeight(28)
        self.done_btn.clicked.connect(self._toggle_complete)
        top_bar.addWidget(self.done_btn)
        outer.addLayout(top_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(268)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { border: none; background: transparent; width: 4px; }
            QScrollBar::handle:vertical { background: rgba(255, 255, 255, 0.32); border-radius: 2px; }
        """)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self.body_layout = QVBoxLayout(content)
        self.body_layout.setContentsMargins(2, 2, 4, 2)
        self.body_layout.setSpacing(10)

        glass_section_style = """
            QFrame {
                background: rgba(255, 255, 255, 0.14);
                border: 1px solid rgba(255, 255, 255, 0.28);
                border-radius: 16px;
                padding: 8px;
            }
        """

        # ── SECTION 1: Detailed Task / Idea Overview ──
        sec1 = QFrame()
        sec1.setStyleSheet(glass_section_style)
        s1_layout = QVBoxLayout(sec1)
        s1_layout.setContentsMargins(8, 6, 8, 6)
        s1_layout.setSpacing(5)

        self.detail_title = QLabel("")
        self.detail_title.setWordWrap(True)
        self.detail_title.setStyleSheet("color: #FFFFFF; font-size: 14.5px; font-weight: 700; border: none; background: transparent;")
        s1_layout.addWidget(self.detail_title)

        self.detail_desc = QLabel("")
        self.detail_desc.setWordWrap(True)
        self.detail_desc.setStyleSheet("color: rgba(255, 255, 255, 0.90); font-size: 12px; border: none; background: transparent;")
        s1_layout.addWidget(self.detail_desc)
        self.body_layout.addWidget(sec1)

        # ── SECTION 2: Associated Links ──
        sec2 = QFrame()
        sec2.setStyleSheet(glass_section_style)
        s2_layout = QVBoxLayout(sec2)
        s2_layout.setContentsMargins(8, 6, 8, 6)
        s2_layout.setSpacing(6)

        links_hdr = QLabel("ASSOCIATED LINKS")
        links_hdr.setStyleSheet("color: rgba(255, 255, 255, 0.72); font-size: 9.5px; font-weight: 700; letter-spacing: 0.6px; border: none; background: transparent;")
        s2_layout.addWidget(links_hdr)

        self.links_list_layout = QVBoxLayout()
        self.links_list_layout.setSpacing(5)
        s2_layout.addLayout(self.links_list_layout)

        link_add_row = QHBoxLayout()
        link_add_row.setSpacing(6)
        self.link_input = QLineEdit()
        self.link_input.setPlaceholderText("")
        self.link_input.setStyleSheet("""
            QLineEdit {
                background: rgba(0, 0, 0, 0.22);
                border: 1px solid rgba(255, 255, 255, 0.28);
                border-radius: 12px;
                color: #FFFFFF;
                font-size: 11.5px;
                padding: 5px 10px;
            }
            QLineEdit:focus { border: 1px solid rgba(255, 255, 255, 0.65); }
        """)
        self.link_input.returnPressed.connect(self._add_link)
        link_add_row.addWidget(self.link_input, 1)

        add_link_btn = QPushButton("+ Link")
        add_link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_link_btn.setFixedHeight(26)
        add_link_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.22);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.38);
                border-radius: 12px;
                font-size: 10.5px;
                font-weight: 600;
                padding: 2px 11px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.36); }
        """)
        add_link_btn.clicked.connect(self._add_link)
        link_add_row.addWidget(add_link_btn)
        s2_layout.addLayout(link_add_row)
        self.body_layout.addWidget(sec2)

        # ── SECTION 3: Dates (To Be Completed By + Date Added) ──
        sec3 = QFrame()
        sec3.setStyleSheet(glass_section_style)
        s3_layout = QVBoxLayout(sec3)
        s3_layout.setContentsMargins(8, 6, 8, 6)
        s3_layout.setSpacing(6)

        dates_hdr = QLabel("SCHEDULE & TIMESTAMPS")
        dates_hdr.setStyleSheet("color: rgba(255, 255, 255, 0.72); font-size: 9.5px; font-weight: 700; letter-spacing: 0.6px; border: none; background: transparent;")
        s3_layout.addWidget(dates_hdr)

        due_row = QHBoxLayout()
        due_lbl = QLabel("To Be Completed By")
        due_lbl.setStyleSheet("color: #FFFFFF; font-size: 11.5px; font-weight: 600; border: none; background: transparent;")
        due_row.addWidget(due_lbl)
        due_row.addStretch()

        self.due_edit = QLineEdit()
        self.due_edit.setPlaceholderText("YYYY-MM-DD")
        self.due_edit.setFixedWidth(115)
        self.due_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.due_edit.setStyleSheet("""
            QLineEdit {
                background: rgba(0, 0, 0, 0.22);
                border: 1px solid rgba(255, 255, 255, 0.28);
                border-radius: 9px;
                color: #FFFFFF;
                font-size: 11px;
                font-weight: 600;
                padding: 3px 6px;
            }
            QLineEdit:focus { border: 1px solid rgba(255, 255, 255, 0.65); }
        """)
        self.due_edit.editingFinished.connect(self._save_due_date)
        due_row.addWidget(self.due_edit)
        s3_layout.addLayout(due_row)

        self.created_lbl = QLabel("Date Added: —")
        self.created_lbl.setStyleSheet("color: rgba(255, 255, 255, 0.80); font-size: 11px; border: none; background: transparent;")
        s3_layout.addWidget(self.created_lbl)
        self.body_layout.addWidget(sec3)

        # ── SECTION 4: Original Raw Text at Last for Future Reference ──
        sec4 = QFrame()
        sec4.setStyleSheet("""
            QFrame {
                background: rgba(0, 0, 0, 0.20);
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 16px;
                padding: 8px;
            }
        """)
        s4_layout = QVBoxLayout(sec4)
        s4_layout.setContentsMargins(8, 5, 8, 5)
        s4_layout.setSpacing(4)

        raw_hdr = QLabel("ORIGINAL RAW TEXT (REFERENCE)")
        raw_hdr.setStyleSheet("color: rgba(255, 255, 255, 0.65); font-size: 9px; font-weight: 700; letter-spacing: 0.6px; border: none; background: transparent;")
        s4_layout.addWidget(raw_hdr)

        self.raw_text_lbl = QLabel("")
        self.raw_text_lbl.setWordWrap(True)
        self.raw_text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.raw_text_lbl.setStyleSheet("color: rgba(255, 255, 255, 0.82); font-size: 11px; font-style: italic; border: none; background: transparent;")
        s4_layout.addWidget(self.raw_text_lbl)
        self.body_layout.addWidget(sec4)

        self.body_layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def load_item(self, kind: str, item_id: int):
        self.current_kind = kind
        self.current_id = item_id

        if kind == "task":
            item = database.get_task_by_id(item_id)
            if not item:
                return
            self.kind_badge.setText("TASK DETAILS")
            self.done_btn.show()
            is_done = item.get("status") == "done"
            self.done_btn.setText("Completed" if is_done else "Mark Complete")
            self.done_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {'rgba(255, 255, 255, 0.88)' if is_done else 'rgba(255, 255, 255, 0.20)'};
                    color: {'#111114' if is_done else '#FFFFFF'};
                    border: 1px solid rgba(255, 255, 255, 0.42);
                    border-radius: 14px;
                    font-size: 11px;
                    font-weight: 600;
                    padding: 2px 12px;
                }}
            """)
            self.detail_title.setText(item.get("title", "Task"))
            self.detail_desc.setText(item.get("description") or item.get("title", ""))
            self.due_edit.setText(item.get("due_date") or "")
            self.created_lbl.setText(f"Date Added: {item.get('created_at', '—')}")
            self.raw_text_lbl.setText(f"\"{item.get('raw_text') or item.get('title', '')}\"")
            self._render_links(item.get("links_list") or [])
        else:
            item = database.get_drop_by_id(item_id)
            if not item:
                return
            self.kind_badge.setText("IDEA DETAILS")
            self.done_btn.hide()
            self.detail_title.setText(item.get("title", "Idea"))
            self.detail_desc.setText(item.get("summary") or item.get("title", ""))
            self.due_edit.setText(item.get("due_date") or "")
            self.created_lbl.setText(f"Date Added: {item.get('created_at', '—')}")
            self.raw_text_lbl.setText(f"\"{item.get('raw_content') or item.get('summary', '')}\"")
            self._render_links(item.get("links_list") or [])

    def _render_links(self, links: list[str]):
        while self.links_list_layout.count():
            child = self.links_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                while child.layout().count():
                    sub = child.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

        if not links:
            none_lbl = QLabel("No associated links yet.")
            none_lbl.setStyleSheet("color: rgba(255, 255, 255, 0.60); font-size: 11px; border: none; background: transparent;")
            self.links_list_layout.addWidget(none_lbl)
            return

        for url in links:
            row = QHBoxLayout()
            row.setSpacing(6)
            host = urlparse(url).netloc or url[:32]
            btn = QPushButton(host)
            btn.setToolTip(url)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.22);
                    color: #FFFFFF;
                    border: 1px solid rgba(255, 255, 255, 0.38);
                    border-radius: 10px;
                    font-size: 11px;
                    font-weight: 600;
                    padding: 4px 10px;
                    text-align: left;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.35);
                }
            """)
            btn.clicked.connect(lambda checked=False, u=url: webbrowser.open(u))
            row.addWidget(btn, 1)

            rm = QPushButton("x")
            rm.setFixedSize(18, 18)
            rm.setCursor(Qt.CursorShape.PointingHandCursor)
            rm.setStyleSheet("QPushButton { background: transparent; color: rgba(255, 255, 255, 0.70); border: none; font-size: 14px; } QPushButton:hover { color: #FFFFFF; }")
            rm.clicked.connect(lambda checked=False, u=url: self._remove_link(u))
            row.addWidget(rm)
            self.links_list_layout.addLayout(row)

    def _add_link(self):
        url = self.link_input.text().strip()
        if not url or self.current_id is None:
            return
        self.link_input.clear()
        if self.current_kind == "task":
            new_links = database.add_link_to_task(self.current_id, url)
        else:
            new_links = database.add_link_to_drop(self.current_id, url)
        self._render_links(new_links)
        self.data_mutated.emit()

    def _remove_link(self, url: str):
        if self.current_id is None:
            return
        if self.current_kind == "task":
            new_links = database.remove_link_from_task(self.current_id, url)
        else:
            new_links = database.remove_link_from_drop(self.current_id, url)
        self._render_links(new_links)
        self.data_mutated.emit()

    def _save_due_date(self):
        if self.current_id is None:
            return
        val = self.due_edit.text().strip() or None
        if self.current_kind == "task":
            database.update_task_due_date(self.current_id, val)
        else:
            database.update_drop_due_date(self.current_id, val)
        self.data_mutated.emit()

    def _toggle_complete(self):
        if self.current_kind == "task" and self.current_id is not None:
            database.toggle_task_status(self.current_id)
            self.load_item("task", self.current_id)
            self.data_mutated.emit()


class SpeechBubbleHUD(QWidget):
    task_updated = Signal()
    movement_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_roaming = True
        self.last_list_tab = 0
        self._ns_view_ref = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(416)
        self.setMaximumHeight(555)

        # Main Translucent Apple Liquid Glass Panel
        self.card = LiquidGlassFrame(radius=30.0, kind="panel", parent=self)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.addWidget(self.card)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(12)

        # --- TOP HEADER: Liquid Glass Capsule Controls ---
        header = QHBoxLayout()
        header.setSpacing(8)

        self.spark_badge = QLabel("Brain")
        self.spark_badge.setStyleSheet(
            f"color: #FFFFFF; font-family: '{APPLE_FONT}'; font-size: 15px; font-weight: 700; letter-spacing: -0.2px; background: transparent;"
        )
        header.addWidget(self.spark_badge)

        header.addStretch()

        # Top-Middle Liquid Glass Focus Pill
        self.focus_pill = LiquidGlassFrame(radius=14.0, kind="capsule")
        self.focus_pill.setFixedHeight(28)
        focus_layout = QHBoxLayout(self.focus_pill)
        focus_layout.setContentsMargins(10, 2, 8, 2)
        focus_layout.setSpacing(5)

        self.focus_label = QLabel("Focus: Off")
        self.focus_label.setStyleSheet(
            f"color: #FFFFFF; font-family: '{APPLE_FONT}'; font-size: 11px; font-weight: 600; border: none; background: transparent;"
        )
        focus_layout.addWidget(self.focus_label)

        self.focus_clear_btn = QPushButton("x")
        self.focus_clear_btn.setFixedSize(14, 14)
        self.focus_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.focus_clear_btn.setStyleSheet("""
            QPushButton { background: transparent; color: rgba(255, 255, 255, 0.75); border: none; font-size: 13px; font-weight: bold; }
            QPushButton:hover { color: #FFFFFF; }
        """)
        self.focus_clear_btn.clicked.connect(self._clear_focus)
        focus_layout.addWidget(self.focus_clear_btn)
        header.addWidget(self.focus_pill)

        # Top-Middle Pet Movement Toggle Capsule right beside Focus button
        self.roam_btn = QPushButton("Moving")
        self.roam_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.roam_btn.setFixedHeight(28)
        self.roam_btn.clicked.connect(self._toggle_roam_mode)
        self._update_roam_btn_style()
        header.addWidget(self.roam_btn)

        header.addStretch()

        self.close_btn = QPushButton("x")
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.22);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.42);
                border-radius: 14px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.36);
            }
        """)
        self.close_btn.clicked.connect(self.hide)
        header.addWidget(self.close_btn)

        card_layout.addLayout(header)

        # ─── LIQUID GLASS SEGMENTED CAPSULE BAR ([ Tasks ] [ Ideas ] [ Answers ]) ───
        seg_frame = LiquidGlassFrame(radius=17.0, kind="capsule")
        seg_frame.setFixedHeight(34)
        tab_bar = QHBoxLayout(seg_frame)
        tab_bar.setContentsMargins(4, 3, 4, 3)
        tab_bar.setSpacing(4)
        self.tab_buttons = {}
        for idx, label in enumerate(["Tasks", "Ideas", "Answers"]):
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda checked=False, i=idx: self._switch_tab(i))
            self.tab_buttons[idx] = btn
            tab_bar.addWidget(btn)
        card_layout.addWidget(seg_frame)

        # ─── STACKED CONTENT PAGES ───
        self.stack = QStackedWidget()

        # PAGE 0: TASKS VIEW
        self.page_tasks = QWidget()
        p0_layout = QVBoxLayout(self.page_tasks)
        p0_layout.setContentsMargins(0, 0, 0, 0)
        p0_layout.setSpacing(6)

        t_meta = QHBoxLayout()
        self.task_count = QLabel("0 tasks")
        self.task_count.setStyleSheet("color: rgba(255, 255, 255, 0.78); font-size: 11px; font-weight: 600; background: transparent;")
        t_meta.addWidget(self.task_count)
        t_meta.addStretch()

        clear_done_btn = QPushButton("Clear Completed")
        clear_done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_done_btn.setStyleSheet("""
            QPushButton { background: transparent; color: rgba(255, 255, 255, 0.75); border: none; font-size: 11px; font-weight: 500; }
            QPushButton:hover { color: #FFFFFF; }
        """)
        clear_done_btn.clicked.connect(self._clear_done_tasks)
        t_meta.addWidget(clear_done_btn)
        p0_layout.addLayout(t_meta)

        self.task_scroll = QScrollArea()
        self.task_scroll.setWidgetResizable(True)
        self.task_scroll.setFixedHeight(250)
        self.task_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { border: none; background: transparent; width: 4px; }
            QScrollBar::handle:vertical { background: rgba(255, 255, 255, 0.35); border-radius: 2px; }
        """)
        self.task_container = QWidget()
        self.task_container.setStyleSheet("background: transparent;")
        self.task_layout = QVBoxLayout(self.task_container)
        self.task_layout.setContentsMargins(0, 0, 0, 0)
        self.task_layout.setSpacing(8)
        self.task_scroll.setWidget(self.task_container)
        p0_layout.addWidget(self.task_scroll)
        self.stack.addWidget(self.page_tasks)

        # PAGE 1: IDEAS VIEW
        self.page_drops = QWidget()
        p1_layout = QVBoxLayout(self.page_drops)
        p1_layout.setContentsMargins(0, 0, 0, 0)
        p1_layout.setSpacing(6)

        self.drops_scroll = QScrollArea()
        self.drops_scroll.setWidgetResizable(True)
        self.drops_scroll.setFixedHeight(270)
        self.drops_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { border: none; background: transparent; width: 4px; }
            QScrollBar::handle:vertical { background: rgba(255, 255, 255, 0.35); border-radius: 2px; }
        """)
        self.drops_container = QWidget()
        self.drops_container.setStyleSheet("background: transparent;")
        self.drops_layout = QVBoxLayout(self.drops_container)
        self.drops_layout.setContentsMargins(0, 0, 0, 0)
        self.drops_layout.setSpacing(8)
        self.drops_scroll.setWidget(self.drops_container)
        p1_layout.addWidget(self.drops_scroll)
        self.stack.addWidget(self.page_drops)

        # PAGE 2: DIRECT ANSWERS VIEW
        self.page_agent = QWidget()
        p2_layout = QVBoxLayout(self.page_agent)
        p2_layout.setContentsMargins(0, 0, 0, 0)
        p2_layout.setSpacing(6)

        self.agent_reply_box = QLabel("")
        self.agent_reply_box.setWordWrap(True)
        self.agent_reply_box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.agent_reply_box.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.agent_reply_box.setStyleSheet(f"""
            QLabel {{
                background: rgba(255, 255, 255, 0.14);
                border: 1px solid rgba(255, 255, 255, 0.30);
                border-radius: 18px;
                color: #FFFFFF;
                font-family: "{APPLE_FONT}";
                font-size: 12.5px;
                padding: 14px;
            }}
        """)
        self.agent_reply_box.setFixedHeight(245)
        p2_layout.addWidget(self.agent_reply_box)

        self.citations_label = QLabel("")
        self.citations_label.setWordWrap(True)
        self.citations_label.setStyleSheet("color: rgba(255, 255, 255, 0.80); font-size: 10.5px; font-weight: 500; background: transparent;")
        p2_layout.addWidget(self.citations_label)
        self.stack.addWidget(self.page_agent)

        # PAGE 3: DETAILED ITEM PAGE VIEW
        self.detail_page = DetailPageWidget()
        self.detail_page.back_requested.connect(self._close_detail_page)
        self.detail_page.data_mutated.connect(self.refresh_data)
        self.stack.addWidget(self.detail_page)

        card_layout.addWidget(self.stack)

        # --- APPLE PARK LIQUID GLASS CAPSULE INPUT BAR ---
        self.input_capsule = LiquidGlassFrame(radius=23.0, kind="capsule")
        self.input_capsule.setFixedHeight(46)
        cap_layout = QHBoxLayout(self.input_capsule)
        cap_layout.setContentsMargins(16, 4, 8, 4)
        cap_layout.setSpacing(8)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("")  # Kept blank per user requirement
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: #FFFFFF;
                font-family: "{APPLE_FONT}";
                font-size: 15px;
                font-weight: 500;
                selection-background-color: rgba(255, 255, 255, 0.35);
            }}
        """)
        self.input_field.returnPressed.connect(self._submit_input)
        cap_layout.addWidget(self.input_field, 1)

        self.send_btn = QPushButton("Send")
        self.send_btn.setFixedSize(46, 32)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.25);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.48);
                border-radius: 16px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.40);
                border: 1px solid #FFFFFF;
            }
        """)
        self.send_btn.clicked.connect(self._submit_input)
        cap_layout.addWidget(self.send_btn)

        card_layout.addWidget(self.input_capsule)

        self.status_bar = QLabel("")
        self.status_bar.setStyleSheet(f"color: rgba(255, 255, 255, 0.75); font-family: '{APPLE_FONT}'; font-size: 10.5px; font-weight: 500; background: transparent;")
        card_layout.addWidget(self.status_bar)

        self._switch_tab(0)
        self.refresh_data()

    def showEvent(self, event):
        super().showEvent(event)
        enable_macos_window_blur(self, blur_radius=36)
        self.input_field.setFocus()

    def set_roaming_state(self, roaming: bool):
        self.is_roaming = roaming
        self._update_roam_btn_style()

    def _toggle_roam_mode(self):
        self.is_roaming = not self.is_roaming
        self._update_roam_btn_style()
        self.movement_toggled.emit(self.is_roaming)

    def _update_roam_btn_style(self):
        if self.is_roaming:
            self.roam_btn.setText("Moving")
            self.roam_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.28);
                    color: #FFFFFF;
                    border: 1px solid rgba(255, 255, 255, 0.52);
                    border-radius: 14px;
                    font-size: 11px;
                    font-weight: 700;
                    padding: 2px 11px;
                }
                QPushButton:hover { background: rgba(255, 255, 255, 0.38); }
            """)
        else:
            self.roam_btn.setText("Resting")
            self.roam_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.14);
                    color: rgba(255, 255, 255, 0.80);
                    border: 1px solid rgba(255, 255, 255, 0.30);
                    border-radius: 14px;
                    font-size: 11px;
                    font-weight: 600;
                    padding: 2px 11px;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.24);
                    color: #FFFFFF;
                }
            """)

    def _switch_tab(self, index: int):
        if index in (0, 1, 2):
            self.last_list_tab = index
        self.stack.setCurrentIndex(index)
        for i, btn in self.tab_buttons.items():
            if i == index:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: rgba(255, 255, 255, 0.28);
                        color: #FFFFFF;
                        border: 1px solid rgba(255, 255, 255, 0.48);
                        border-radius: 13px;
                        font-family: "{APPLE_FONT}";
                        font-size: 11.5px;
                        font-weight: 700;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent;
                        color: rgba(255, 255, 255, 0.72);
                        border: none;
                        border-radius: 13px;
                        font-family: "{APPLE_FONT}";
                        font-size: 11.5px;
                        font-weight: 600;
                    }}
                    QPushButton:hover {{ color: #FFFFFF; }}
                """)

    def _open_detail_page(self, kind: str, item_id: int):
        self.detail_page.load_item(kind, item_id)
        self.stack.setCurrentIndex(3)

    def _close_detail_page(self):
        self.refresh_data()
        self._switch_tab(self.last_list_tab)

    def refresh_data(self):
        focus = database.get_focus()
        if focus:
            self.focus_label.setText(f"Focus: {focus[:16]}")
        else:
            self.focus_label.setText("Focus: Off")

        # 1. Populate Tasks
        while self.task_layout.count():
            item = self.task_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        tasks = database.get_pending_tasks(limit=20)
        self.task_count.setText(f"{len(tasks)} pending")

        if not tasks:
            empty_lbl = QLabel("No pending tasks")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet("color: rgba(255, 255, 255, 0.65); font-size: 12px; padding: 32px 8px; background: transparent;")
            self.task_layout.addWidget(empty_lbl)
        else:
            for t in tasks:
                card = SummaryBoxCard(t, kind="task")
                card.clicked.connect(self._open_detail_page)
                card.status_changed.connect(self._on_task_toggled)
                card.deleted.connect(self.refresh_data)
                self.task_layout.addWidget(card)
        self.task_layout.addStretch()

        # 2. Populate Ideas
        while self.drops_layout.count():
            item = self.drops_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        drops = database.get_recent_drops(limit=20)
        if not drops:
            lbl = QLabel("No ideas saved yet")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: rgba(255, 255, 255, 0.65); font-size: 12px; padding: 32px 8px; background: transparent;")
            self.drops_layout.addWidget(lbl)
        else:
            for d in drops:
                card = SummaryBoxCard(d, kind="idea")
                card.clicked.connect(self._open_detail_page)
                card.deleted.connect(self.refresh_data)
                self.drops_layout.addWidget(card)
        self.drops_layout.addStretch()

    def _clear_focus(self):
        database.set_focus(None)
        self.refresh_data()

    def _clear_done_tasks(self):
        database.clear_completed_tasks()
        self.refresh_data()

    def _on_task_toggled(self):
        self.task_updated.emit()
        self.refresh_data()

    def _submit_input(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()

        if text.lower().startswith("/focus"):
            args = text[6:].strip()
            msg = handle_focus_command(args)
            self.status_bar.setText(msg)
            self.refresh_data()
            return
        elif text.lower().startswith("/remind "):
            args = text[8:].strip()
            ok = mac.create_reminder(args)
            self.status_bar.setText("Reminder created" if ok else "Reminder failed")
            self.refresh_data()
            return

        if ai.is_question_text(text):
            self._switch_tab(2)
            self.agent_reply_box.setText("Thinking...")
            self.status_bar.setText("Answering...")
            self.worker = SmartInputWorker(text, force_mode="question")
        else:
            self.status_bar.setText("Refining & saving...")
            self.worker = SmartInputWorker(text, force_mode="auto")

        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_worker_finished(self, result: dict):
        mode = result.get("worker_mode", "idea")
        if result.get("status") != "success":
            self.status_bar.setText(f"Error: {result.get('message', 'Failed')}")
            return

        if mode == "question":
            self._switch_tab(2)
            self.agent_reply_box.setText(result.get("reply", ""))
            cites = result.get("citations", [])
            self.citations_label.setText("Sources: " + " | ".join(str(c) for c in cites[:4]) if cites else "")
            self.status_bar.setText("Answered")
        elif mode == "task":
            self.refresh_data()
            self._switch_tab(0)
            self.status_bar.setText(f"Task added: {result.get('title', 'Task')[:28]}")
        else:
            self.refresh_data()
            self._switch_tab(1)
            self.status_bar.setText(f"Idea saved: {result.get('title', 'Idea')[:28]}")

    def position_above(self, target_rect: QPoint, target_size):
        screen = QApplication.screenAt(target_rect) or QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QRectF(0, 0, 1440, 900)

        x = target_rect.x() - (self.width() // 2) + (target_size.width() // 2)
        y = target_rect.y() - self.height() - 12

        min_x = int(avail.left()) + 18
        max_x = int(avail.right()) - self.width() - 18
        if x > max_x:
            x = max_x
        if x < min_x:
            x = min_x

        min_y = int(avail.top()) + 18
        max_y = int(avail.bottom()) - self.height() - 18
        if y < min_y:
            y = min(max_y, target_rect.y() + target_size.height() + 12)
        if y > max_y:
            y = max_y

        self.move(int(x), int(y))

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            if self.stack.currentIndex() == 3:
                self._close_detail_page()
            else:
                self.hide()
        else:
            super().keyPressEvent(event)
