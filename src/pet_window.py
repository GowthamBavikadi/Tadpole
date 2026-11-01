# pet_window.py — macOS Desktop Pet with Ballistic Throw Physics, Terminal-Region Roaming & Liquid Glass Pills
# Features:
#   1. 60 FPS Ballistic Throw & Momentum Physics:
#      - Tracks mouse flick velocity when dragging; releasing a flick launches the pet across the screen
#        like a thrown ball with momentum, air friction deceleration, and elastic wall bounces!
#   2. Full Terminal-Region Movement Bounds:
#      - Detects the Terminal window bounds (or full available desktop region covering the Terminal)
#        so the pet can roam and be thrown all the way across the entire Terminal window area.
#   3. Safe PyObjC pointer retention (.retain()) & Apple Liquid Glass floating status pills.

import os
import sys
import time
import math
import random
from collections import deque
from ctypes import c_void_p
from PySide6.QtWidgets import (
    QWidget, QApplication, QMenu
)
from PySide6.QtCore import Qt, QTimer, QPoint, QRect, QRectF, Signal, QThread
from PySide6.QtGui import (
    QPixmap, QPainter, QPainterPath, QColor, QBrush, QPen, QFont,
    QLinearGradient, QDragEnterEvent, QDropEvent, QMouseEvent, QTransform
)

import AppKit
import Quartz
import objc

from pet_hud import SpeechBubbleHUD, APPLE_FONT, draw_apple_liquid_glass
from brain_core import ingest_drop, VAULT_PATH
import database


class DropWorker(QThread):
    finished = Signal(dict)

    def __init__(self, raw_input: str, source_hint: str = ""):
        super().__init__()
        self.raw_input = raw_input
        self.source_hint = source_hint

    def run(self):
        try:
            res = ingest_drop(self.raw_input, source_hint=self.source_hint)
            self.finished.emit(res)
        except Exception as e:
            self.finished.emit({"status": "error", "message": str(e)})


