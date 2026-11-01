#!/usr/bin/env python3
# render_3ds_greninja.py — High-Res 3DS #0658 Ash-Greninja Textured Z-Buffer & Skeletal Renderer
# Parses assets/ash_greninja_3d/Ash-Greninja/model.smd (10,814 triangles + 93 bones) and
# official Nintendo 3DS textures (Standard & Shiny) to generate:
#   - 32 animated state frames (frame_0_0.png .. frame_3_7.png) with 100% transparent alpha
#   - 9 multi-angle 3D turntable frames (turntable_0.png .. turntable_8.png) for live cursor look-at
#   - Both Standard Ash-Greninja (assets/greninja/) and Shiny Black Ash-Greninja (assets/greninja_shiny/)

import os
import math
import zipfile
from PIL import Image, ImageFilter, ImageEnhance

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
ZIP_PATH = os.path.join(ASSETS_DIR, "3DS - Pokemon Sun _ Moon - Pokemon (6th Generation) - #0658 Ash-Greninja.zip")
EXTRACT_DIR = os.path.join(ASSETS_DIR, "ash_greninja_3d", "Ash-Greninja")
SMD_PATH = os.path.join(EXTRACT_DIR, "model.smd")

LEFT_ARM_BONES = set(range(27, 43))
RIGHT_ARM_BONES = set(range(43, 59))
HEAD_BONES = {5, 6, 7, 8, 9, 10, 11, 12}
JAW_BONES = {7, 8}
SCARF_BONES = set(range(16, 25))
SHURIKEN_BONES = {59, 60} | set(range(80, 94))
LEFT_LEG_BONES = set(range(62, 71))
RIGHT_LEG_BONES = set(range(71, 80))


def ensure_extracted():
    if not os.path.exists(SMD_PATH) and os.path.exists(ZIP_PATH):
        os.makedirs(os.path.dirname(EXTRACT_DIR), exist_ok=True)
        with zipfile.ZipFile(ZIP_PATH, "r") as z:
            z.extractall(os.path.dirname(EXTRACT_DIR))


