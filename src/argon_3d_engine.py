# argon_3d_engine.py — Argon Interactive 3D & 3DS Ash-Greninja Engine for Brain Desktop Pet
# Renders:
#   1. Official Nintendo 3DS #0658 Ash-Greninja 3D Model (multi-angle 3D cursor turntable + skeletal states)
#   2. Official Nintendo 3DS #0658 Shiny Black Ash-Greninja 3D Model
#   3. Procedural 3D Shinobi Rig & Argon 3D Gyroscopic Mecha-Orb
# Includes live global cursor look-at tracking, spring squish/jump physics, and water-chakra particles.

import os
import json
import math
import random
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF
from PySide6.QtGui import (
    QPainter, QColor, QBrush, QPen, QRadialGradient,
    QLinearGradient, QPolygonF, QPainterPath, QCursor, QPixmap
)

ASSETS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets"))
MANIFEST_PATH = os.path.join(ASSETS_DIR, "pet_manifest.json")


class Argon3DEngine:
    MODEL_3DS_ASH_GRENINJA = "ash_greninja_3ds"
    MODEL_3DS_SHINY_GRENINJA = "shiny_greninja_3ds"
    MODEL_GRENINJA_3D_RIG = "greninja_3d"
    MODEL_ARGON_CORE = "argon_core_3d"

    def __init__(self):
        self.active_model = self.MODEL_3DS_ASH_GRENINJA
        self.manifest = self._load_or_init_manifest()

        # Real-time 3D orientation & physics state
        self.yaw = 0.0
        self.pitch = 0.0
        self.roll = 0.0
        self.target_yaw = 0.0
        self.target_pitch = 0.0

        # Spring physics for click/drop bounce
        self.scale_spring = 1.0
        self.scale_vel = 0.0
        self.jump_y = 0.0
        self.jump_vel = 0.0

        # 3D Tongue-Scarf verlet chain nodes (x, y, z)
        self.scarf_nodes = [[0.0, 0.0, 0.0] for _ in range(8)]
        self.particles = []
        self.blink_ticks = 0

    def _load_or_init_manifest(self) -> dict:
        default_manifest = {
            "default_model": self.MODEL_3DS_ASH_GRENINJA,
            "available_models": [
                {
                    "id": "ash_greninja_3ds",
                    "name": "3DS Ash-Greninja (Interactive 3D Model + Turntable)",
                    "type": "3ds_rendered_rig",
                    "scale": 1.0,
                    "hud_offset_y": -14
                },
                {
                    "id": "shiny_greninja_3ds",
                    "name": "3DS Shiny Black Ash-Greninja (Interactive 3D Model)",
                    "type": "3ds_rendered_rig",
                    "scale": 1.0,
                    "hud_offset_y": -14
                },
                {
                    "id": "greninja_3d",
                    "name": "Argon 3D Shinobi Greninja (Vector Rig)",
                    "type": "procedural_3d_rig",
                    "scale": 1.0,
                    "hud_offset_y": -12
                },
                {
                    "id": "argon_core_3d",
                    "name": "Argon 3D Mecha-Orb (Gyroscope Core)",
                    "type": "procedural_3d_orb",
                    "scale": 1.0,
                    "hud_offset_y": -12
                }
            ],
            "states": ["idle", "wander", "eating", "thinking", "alert", "sleep"]
        }
        try:
            os.makedirs(ASSETS_DIR, exist_ok=True)
            if os.path.exists(MANIFEST_PATH):
                with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    saved = data.get("default_model", self.MODEL_3DS_ASH_GRENINJA)
                    valid_ids = {
                        self.MODEL_3DS_ASH_GRENINJA,
                        self.MODEL_3DS_SHINY_GRENINJA,
                        self.MODEL_GRENINJA_3D_RIG,
                        self.MODEL_ARGON_CORE,
                    }
                    self.active_model = saved if saved in valid_ids else self.MODEL_3DS_ASH_GRENINJA
                    return data
            else:
                with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
                    json.dump(default_manifest, f, indent=2)
        except Exception as e:
            print(f"[Argon3D] Manifest load warning: {e}")
        return default_manifest

    def set_model(self, model_id: str):
        self.active_model = model_id
        self.trigger_boop()
        try:
            self.manifest["default_model"] = model_id
            with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
                json.dump(self.manifest, f, indent=2)
        except Exception:
            pass

    def trigger_boop(self):
        """Trigger interactive 3D spring squish & jump when clicked or fed."""
        self.scale_vel = 0.20
        self.jump_vel = -7.2
        for _ in range(14):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(1.8, 4.4)
            self.particles.append({
                "x": 0.0,
                "y": 0.0,
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed - 1.2,
                "size": random.uniform(3.5, 6.5),
                "alpha": 255,
                "color": QColor(244, 63, 94) if self.active_model == self.MODEL_3DS_SHINY_GRENINJA else QColor(56, 189, 248)
            })

    def step_physics(self, widget_global_center: QPoint, state: str, frame_idx: int, vx: float = 0.0, vy: float = 0.0):
        """Update 3D cursor look-at angles, spring kinematics, and water/chakra particles."""
        cursor_pos = QCursor.pos()
        dx = cursor_pos.x() - widget_global_center.x()
        dy = cursor_pos.y() - widget_global_center.y()

        if state == "sleep":
            self.target_yaw = 0.0
            self.target_pitch = 0.25
        elif state == "wander":
            self.target_yaw = 0.50 if vx >= 0 else -0.50
            self.target_pitch = 0.05 * math.sin(frame_idx * 0.4)
        else:
            # Map horizontal cursor distance to [-0.65, +0.65] rad for 9-angle 3D turntable tracking
            self.target_yaw = max(-0.65, min(0.65, dx / 280.0))
            self.target_pitch = max(-0.40, min(0.40, dy / 280.0))

        self.yaw += (self.target_yaw - self.yaw) * 0.24
        self.pitch += (self.target_pitch - self.pitch) * 0.22
        target_roll = max(-0.32, min(0.32, -vx * 0.038))
        self.roll += (target_roll - self.roll) * 0.25

        # Spring Squish & Jump Kinematics
        spring_force = (1.0 - self.scale_spring) * 0.35
        self.scale_vel = (self.scale_vel + spring_force) * 0.72
        self.scale_spring += self.scale_vel

        if self.jump_y < 0.0 or self.jump_vel != 0.0:
            self.jump_y += self.jump_vel
            self.jump_vel += 0.95
            if self.jump_y >= 0.0:
                self.jump_y = 0.0
                self.jump_vel = 0.0
                self.scale_spring = 0.85

        if self.blink_ticks > 0:
            self.blink_ticks -= 1
        elif random.random() < 0.025:
            self.blink_ticks = 3

        # Update Scarf 3D Chain for procedural rig
        head_x = math.sin(self.yaw) * 8.0
        head_y = math.sin(self.pitch) * 5.0 + self.jump_y
        self.scarf_nodes[0] = [head_x, head_y - 2.0, 0.0]
        direction_sign = -1.0 if self.yaw >= 0 else 1.0
        for i in range(1, len(self.scarf_nodes)):
            prev = self.scarf_nodes[i - 1]
            curr = self.scarf_nodes[i]
            wave = math.sin(frame_idx * 0.38 - i * 0.65) * (3.8 if state != "sleep" else 0.8)
            wind_x = -vx * 1.4 + direction_sign * 7.5
            curr[0] += ((prev[0] + wind_x * 0.55) - curr[0]) * 0.48
            curr[1] += ((prev[1] + 2.2 + wave - vy * 0.35) - curr[1]) * 0.48
            curr[2] = -i * 2.0

        # Ambient Water / Chakra Particles
        if state in ("thinking", "eating", "alert") and frame_idx % 2 == 0:
            ang = random.uniform(0, math.tau)
            dist = 48.0 if state == "eating" else 26.0
            self.particles.append({
                "x": math.cos(ang) * dist,
                "y": math.sin(ang) * dist,
                "vx": -math.cos(ang) * 2.4 if state == "eating" else math.cos(ang) * 1.5,
                "vy": -math.sin(ang) * 2.4 if state == "eating" else -random.uniform(1.0, 2.5),
                "size": random.uniform(3.0, 6.0),
                "alpha": 235,
                "color": QColor(244, 63, 94) if state == "alert" else QColor(56, 189, 248)
            })

        alive = []
        for p in self.particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["alpha"] -= 18
            p["size"] *= 0.95
            if p["alpha"] > 15:
                alive.append(p)
        self.particles = alive

    def _project_3d(self, x: float, y: float, z: float, cx: float, cy: float, fov: float = 240.0):
        cos_y, sin_y = math.cos(self.yaw), math.sin(self.yaw)
        x1 = x * cos_y + z * sin_y
        z1 = -x * sin_y + z * cos_y

        cos_p, sin_p = math.cos(self.pitch), math.sin(self.pitch)
        y2 = y * cos_p - z1 * sin_p
        z2 = y * sin_p + z1 * cos_p

        cos_r, sin_r = math.cos(self.roll), math.sin(self.roll)
        x3 = x1 * cos_r - y2 * sin_r
        y3 = x1 * sin_r + y2 * cos_r

        scale = fov / max(60.0, fov + z2)
        px = cx + x3 * scale * self.scale_spring
        py = cy + (y3 * scale / max(0.75, 2.0 - self.scale_spring)) + self.jump_y
        return QPointF(px, py), scale, z2

    def _draw_water_shuriken(self, painter: QPainter, center: QPointF, frame_idx: int, state: str, radius: float = 42.0):
        """Draw spinning 3D translucent cyan Water Shuriken behind Ash-Greninja."""
        shuriken_speed = 0.48 if state == "thinking" else (0.30 if state == "alert" else 0.10)
        shuriken_angle = frame_idx * shuriken_speed
        painter.save()
        painter.translate(center)
        painter.rotate(math.degrees(shuriken_angle))
        sh_path = QPainterPath()
        for i in range(4):
            ang = i * (math.pi / 2.0)
            tip = QPointF(math.cos(ang) * radius, math.sin(ang) * radius)
            left = QPointF(math.cos(ang - 0.32) * (radius * 0.28), math.sin(ang - 0.32) * (radius * 0.28))
            right = QPointF(math.cos(ang + 0.32) * (radius * 0.28), math.sin(ang + 0.32) * (radius * 0.28))
            sh_path.moveTo(0, 0)
            sh_path.lineTo(left)
            sh_path.lineTo(tip)
            sh_path.lineTo(right)
            sh_path.closeSubpath()

        sh_grad = QRadialGradient(QPointF(0, 0), radius)
        if state == "alert":
            sh_grad.setColorAt(0.0, QColor(254, 202, 202, 240))
            sh_grad.setColorAt(0.5, QColor(244, 63, 94, 210))
            sh_grad.setColorAt(1.0, QColor(159, 18, 57, 70))
        else:
            sh_grad.setColorAt(0.0, QColor(224, 242, 254, 245))
            sh_grad.setColorAt(0.45, QColor(56, 189, 248, 220))
            sh_grad.setColorAt(1.0, QColor(2, 132, 199, 60))
        painter.setPen(QPen(QColor(186, 230, 253, 220), 1.5))
        painter.setBrush(QBrush(sh_grad))
        painter.drawPath(sh_path)
        painter.setBrush(QBrush(QColor(15, 23, 42, 200)))
        painter.drawEllipse(QPointF(0, 0), radius * 0.14, radius * 0.14)
        painter.restore()

    def render(
        self,
        painter: QPainter,
        width: int,
        height: int,
        state: str,
        frame_idx: int,
        sprite_frames: list = None,
        turntable_frames: list = None,
        facing_right: bool = True
    ):
        """Render the active 3DS Ash-Greninja model, Shiny 3DS model, or Argon 3D rig."""
        cx = width / 2.0
        cy = height / 2.0 + 6.0

        # 1. Dynamic 3D Ground Contact Shadow
        shadow_scale = max(0.45, 1.0 + self.jump_y / 45.0)
        shadow_grad = QRadialGradient(QPointF(cx, height - 14), 44 * shadow_scale)
        shadow_grad.setColorAt(0.0, QColor(0, 0, 0, int(155 * shadow_scale)))
        shadow_grad.setColorAt(0.65, QColor(15, 23, 42, int(75 * shadow_scale)))
        shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(shadow_grad))
        painter.drawEllipse(QPointF(cx, height - 14), 40 * shadow_scale, 11 * shadow_scale)

        if self.active_model in (self.MODEL_3DS_ASH_GRENINJA, self.MODEL_3DS_SHINY_GRENINJA) and sprite_frames:
            self._render_3ds_model(
                painter, cx, cy, width, height, state, frame_idx,
                sprite_frames, turntable_frames, facing_right
            )
        elif self.active_model == self.MODEL_ARGON_CORE:
            self._render_argon_core_3d(painter, cx, cy, state, frame_idx)
        else:
            self._render_anatomical_greninja_3d(painter, cx, cy, state, frame_idx)

        # Render foreground 3D Water / Chakra particles
        for p in self.particles:
            c = QColor(p["color"])
            c.setAlpha(max(0, min(255, int(p["alpha"]))))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(c))
            painter.drawEllipse(QPointF(cx + p["x"], cy + p["y"] + self.jump_y), p["size"], p["size"])

    def _render_3ds_model(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        width: int,
        height: int,
        state: str,
        frame_idx: int,
        sprite_frames: list,
        turntable_frames: list,
        facing_right: bool
    ):
        """
        Render the authentic Nintendo 3DS #0658 Ash-Greninja 3D renders:
        - In IDLE mode, dynamically selects from the 9-angle 3D turntable based on cursor yaw
          when the user moves their mouse near/around the pet, while breathing & blinking!
        - In WANDER, EATING, THINKING, ALERT, SLEEP, plays the full 8-frame 3DS skeletal animation.
        """
        breath = math.sin(frame_idx * 0.22) * 2.2 if state == "idle" else 0.0
        base_y = cy - 4.0 + breath + self.jump_y

        # Draw glowing 3D Water Shuriken aura behind Ash-Greninja during thinking/alert/eating
        if state in ("thinking", "alert", "eating"):
            self._draw_water_shuriken(painter, QPointF(cx, base_y - 6), frame_idx, state, radius=58.0)

        pix: QPixmap = None
        use_turntable = (
            state == "idle"
            and turntable_frames
            and len(turntable_frames) == 9
            and self.blink_ticks == 0
            and abs(self.yaw - self.target_yaw) > 0.015
        )

        if use_turntable:
            # Map yaw in [-0.65, +0.65] -> turntable index [0..8]
            norm = (self.yaw + 0.65) / 1.30
            t_idx = max(0, min(8, int(round(norm * 8))))
            pix = turntable_frames[t_idx]
        else:
            # Play skeletal 3DS animation loop (with periodic blink on frame 7 in idle)
            idx = (frame_idx // 2) % len(sprite_frames)
            pix = sprite_frames[idx]

        painter.save()
        painter.translate(cx, base_y)
        # Apply subtle 3D drag tilt (roll) and spring squash/stretch
        painter.rotate(math.degrees(self.roll * 0.55))

        flip_x = -1.0 if (state == "wander" and not facing_right) else 1.0
        sx = flip_x * self.scale_spring
        sy = 1.0 / max(0.82, self.scale_spring)
        painter.scale(sx, sy)

        target_w = pix.width()
        target_h = pix.height()
        painter.drawPixmap(-target_w // 2, -target_h // 2, target_w, target_h, pix)
        painter.restore()

    def _render_anatomical_greninja_3d(self, painter: QPainter, cx: float, cy: float, state: str, frame_idx: int):
        """Procedural 3D Shinobi Greninja fallback rig."""
        breath = math.sin(frame_idx * 0.25) * 2.2
        base_y = cy + breath

        sh_pt, _, _ = self._project_3d(0.0, -8.0, 22.0, cx, base_y)
        self._draw_water_shuriken(painter, sh_pt, frame_idx, state, radius=38.0)

        if self.scarf_nodes:
            scarf_poly = QPainterPath()
            p0 = QPointF(cx + self.scarf_nodes[0][0], base_y + self.scarf_nodes[0][1])
            scarf_poly.moveTo(p0)
            for node in self.scarf_nodes[1:]:
                scarf_poly.lineTo(QPointF(cx + node[0], base_y + node[1]))
            painter.setPen(QPen(QColor("#E11D48"), 12, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(scarf_poly)

        torso_top, t_s, _ = self._project_3d(0.0, -4.0, 0.0, cx, base_y)
        torso_bot, _, _ = self._project_3d(0.0, 20.0, 4.0, cx, base_y)
        torso_poly = QPolygonF([
            torso_top + QPointF(-19 * t_s, 0),
            torso_top + QPointF(19 * t_s, 0),
            torso_bot + QPointF(13 * t_s, 0),
            torso_bot + QPointF(-13 * t_s, 0),
        ])
        painter.setPen(QPen(QColor("#3B82F6"), 1.3))
        painter.setBrush(QBrush(QColor("#172554")))
        painter.drawPolygon(torso_poly)

        snout_tip, _, _ = self._project_3d(0.0, -8.0, -22.0, cx, base_y)
        temple_l, _, _ = self._project_3d(-22.0, -16.0, -8.0, cx, base_y)
        temple_r, _, _ = self._project_3d(22.0, -16.0, -8.0, cx, base_y)
        crown_pt, _, _ = self._project_3d(0.0, -24.0, -10.0, cx, base_y)
        painter.drawPolygon(QPolygonF([crown_pt, temple_l, snout_tip, temple_r]))

    def _render_argon_core_3d(self, painter: QPainter, cx: float, cy: float, state: str, frame_idx: int):
        """Render the Argon 3D Gyroscopic Mecha-Orb with 3D matrix-rotated orbital rings."""
        hover = math.sin(frame_idx * 0.2) * 3.5
        base_y = cy + hover

        for ring_idx, (radius, speed, color_hex) in enumerate([
            (44.0, 0.09, "#38BDF8"),
            (36.0, -0.14, "#A855F7"),
            (29.0, 0.20, "#F43F5E" if state == "alert" else "#10B981")
        ]):
            pts = []
            rot_a = frame_idx * speed + ring_idx * 1.1
            rot_b = frame_idx * (speed * 0.7) + self.yaw
            for step in range(28):
                theta = (step / 28.0) * math.tau
                rx = math.cos(theta) * radius
                ry = math.sin(theta) * radius * math.cos(rot_a)
                rz = math.sin(theta) * radius * math.sin(rot_a)
                ry2 = ry * math.cos(rot_b) - rz * math.sin(rot_b)
                rz2 = ry * math.sin(rot_b) + rz * math.cos(rot_b)
                pt, _, _ = self._project_3d(rx, ry2, rz2, cx, base_y)
                pts.append(pt)
            pts.append(pts[0])
            c = QColor(color_hex)
            c.setAlpha(185 if state != "sleep" else 90)
            painter.setPen(QPen(c, 2.0 if ring_idx == 0 else 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolyline(QPolygonF(pts))

        core_pt, c_scale, _ = self._project_3d(0.0, 0.0, 0.0, cx, base_y)
        core_grad = QRadialGradient(core_pt - QPointF(6, 8), 26 * c_scale)
        core_grad.setColorAt(0.0, QColor("#BAE6FD"))
        core_grad.setColorAt(0.45, QColor("#0284C7"))
        core_grad.setColorAt(1.0, QColor("#0F172A"))
        painter.setPen(QPen(QColor(255, 255, 255, 160), 1.4))
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(core_pt, 22 * c_scale, 22 * c_scale)