class DesktopPetWindow(QWidget):
    STATE_IDLE = "idle"
    STATE_WANDER = "wander"
    STATE_THROWN = "thrown"
    STATE_EATING = "eating"
    STATE_THINKING = "thinking"

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Brain Desktop Pet")
        self.pet_size = 128
        self.setFixedSize(164, 164)
        self._ns_view_ref = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAcceptDrops(True)

        # ─── Single Default Sprite Bank ('greninja_crouch') ───
        self.state = self.STATE_IDLE
        self.frame_idx = 0
        self.frames = {}
        self._load_default_sprites()

        # ─── Natural Roaming & Ballistic Throw Physics State ───
        self.can_wander = True
        self.facing_right = False
        self.target_point: QPoint | None = None
        self.pause_ticks = 16
        self.bubble_toast = ""
        self.toast_timer = 0
        self.jump_y = 0.0
        self.jump_vel = 0.0

        # Ballistic Throw Velocity (px per 16ms frame) & Mouse Flick History
        self.pos_f_x = 0.0
        self.pos_f_y = 0.0
        self.throw_vx = 0.0
        self.throw_vy = 0.0
        self.drag_history = deque(maxlen=6)  # stores (timestamp, QPoint)

        self.drag_position = QPoint()
        self.is_dragging = False
        self.drag_start_pos = QPoint()

        # ─── Apple Liquid Glass HUD ───
        self.hud = SpeechBubbleHUD()
        self.hud.task_updated.connect(self._on_task_completed_badge)
        self.hud.movement_toggled.connect(self._on_hud_movement_toggled)

        self._position_default()
        self.pos_f_x = float(self.x())
        self.pos_f_y = float(self.y())
        self._apply_macos_native_flags()

        # Timer switches to 16ms (60 FPS) during a ballistic throw and 90ms during normal walk
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._on_tick)
        self.anim_timer.start(90)

    def _apply_macos_native_flags(self):
        try:
            AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
            wid = int(self.winId())
            if self._ns_view_ref is None:
                ns_view = objc.objc_object(c_void_p=wid)
                ns_view.retain()
                self._ns_view_ref = ns_view
            else:
                ns_view = self._ns_view_ref

            ns_window = ns_view.window()
            if ns_window:
                ns_window.setHidesOnDeactivate_(False)
                ns_window.setCanHide_(False)
                behavior = (
                    AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces |
                    AppKit.NSWindowCollectionBehaviorStationary |
                    AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary |
                    AppKit.NSWindowCollectionBehaviorIgnoresCycle
                )
                ns_window.setCollectionBehavior_(behavior)
                ns_window.setLevel_(AppKit.NSStatusWindowLevel)
                ns_window.orderFrontRegardless()
        except Exception as e:
            print(f"[Pet Window] PyObjC warning: {e}")

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_macos_native_flags()

    def _load_default_sprites(self):
        asset_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "greninja_crouch")
        if not os.path.exists(asset_dir):
            asset_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "greninja")

        def _get_row(row_idx):
            row_frames = []
            for c in range(8):
                p = os.path.join(asset_dir, f"frame_{row_idx}_{c}.png")
                if os.path.exists(p):
                    pix = QPixmap(p).scaled(
                        self.pet_size, self.pet_size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.FastTransformation
                    )
                    row_frames.append(pix)
            return row_frames

        self.frames = {
            self.STATE_IDLE: _get_row(0),
            self.STATE_WANDER: _get_row(1),
            self.STATE_THROWN: _get_row(1),
            self.STATE_EATING: _get_row(2),
            self.STATE_THINKING: _get_row(3),
        }

    def _get_movement_bounds(self) -> QRect:
        """
        Returns the movement boundary covering the Terminal window region (or full available desktop screen).
        Queries macOS Quartz CGWindowListCopyWindowInfo for the frontmost Terminal window; if Terminal
        is found and large, uses its exact region; otherwise uses the full available desktop screen.
        """
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QRect(0, 28, 1440, 872)

        try:
            win_list = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
                Quartz.kCGNullWindowID
            )
            for w in win_list:
                owner = str(w.get("kCGWindowOwnerName", ""))
                if owner in ("Terminal", "iTerm2", "Warp"):
                    b = w.get("kCGWindowBounds")
                    if b:
                        tw = int(b.get("Width", 0))
                        th = int(b.get("Height", 0))
                        if tw >= 450 and th >= 300:
                            tx = int(b.get("X", avail.left()))
                            ty = int(b.get("Y", avail.top()))
                            return QRect(tx, ty, tw, th)
        except Exception:
            pass

        return avail

    def _position_default(self):
        bounds = self._get_movement_bounds()
        x = bounds.right() - self.width() - 220
        y = bounds.bottom() - self.height() - 28
        self.move(max(bounds.left() + 20, x), max(bounds.top() + 20, y))

    def _pick_next_roam_target(self):
        bounds = self._get_movement_bounds()
        min_x = bounds.left() + 12
        max_x = max(min_x + 40, bounds.right() - self.width() - 12)
        min_y = bounds.top() + 16
        max_y = max(min_y + 40, bounds.bottom() - self.height() - 12)

        cur_x, cur_y = self.x(), self.y()
        angle = random.uniform(0, math.tau)
        dist = random.uniform(140, 380)
        tx = int(max(min_x, min(max_x, cur_x + math.cos(angle) * dist)))
        ty = int(max(min_y, min(max_y, cur_y + math.sin(angle) * dist * 0.75)))
        self.target_point = QPoint(tx, ty)
        self.facing_right = (tx >= cur_x)

    def _trigger_hop(self):
        self.jump_vel = -5.5

    def _on_tick(self):
        self.frame_idx += 1

        if self.toast_timer > 0:
            self.toast_timer -= 1
            if self.toast_timer == 0:
                self.bubble_toast = ""

        if self.jump_y < 0.0 or self.jump_vel != 0.0:
            self.jump_y += self.jump_vel
            self.jump_vel += 1.6
            if self.jump_y >= 0.0:
                self.jump_y = 0.0
                self.jump_vel = 0.0

        # ─── 1. BALLISTIC THROW PHYSICS (60 FPS Momentum & Wall Bounce like a thrown ball) ───
        if self.state == self.STATE_THROWN:
            if self.anim_timer.interval() != 16:
                self.anim_timer.setInterval(16)

            bounds = self._get_movement_bounds()
            min_x = float(bounds.left() + 6)
            max_x = float(max(min_x + 20, bounds.right() - self.width() - 6))
            min_y = float(bounds.top() + 6)
            max_y = float(max(min_y + 20, bounds.bottom() - self.height() - 6))

            self.pos_f_x += self.throw_vx
            self.pos_f_y += self.throw_vy

            # Elastic wall bounce on Left / Right edges of Terminal region
            if self.pos_f_x <= min_x:
                self.pos_f_x = min_x
                self.throw_vx = -self.throw_vx * 0.74
                self.facing_right = True
                self._trigger_hop()
            elif self.pos_f_x >= max_x:
                self.pos_f_x = max_x
                self.throw_vx = -self.throw_vx * 0.74
                self.facing_right = False
                self._trigger_hop()

            # Elastic wall bounce on Top / Bottom edges of Terminal region
            if self.pos_f_y <= min_y:
                self.pos_f_y = min_y
                self.throw_vy = -self.throw_vy * 0.74
                self._trigger_hop()
            elif self.pos_f_y >= max_y:
                self.pos_f_y = max_y
                self.throw_vy = -self.throw_vy * 0.74
                self._trigger_hop()

            self.facing_right = (self.throw_vx >= 0)
            self.move(int(round(self.pos_f_x)), int(round(self.pos_f_y)))
            if self.hud.isVisible():
                self.hud.position_above(self.pos(), self.size())

            # Smooth surface friction deceleration
            self.throw_vx *= 0.945
            self.throw_vy *= 0.945

            if math.hypot(self.throw_vx, self.throw_vy) < 0.75:
                self.throw_vx = 0.0
                self.throw_vy = 0.0
                self.state = self.STATE_IDLE
                self.pause_ticks = 22
                self.anim_timer.setInterval(90)

            self.update()
            return

        # ─── 2. NORMAL IDLE / AUTONOMOUS ROAMING ───
        actively_using = self.is_dragging or self.hud.isVisible() or self.state in (self.STATE_EATING, self.STATE_THINKING)

        if not self.can_wander or actively_using:
            if self.state == self.STATE_WANDER:
                self.state = self.STATE_IDLE
            target_interval = 220 if not self.can_wander and self.jump_y == 0 else 90
            if self.anim_timer.interval() != target_interval:
                self.anim_timer.setInterval(target_interval)
            self.update()
            return

        if self.anim_timer.interval() != 90:
            self.anim_timer.setInterval(90)

        if self.pause_ticks > 0:
            self.state = self.STATE_IDLE
            self.pause_ticks -= 1
            if self.pause_ticks == 0:
                self._pick_next_roam_target()
                self.state = self.STATE_WANDER
        else:
            if self.target_point is None:
                self._pick_next_roam_target()
            if self.target_point is not None:
                dx = self.target_point.x() - self.x()
                dy = self.target_point.y() - self.y()
                dist = math.hypot(dx, dy)
                step_speed = 3.2
                if dist <= step_speed + 1.0:
                    self.move(self.target_point)
                    self.pos_f_x = float(self.x())
                    self.pos_f_y = float(self.y())
                    self.target_point = None
                    self.state = self.STATE_IDLE
                    self.pause_ticks = random.randint(24, 55)
                else:
                    nx = int(round(self.x() + (dx / dist) * step_speed))
                    ny = int(round(self.y() + (dy / dist) * step_speed))
                    self.facing_right = (dx >= 0)
                    self.state = self.STATE_WANDER
                    self.move(nx, ny)
                    self.pos_f_x = float(nx)
                    self.pos_f_y = float(ny)

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

        # Ground shadow oval
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 80)))
        painter.drawEllipse((self.width() - 76) // 2, self.height() - 18, 76, 10)

        active_frames = self.frames.get(self.state) or self.frames.get(self.STATE_IDLE, [])
        if active_frames:
            idx = (self.frame_idx // 2) % len(active_frames) if self.state == self.STATE_THROWN else self.frame_idx % len(active_frames)
            pix = active_frames[idx]
            if not self.facing_right:
                pix = pix.transformed(QTransform().scale(-1, 1))

            x = (self.width() - pix.width()) // 2
            y = (self.height() - pix.height()) // 2 + 6 + int(self.jump_y)
            painter.drawPixmap(x, y, pix)

        # Apple Liquid Glass Floating Capsule Badge
        if self.bubble_toast or self.state == self.STATE_THINKING:
            label_text = self.bubble_toast if self.bubble_toast else "Saving…"
            pill_rect = QRectF(12, 4, self.width() - 24, 26)
            draw_apple_liquid_glass(painter, pill_rect, 13.0, kind="capsule", hovered=True)

            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.setPen(QColor("#FFFFFF"))
            font = QFont(APPLE_FONT, 10, QFont.Weight.DemiBold)
            painter.setFont(font)
            painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, label_text)

        painter.end()

    # ─── DRAG & DROP IDEA / TASK / FILE "FEEDING" ───
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
            self.state = self.STATE_EATING
            self._trigger_hop()
            self._show_toast("Drop to Add", 2)
            self.update()

    def dragLeaveEvent(self, event):
        self.state = self.STATE_IDLE
        self.update()

    def dropEvent(self, event: QDropEvent):
        event.acceptProposedAction()
        self.state = self.STATE_THINKING
        self._trigger_hop()
        self.update()

        dropped_text = ""
        source_hint = "Drop"

        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                first_url = urls[0]
                if first_url.isLocalFile():
                    dropped_text = first_url.toLocalFile()
                    source_hint = f"File: {os.path.basename(dropped_text)}"
                else:
                    dropped_text = first_url.toString()
                    source_hint = "Web URL"
        elif event.mimeData().hasText():
            dropped_text = event.mimeData().text()
            source_hint = "Text Drop"

        if dropped_text:
            self._show_toast("Refining…", 3)
            self.worker = DropWorker(dropped_text, source_hint=source_hint)
            self.worker.finished.connect(self._on_drop_finished)
            self.worker.start()
        else:
            self.state = self.STATE_IDLE

    def _on_drop_finished(self, result: dict):
        self.state = self.STATE_IDLE
        self._trigger_hop()
        if result.get("status") == "success":
            title = result.get("title", "Saved")
            self._show_toast(f"{title[:15]}", 3)
            self.hud.refresh_data()
            target_tab = 0 if result.get("item_kind") == "task" else 1
            self.hud._switch_tab(target_tab)
            self.hud.position_above(self.pos(), self.size())
            self.hud.show()
            self.hud.raise_()
        else:
            self._show_toast("Drop failed", 3)
        self.update()

    def _show_toast(self, text: str, seconds: int = 3):
        self.bubble_toast = text
        self.toast_timer = max(4, int(seconds * (1000 / max(1, self.anim_timer.interval()))))

    def _on_task_completed_badge(self):
        self._trigger_hop()
        self._show_toast("Completed", 2)

    def _on_hud_movement_toggled(self, should_roam: bool):
        self.can_wander = should_roam
        if self.can_wander:
            self.pause_ticks = 4
            self._show_toast("Moving", 2)
        else:
            self.state = self.STATE_IDLE
            self.target_point = None
            self._show_toast("Resting", 2)
        self.update()

    # ─── MOUSE CLICKS, DRAGGING & BALLISTIC FLICK/THROW PHYSICS ───
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.throw_vx = 0.0
            self.throw_vy = 0.0
            if self.state == self.STATE_THROWN:
                self.state = self.STATE_IDLE
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.drag_start_pos = event.globalPosition().toPoint()
            self.is_dragging = False
            self.drag_history.clear()
            self.drag_history.append((time.perf_counter(), event.globalPosition().toPoint()))
            self._trigger_hop()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton:
            curr_global = event.globalPosition().toPoint()
            if (curr_global - self.drag_start_pos).manhattanLength() > 4:
                self.is_dragging = True
                new_pos = curr_global - self.drag_position

                # Clamp manual drag within the Terminal / screen region
                bounds = self._get_movement_bounds()
                nx = max(bounds.left() + 4, min(bounds.right() - self.width() - 4, new_pos.x()))
                ny = max(bounds.top() + 4, min(bounds.bottom() - self.height() - 4, new_pos.y()))

                if nx > self.x():
                    self.facing_right = True
                elif nx < self.x():
                    self.facing_right = False

                self.move(nx, ny)
                self.pos_f_x = float(nx)
                self.pos_f_y = float(ny)
                self.drag_history.append((time.perf_counter(), curr_global))

                if self.hud.isVisible():
                    self.hud.position_above(self.pos(), self.size())
                event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.is_dragging:
                self._toggle_hud()
            else:
                self.is_dragging = False
                self.drag_history.append((time.perf_counter(), event.globalPosition().toPoint()))

                # Compute flick/throw velocity from recent pointer samples
                if len(self.drag_history) >= 2:
                    t0, p0 = self.drag_history[0]
                    t1, p1 = self.drag_history[-1]
                    dt = max(0.008, t1 - t0)
                    # Only launch if the release happened right after moving (within 120ms)
                    if dt < 0.35:
                        vx_per_sec = (p1.x() - p0.x()) / dt
                        vy_per_sec = (p1.y() - p0.y()) / dt
                        # Convert px/sec to px per 16ms frame with a punchy throw multiplier (1.45x)
                        vx_frame = (vx_per_sec * 0.016) * 1.45
                        vy_frame = (vy_per_sec * 0.016) * 1.45
                        speed = math.hypot(vx_frame, vy_frame)
                        if speed > 3.2:
                            max_speed = 62.0
                            if speed > max_speed:
                                scale = max_speed / speed
                                vx_frame *= scale
                                vy_frame *= scale
                            self.throw_vx = vx_frame
                            self.throw_vy = vy_frame
                            self.pos_f_x = float(self.x())
                            self.pos_f_y = float(self.y())
                            self.state = self.STATE_THROWN
                            self.anim_timer.setInterval(16)
                            event.accept()
                            return

                self.pause_ticks = 20
            event.accept()

    def _toggle_hud(self):
        if self.hud.isVisible():
            self.hud.hide()
        else:
            self.hud.refresh_data()
            self.hud.position_above(self.pos(), self.size())
            self.hud.show()
            self.hud.raise_()
            self.hud.activateWindow()

    def _show_context_menu(self, global_pos: QPoint):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: rgba(52, 56, 64, 225);
                border: 1px solid rgba(255, 255, 255, 0.35);
                border-radius: 14px;
                color: #FFFFFF;
                font-family: "{APPLE_FONT}";
                padding: 6px;
            }}
            QMenu::item {{
                padding: 6px 14px;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 500;
            }}
            QMenu::item:selected {{
                background: rgba(255, 255, 255, 0.25);
                color: #FFFFFF;
            }}
            QMenu::separator {{
                height: 1px;
                background: rgba(255, 255, 255, 0.18);
                margin: 4px 6px;
            }}
        """)

        action_hud = menu.addAction("Open Brain")
        action_hud.triggered.connect(self._toggle_hud)

        action_wander = menu.addAction("Rest in Place" if self.can_wander else "Allow Pet to Move")
        action_wander.triggered.connect(self._toggle_wander_from_menu)

        action_vault = menu.addAction("Open Obsidian Vault")
        action_vault.triggered.connect(self._open_vault)

        menu.addSeparator()

        action_quit = menu.addAction("Quit")
        action_quit.triggered.connect(QApplication.instance().quit)

        menu.exec(global_pos)

    def _toggle_wander_from_menu(self):
        new_state = not self.can_wander
        self.hud.set_roaming_state(new_state)
        self._on_hud_movement_toggled(new_state)

    def _open_vault(self):
        import subprocess
        subprocess.run(["open", VAULT_PATH])