def load_smd(smd_path: str):
    """Parse all textured triangles, vertex normals, UVs, and dominant bone IDs from model.smd."""
    triangles = []
    with open(smd_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.read().splitlines()

    in_tris = False
    i = 0
    n = len(lines)
    while i < n:
        s = lines[i].strip()
        if s == "triangles":
            in_tris = True
            i += 1
            continue
        if s == "end":
            in_tris = False
            i += 1
            continue
        if in_tris:
            mat = s
            if i + 3 >= n:
                break
            verts = []
            for k in range(1, 4):
                parts = lines[i + k].strip().split()
                if len(parts) < 9:
                    break
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                nx, ny, nz = float(parts[4]), float(parts[5]), float(parts[6])
                u, v = float(parts[7]), float(parts[8])
                # Find dominant bone weight
                dom_bone = int(parts[0])
                if len(parts) >= 11:
                    num_links = int(parts[9])
                    best_w = -1.0
                    idx = 10
                    for _ in range(num_links):
                        if idx + 1 < len(parts):
                            b_id = int(parts[idx])
                            w = float(parts[idx + 1])
                            if w > best_w:
                                best_w = w
                                dom_bone = b_id
                            idx += 2
                verts.append((x, y, z, nx, ny, nz, u, v, dom_bone))
            if len(verts) == 3:
                triangles.append((mat, verts))
            i += 4
        else:
            i += 1
    return triangles


def load_textures(tex_dir: str):
    """Load 3DS textures into fast pixel lookup arrays."""
    mapping = {
        "pm0725_13_BodyA1.tga": "pm0725_13_BodyA1.tga.png",
        "pm0725_13_BodyB1.tga": "pm0725_13_BodyB1.tga.png",
        "pm0725_13_BodyC3.tga": "pm0725_13_BodyC3.tga.png",
        "pm0725_13_Eye1.tga": "pm0725_13_Eye1.tga.png",
    }
    tex_data = {}
    for mat_name, fname in mapping.items():
        p = os.path.join(tex_dir, fname)
        if os.path.exists(p):
            im = Image.open(p).convert("RGBA")
            w, h = im.size
            tex_data[mat_name] = (w, h, im.load())
    return tex_data


def rot_axis_point(x, y, z, px, py, pz, rx, ry, rz):
    """Rotate (x, y, z) around pivot (px, py, pz) by Euler angles (rx, ry, rz)."""
    dx, dy, dz = x - px, y - py, z - pz
    if rx != 0.0:
        c, s = math.cos(rx), math.sin(rx)
        dy, dz = dy * c - dz * s, dy * s + dz * c
    if ry != 0.0:
        c, s = math.cos(ry), math.sin(ry)
        dx, dz = dx * c + dz * s, -dx * s + dz * c
    if rz != 0.0:
        c, s = math.cos(rz), math.sin(rz)
        dx, dy = dx * c - dy * s, dx * s + dy * c
    return px + dx, py + dy, pz + dz


def transform_vertex(v, pose: dict):
    """
    Apply skeletal articulation to a vertex (x, y, z, nx, ny, nz, u, v, bone_id)
    and return world-rotated (wx, wy, wz, wnx, wny, wnz, u, v).
    """
    x, y, z, nx, ny, nz, u, tv, b = v

    # 1. Bring arms down from T-pose into natural Ash-Greninja ninja stance
    arm_drop = pose.get("arm_drop", 0.58)
    arm_fwd = pose.get("arm_fwd", 0.22)
    l_arm_swing = pose.get("l_arm_swing", 0.0)
    r_arm_swing = pose.get("r_arm_swing", 0.0)

    if b in LEFT_ARM_BONES:
        x, y, z = rot_axis_point(x, y, z, 13.0, -8.0, 120.0, l_arm_swing, -arm_drop, -arm_fwd)
        nx, ny, nz = rot_axis_point(nx, ny, nz, 0.0, 0.0, 0.0, l_arm_swing, -arm_drop, -arm_fwd)
    elif b in RIGHT_ARM_BONES:
        x, y, z = rot_axis_point(x, y, z, -13.0, -8.0, 120.0, r_arm_swing, arm_drop, arm_fwd)
        nx, ny, nz = rot_axis_point(nx, ny, nz, 0.0, 0.0, 0.0, r_arm_swing, arm_drop, arm_fwd)

    # 2. Head & Jaw articulation
    if b in JAW_BONES and pose.get("jaw_open", 0.0) != 0.0:
        jo = pose["jaw_open"]
        x, y, z = rot_axis_point(x, y, z, 0.0, -6.0, 136.5, jo, 0.0, 0.0)
    if b in HEAD_BONES:
        hyaw = pose.get("head_yaw", 0.0)
        hpitch = pose.get("head_pitch", 0.0)
        x, y, z = rot_axis_point(x, y, z, 0.0, -2.0, 136.0, hpitch, 0.0, hyaw)
        nx, ny, nz = rot_axis_point(nx, ny, nz, 0.0, 0.0, 0.0, hpitch, 0.0, hyaw)

    # 3. Flowing Tongue Scarf wave
    if b in SCARF_BONES:
        idx = b - 15
        swave = math.sin(pose.get("phase", 0.0) - idx * 0.55) * (1.8 * idx)
        x += swave
        z += math.cos(pose.get("phase", 0.0) - idx * 0.45) * (0.9 * idx)

    # 4. Giant Back Water Shuriken spin & scale
    if b in SHURIKEN_BONES:
        sh_spin = pose.get("shuriken_spin", 0.0)
        if sh_spin != 0.0:
            x, y, z = rot_axis_point(x, y, z, 0.0, 45.0, 82.0, 0.0, sh_spin, 0.0)
            nx, ny, nz = rot_axis_point(nx, ny, nz, 0.0, 0.0, 0.0, 0.0, sh_spin, 0.0)

    # 5. Leg stride & crouch bounce
    if b in LEFT_LEG_BONES:
        l_stride = pose.get("l_leg_stride", 0.0)
        if l_stride != 0.0:
            x, y, z = rot_axis_point(x, y, z, 18.0, -2.0, 75.0, l_stride, 0.0, 0.0)
    elif b in RIGHT_LEG_BONES:
        r_stride = pose.get("r_leg_stride", 0.0)
        if r_stride != 0.0:
            x, y, z = rot_axis_point(x, y, z, -18.0, -2.0, 75.0, r_stride, 0.0, 0.0)
    else:
        # Upper body breathing / crouch bob
        z += pose.get("body_bob", 0.0)
        lean = pose.get("torso_lean", 0.10)
        if lean != 0.0:
            x, y, z = rot_axis_point(x, y, z, 0.0, 0.0, 82.0, lean, 0.0, 0.0)
            nx, ny, nz = rot_axis_point(nx, ny, nz, 0.0, 0.0, 0.0, lean, 0.0, 0.0)

    # 6. Global Camera Yaw & Pitch around model center (0, 0, 86)
    cam_yaw = pose.get("cam_yaw", 0.28)    # Slight 3/4 dynamic angle by default
    cam_pitch = pose.get("cam_pitch", 0.08)
    x, y, z = rot_axis_point(x, y, z, 0.0, 0.0, 86.0, cam_pitch, 0.0, cam_yaw)
    nx, ny, nz = rot_axis_point(nx, ny, nz, 0.0, 0.0, 0.0, cam_pitch, 0.0, cam_yaw)

    # Eye expression V offset
    if "eye_v_offset" in pose:
        tv = tv + pose["eye_v_offset"]

    return x, y, z, nx, ny, nz, u, tv


def render_frame(triangles, textures, pose: dict, out_size: int = 160) -> Image.Image:
    """
    Rasterize the posed 10,814-triangle 3DS Ash-Greninja model at 2x supersampled resolution
    with per-pixel Z-buffering, UV texture lookup, cel-toon shading, rim light, and crisp outline.
    """
    ss = 2
    W = out_size * ss
    H = out_size * ss
    zbuf = [1e9] * (W * H)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pix = img.load()

    # Camera projection constants (-Y is toward camera, Z is up, X is right)
    fov_scale = W * 1.62
    cam_dist = 275.0
    cx = W * 0.50
    cy = H * 0.54

    # Directional key light (from front-top-left)
    lx, ly, lz = -0.38, -0.78, 0.50

    for mat, verts in triangles:
        tex = textures.get(mat)
        if not tex:
            continue
        tw, th, tpix = tex
        is_eye = ("Eye" in mat)

        tv0 = transform_vertex(verts[0], pose)
        tv1 = transform_vertex(verts[1], pose)
        tv2 = transform_vertex(verts[2], pose)

        # Project to screen space (depth = y + cam_dist since -Y is front)
        d0 = tv0[1] + cam_dist
        d1 = tv1[1] + cam_dist
        d2 = tv2[1] + cam_dist
        if d0 <= 20.0 or d1 <= 20.0 or d2 <= 20.0:
            continue

        s0 = fov_scale / d0
        s1 = fov_scale / d1
        s2 = fov_scale / d2

        x0, y0 = cx + tv0[0] * s0, cy - (tv0[2] - 84.0) * s0
        x1, y1 = cx + tv1[0] * s1, cy - (tv1[2] - 84.0) * s1
        x2, y2 = cx + tv2[0] * s2, cy - (tv2[2] - 84.0) * s2

        # Bounding box in pixel coordinates
        min_x = max(0, int(min(x0, x1, x2)))
        max_x = min(W - 1, int(max(x0, x1, x2)) + 1)
        min_y = max(0, int(min(y0, y1, y2)))
        max_y = min(H - 1, int(max(y0, y1, y2)) + 1)
        if min_x > max_x or min_y > max_y:
            continue

        denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(denom) < 1e-5:
            continue
        inv_denom = 1.0 / denom

        # Average vertex normal for anime cel-shading + rim light
        nx = (tv0[3] + tv1[3] + tv2[3]) * 0.333
        ny = (tv0[4] + tv1[4] + tv2[4]) * 0.333
        nz = (tv0[5] + tv1[5] + tv2[5]) * 0.333
        nlen = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        nx, ny, nz = nx / nlen, ny / nlen, nz / nlen

        ndotl = -(nx * lx + ny * ly + nz * lz)
        # Anime 2-tone cel shading (bright & shadow step)
        if is_eye:
            shade = 1.05
        elif ndotl > 0.15:
            shade = 1.06
        elif ndotl > -0.20:
            shade = 0.90
        else:
            shade = 0.72

        # Subtle cyan chakra rim light on grazing edges
        rim = max(0.0, 1.0 - abs(ny)) ** 3.2
        rim_boost = int(rim * 28) if not is_eye else 0

        u0, v0 = tv0[6], tv0[7]
        u1, v1 = tv1[6], tv1[7]
        u2, v2 = tv2[6], tv2[7]

        for py in range(min_y, max_y + 1):
             py_f = py + 0.5
             row_offset = py * W
             for px in range(min_x, max_x + 1):
                 px_f = px + 0.5
                 w0 = ((y1 - y2) * (px_f - x2) + (x2 - x1) * (py_f - y2)) * inv_denom
                 if w0 < 0.0:
                     continue
                 w1 = ((y2 - y0) * (px_f - x2) + (x0 - x2) * (py_f - y2)) * inv_denom
                 if w1 < 0.0:
                     continue
                 w2 = 1.0 - w0 - w1
                 if w2 < 0.0:
                     continue

                 z_depth = w0 * d0 + w1 * d1 + w2 * d2
                 idx = row_offset + px
                 if z_depth < zbuf[idx]:
                     u = (w0 * u0 + w1 * u1 + w2 * u2) % 1.0
                     v = (1.0 - ((w0 * v0 + w1 * v1 + w2 * v2) % 1.0)) % 1.0
                     tx = min(tw - 1, max(0, int(u * tw)))
                     ty = min(th - 1, max(0, int(v * th)))
                     r, g, b_col, a = tpix[tx, ty]
                     if a < 30:
                         continue
                     zbuf[idx] = z_depth
                     r = min(255, int(r * shade) + rim_boost // 2)
                     g = min(255, int(g * shade) + rim_boost)
                     b_col = min(255, int(b_col * shade) + int(rim_boost * 1.4))
                     pix[px, py] = (r, g, b_col, 255)

    # Add crisp dark-navy anime silhouette outline before downsampling
    alpha = img.split()[3]
    dilated = alpha.filter(ImageFilter.MaxFilter(5))
    outline_img = Image.new("RGBA", (W, H), (11, 19, 43, 235))
    outline_img.putalpha(dilated)
    combined = Image.alpha_composite(outline_img, img)

    # Downsample 2x -> 1x with LANCZOS for silky-smooth anti-aliased edges
    final_img = combined.resize((out_size, out_size), Image.Resampling.LANCZOS)
    return final_img


def generate_all_assets():
    ensure_extracted()
    print("[3DS Renderer] Loading 10,814-triangle Ash-Greninja 3DS mesh...")
    triangles = load_smd(SMD_PATH)

    variants = [
        ("greninja", os.path.join(EXTRACT_DIR, "Textures")),
        ("greninja_shiny", os.path.join(EXTRACT_DIR, "Shiny")),
    ]

    for folder_name, tex_dir in variants:
        out_dir = os.path.join(ASSETS_DIR, folder_name)
        os.makedirs(out_dir, exist_ok=True)
        textures = load_textures(tex_dir)
        print(f"[3DS Renderer] Rendering {folder_name} 3D animation sheets & 9-angle turntable...")

        # Row 0: IDLE (8 frames — breathing, scarf wave, subtle 3/4 look, blink on frame 7)
        for c in range(8):
            phase = (c / 8.0) * math.tau
            pose = {
                "phase": phase,
                "arm_drop": 0.56,
                "arm_fwd": 0.25,
                "body_bob": math.sin(phase) * 2.5,
                "torso_lean": 0.12,
                "cam_yaw": 0.26 + math.sin(phase) * 0.06,
                "cam_pitch": 0.06,
                "shuriken_spin": phase * 0.25,
                "eye_v_offset": 0.50 if c == 7 else 0.0,
            }
            im = render_frame(triangles, textures, pose, out_size=160)
            im.save(os.path.join(out_dir, f"frame_0_{c}.png"))

        # Row 1: WANDER / SHINOBI DASH (8 frames — ninja forward lean, arms swept back, leg stride)
        for c in range(8):
            phase = (c / 8.0) * math.tau
            stride = math.sin(phase) * 0.48
            pose = {
                "phase": phase * 2.0,
                "arm_drop": 0.65,
                "arm_fwd": -0.35,  # Swept back ninja dash
                "l_arm_swing": -stride * 0.4,
                "r_arm_swing": stride * 0.4,
                "l_leg_stride": stride,
                "r_leg_stride": -stride,
                "body_bob": abs(math.cos(phase)) * 4.0 - 2.0,
                "torso_lean": 0.28,
                "cam_yaw": 0.42,
                "cam_pitch": 0.08,
                "shuriken_spin": phase,
            }
            im = render_frame(triangles, textures, pose, out_size=160)
            im.save(os.path.join(out_dir, f"frame_1_{c}.png"))

        # Row 2: EATING / BATTLE ACTION (8 frames — jaw open catch + dynamic slash)
        for c in range(8):
            phase = (c / 8.0) * math.tau
            pose = {
                "phase": phase * 2.0,
                "arm_drop": 0.35 + math.sin(phase) * 0.25,
                "arm_fwd": 0.55,
                "jaw_open": 0.32 * abs(math.sin(phase * 0.5)),
                "body_bob": math.sin(phase) * 3.5,
                "torso_lean": 0.18,
                "cam_yaw": 0.20 + math.sin(phase) * 0.15,
                "cam_pitch": 0.04,
                "shuriken_spin": phase * 2.0,
            }
            im = render_frame(triangles, textures, pose, out_size=160)
            im.save(os.path.join(out_dir, f"frame_2_{c}.png"))

        # Row 3: THINKING / SHURIKEN OVERDRIVE (8 frames — fast spinning back shuriken & focused pose)
        for c in range(8):
            phase = (c / 8.0) * math.tau
            pose = {
                "phase": phase,
                "arm_drop": 0.62,
                "arm_fwd": 0.42,
                "body_bob": math.sin(phase) * 2.0,
                "torso_lean": 0.14,
                "cam_yaw": 0.25,
                "cam_pitch": 0.08,
                "shuriken_spin": phase * 2.0,
                "eye_v_offset": 0.25,  # Focused battle eyes
            }
            im = render_frame(triangles, textures, pose, out_size=160)
            im.save(os.path.join(out_dir, f"frame_3_{c}.png"))

        # 9-Angle Interactive 3D Cursor-Tracking Turntable (turntable_0.png .. turntable_8.png)
        # Spans yaw from -0.68 rad (-39 deg) to +0.68 rad (+39 deg) with matching head turn
        for idx in range(9):
            norm = (idx - 4) / 4.0  # -1.0 to +1.0
            pose = {
                "phase": idx * 0.4,
                "arm_drop": 0.56,
                "arm_fwd": 0.25,
                "head_yaw": norm * 0.25,
                "body_bob": 0.0,
                "torso_lean": 0.12,
                "cam_yaw": norm * 0.65,
                "cam_pitch": 0.06,
                "shuriken_spin": idx * 0.2,
            }
            im = render_frame(triangles, textures, pose, out_size=160)
            im.save(os.path.join(out_dir, f"turntable_{idx}.png"))

    print("[3DS Renderer] Completed all Standard & Shiny 3DS Ash-Greninja renders!")


if __name__ == "__main__":
    generate_all_assets()
