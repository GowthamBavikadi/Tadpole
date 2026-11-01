#!/usr/bin/env python3
# generate_pixel_greninja.py — Pixel-Art Sprite Sheet Generator for Brain Desktop Pet
# Generates:
#   1. Anthropic "Clawd" Mascot (assets/clawd/) — Warm Terracotta (#D97757) pixel-art companion
#      inspired by anthropics/claude-desktop-buddy, rullerzhou-afk/clawd-on-desk & StartripAI/buddyClaw
#   2. Low Frog-Crouch Pixel-Art Greninja (assets/greninja_crouch/) & Shiny Black (assets/greninja_shiny/)
#   3. Preserves cleaned HD Pixel-Art Greninja in assets/greninja/

import os
from PIL import Image

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

PALETTE_STANDARD = {
    "O": (10, 15, 29, 255),
    "D": (23, 37, 84, 255),
    "B": (37, 99, 235, 255),
    "L": (96, 165, 250, 255),
    "W": (248, 250, 252, 255),
    "Y": (254, 240, 138, 255),
    "E": (250, 204, 21, 255),
    "P": (225, 29, 72, 255),
    "S": (244, 63, 94, 255),
    "s": (190, 18, 60, 255),
    "C": (56, 189, 248, 255),
    "c": (224, 242, 254, 255),
}

PALETTE_SHINY = {
    "O": (9, 9, 11, 255),
    "D": (24, 24, 27, 255),
    "B": (39, 39, 42, 255),
    "L": (148, 163, 184, 255),
    "W": (248, 250, 252, 255),
    "Y": (226, 232, 240, 255),
    "E": (250, 204, 21, 255),
    "P": (239, 68, 68, 255),
    "S": (220, 38, 38, 255),
    "s": (153, 27, 27, 255),
    "C": (56, 189, 248, 255),
    "c": (224, 242, 254, 255),
}

# Anthropic Claude / Clawd Official Terracotta & Warm Ivory Palette
PALETTE_CLAWD = {
    "O": (20, 20, 19, 255),       # Anthropic Warm Obsidian outline (#141413)
    "T": (217, 119, 87, 255),     # Claude Signature Terracotta (#D97757)
    "H": (235, 152, 124, 255),    # Warm Peach-Terracotta top highlight
    "S": (176, 86, 58, 255),      # Deep Terracotta lower shadow
    "W": (250, 249, 245, 255),    # Anthropic Warm Ivory (#FAF9F5)
    "E": (20, 20, 19, 255),       # Dark pixel eyes
    "G": (245, 158, 11, 255),     # Warm Amber Claude Thinking Spark (#F59E0B)
    "P": (244, 63, 94, 255),      # Heart pink reaction
}


def put_px(grid, x, y, ch, size=36):
    if 0 <= x < size and 0 <= y < size:
        grid[y][x] = ch


def draw_rect(grid, x0, y0, w, h, ch, size=36):
    for dy in range(h):
        for dx in range(w):
            put_px(grid, x0 + dx, y0 + dy, ch, size=size)


def add_outline(grid, size=36):
    outlined = [row[:] for row in grid]
    for y in range(size):
        for x in range(size):
            if grid[y][x] == ".":
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < size and 0 <= ny < size and grid[ny][nx] not in (".", "O"):
                        outlined[y][x] = "O"
                        break
    return outlined


def draw_anthropic_clawd(frame_idx: int, mode: str) -> list:
    """
    Build a 32x32 pixel-art grid of Anthropic's iconic 'Clawd' mascot
    (the blocky warm-terracotta pixel buddy from Claude Code / clawd-on-desk).
    """
    sz = 32
    grid = [["." for _ in range(sz)] for _ in range(sz)]

    if mode == "idle":
        bob = 1 if frame_idx in (2, 3, 4) else 0
    elif mode == "wander":
        bob = -1 if frame_idx % 2 == 1 else 0
    elif mode == "eating":
        bob = -2 if frame_idx % 2 == 0 else 0
    else:
        bob = 1 if frame_idx % 4 >= 2 else 0

    by = 10 + bob

    # 1. Iconic Wide Blocky Terracotta Head/Body (x=8..23, y=by..by+10)
    draw_rect(grid, 9, by, 14, 1, "H", sz)           # Top rounded highlight cap
    draw_rect(grid, 8, by + 1, 16, 8, "T", sz)       # Main terracotta body
    draw_rect(grid, 8, by + 1, 16, 1, "H", sz)       # Upper rim highlight
    draw_rect(grid, 8, by + 8, 16, 2, "S", sz)       # Lower body shadow shading

    # 2. Cute Side Pixel Arms / Claws (x=5..7 on left, x=24..26 on right)
    arm_up = -1 if (mode == "eating" or (mode == "idle" and frame_idx in (3, 4))) else 0
    draw_rect(grid, 6, by + 3 + arm_up, 2, 3, "T", sz)
    put_px(grid, 6, by + 2 + arm_up, "H", sz)
    draw_rect(grid, 24, by + 3 - arm_up, 2, 3, "T", sz)
    put_px(grid, 25, by + 2 - arm_up, "H", sz)

    # 3. Expressive Pixel Eyes (2x3 dark eyes with warm ivory glint)
    eye_shift = 1 if (mode == "wander") else 0
    if mode == "idle" and frame_idx == 7:
        # Blink
        draw_rect(grid, 11 + eye_shift, by + 5, 2, 1, "E", sz)
        draw_rect(grid, 19 + eye_shift, by + 5, 2, 1, "E", sz)
    elif mode == "eating":
        # Happy ^ ^ chevron eyes
        put_px(grid, 11, by + 5, "E", sz)
        put_px(grid, 12, by + 4, "E", sz)
        put_px(grid, 13, by + 5, "E", sz)
        put_px(grid, 19, by + 5, "E", sz)
        put_px(grid, 20, by + 4, "E", sz)
        put_px(grid, 21, by + 5, "E", sz)
    else:
        draw_rect(grid, 11 + eye_shift, by + 3, 2, 3, "E", sz)
        draw_rect(grid, 19 + eye_shift, by + 3, 2, 3, "E", sz)
        put_px(grid, 11 + eye_shift, by + 3, "W", sz)
        put_px(grid, 19 + eye_shift, by + 3, "W", sz)

    # 4. Signature 4 Scurrying Pixel Legs Underneath (x=9, 13, 17, 21)
    leg_xs = [9, 13, 17, 21]
    for i, lx in enumerate(leg_xs):
        if mode == "wander":
            step_h = 2 if (i + frame_idx) % 2 == 0 else 4
        else:
            step_h = 3
        draw_rect(grid, lx, by + 10, 2, step_h, "S", sz)
        put_px(grid, lx, by + 10, "T", sz)

    # 5. Mode-Specific Anthropic Sparkburst / Heart Emotes
    if mode == "thinking":
        # Claude's iconic starburst spark (*) floating above-right
        sx, sy = 25, by - 4
        put_px(grid, sx, sy, "W", sz)
        for d in (1, 2):
            if frame_idx % 2 == 0:
                put_px(grid, sx + d, sy, "G", sz)
                put_px(grid, sx - d, sy, "G", sz)
                put_px(grid, sx, sy + d, "G", sz)
                put_px(grid, sx, sy - d, "G", sz)
            else:
                put_px(grid, sx + 1, sy + 1, "G", sz)
                put_px(grid, sx - 1, sy - 1, "G", sz)
                put_px(grid, sx + 1, sy - 1, "G", sz)
                put_px(grid, sx - 1, sy + 1, "G", sz)
    elif mode == "eating":
        # Floating pixel heart above head
        hx, hy = 15, by - 5 - (frame_idx % 2)
        put_px(grid, hx, hy, "P", sz)
        put_px(grid, hx + 2, hy, "P", sz)
        draw_rect(grid, hx, hy + 1, 3, 1, "P", sz)
        put_px(grid, hx + 1, hy + 2, "P", sz)

    return add_outline(grid, size=sz)


def draw_crouching_greninja(frame_idx: int, mode: str) -> list:
    sz = 36
    grid = [["." for _ in range(sz)] for _ in range(sz)]

    if mode == "idle":
        bob_y = 1 if frame_idx in (2, 3, 4) else 0
        hop_y = 0
        stride = 0
    elif mode == "wander":
        hop_table = [0, -1, -2, -1, 0, 1, 0, -1]
        hop_y = hop_table[frame_idx % 8]
        bob_y = 0
        stride = 1 if (frame_idx % 4) in (0, 1) else -1
    elif mode == "eating":
        bob_y = -1 if frame_idx % 2 == 0 else 0
        hop_y = 0
        stride = 0
    else:
        bob_y = 1 if frame_idx % 4 >= 2 else 0
        hop_y = 0
        stride = 0

    by = bob_y + hop_y

    scarf_wave = [0, 1, 1, 0, -1, -1, 0, 1]
    for seg in range(11):
        sx = 13 - seg
        w_off = scarf_wave[(frame_idx + seg) % 8]
        sy = 18 + by - (seg // 3) + w_off
        draw_rect(grid, sx, sy, 2, 3, "S", sz)
        put_px(grid, sx, sy + 2, "s", sz)

    hx = 10 + stride
    hy = 22 + by
    draw_rect(grid, hx, hy, 7, 5, "D", sz)
    draw_rect(grid, hx + 1, hy + 1, 5, 3, "B", sz)
    draw_rect(grid, hx + 1, hy + 1, 2, 2, "W", sz)

    fx = 8 + stride
    fy = 27 + (hop_y if hop_y < 0 else 0)
    draw_rect(grid, fx, fy, 6, 3, "D", sz)
    draw_rect(grid, fx + 1, fy + 1, 5, 2, "B", sz)
    put_px(grid, fx - 1, fy + 2, "W", sz)
    put_px(grid, fx + 2, fy + 2, "W", sz)
    put_px(grid, fx + 5, fy + 2, "W", sz)

    draw_rect(grid, 14, 19 + by, 10, 7, "D", sz)
    draw_rect(grid, 15, 20 + by, 8, 5, "B", sz)
    draw_rect(grid, 16, 23 + by, 7, 3, "Y", sz)

    ax = 21 - stride
    ay = 22 + by
    draw_rect(grid, ax, ay, 3, 6, "B", sz)
    put_px(grid, ax + 1, ay, "W", sz)
    put_px(grid, ax + 1, ay + 1, "W", sz)
    hand_y = 28 + (hop_y if hop_y < 0 else 0)
    draw_rect(grid, ax, hand_y, 5, 2, "B", sz)
    put_px(grid, ax, hand_y + 1, "W", sz)
    put_px(grid, ax + 2, hand_y + 1, "W", sz)
    put_px(grid, ax + 4, hand_y + 1, "W", sz)

    for k in range(9):
        ex = 18 - k
        ey = 12 + by - (k // 2)
        draw_rect(grid, ex, ey, 3, 2, "D", sz)
        put_px(grid, ex + 1, ey + 1, "L", sz)
    for k in range(6):
        cx = 20 - (k // 2)
        cy = 10 + by - (k // 2)
        draw_rect(grid, cx, cy, 2, 2, "B", sz)

    draw_rect(grid, 17, 12 + by, 10, 6, "B", sz)
    draw_rect(grid, 27, 14 + by, 3, 3, "B", sz)
    draw_rect(grid, 18, 12 + by, 8, 2, "D", sz)

    put_px(grid, 21, 12 + by, "W", sz)
    put_px(grid, 22, 12 + by, "W", sz)
    put_px(grid, 23, 13 + by, "W", sz)
    put_px(grid, 24, 13 + by, "W", sz)
    put_px(grid, 25, 14 + by, "W", sz)

    if mode == "idle" and frame_idx == 7:
        put_px(grid, 23, 15 + by, "L", sz)
        put_px(grid, 24, 15 + by, "L", sz)
        put_px(grid, 25, 15 + by, "L", sz)
    else:
        draw_rect(grid, 23, 14 + by, 3, 2, "E", sz)
        put_px(grid, 24, 14 + by, "P", sz)
        put_px(grid, 24, 15 + by, "P", sz)

    draw_rect(grid, 15, 17 + by, 12, 3, "S", sz)
    draw_rect(grid, 16, 19 + by, 10, 1, "s", sz)

    if mode == "eating":
        tongue_len = 2 + (frame_idx % 4) * 2
        for tx in range(tongue_len):
            put_px(grid, 28 + tx, 16 + by, "S", sz)
            put_px(grid, 28 + tx, 17 + by, "s", sz)
    elif mode == "thinking":
        sh_x, sh_y = 14, 9 + by
        put_px(grid, sh_x, sh_y, "c", sz)
        if frame_idx % 2 == 0:
            for d in range(1, 5):
                put_px(grid, sh_x + d, sh_y, "C", sz)
                put_px(grid, sh_x - d, sh_y, "C", sz)
                put_px(grid, sh_x, sh_y + d, "C", sz)
                put_px(grid, sh_x, sh_y - d, "C", sz)
        else:
            for d in range(1, 4):
                put_px(grid, sh_x + d, sh_y + d, "C", sz)
                put_px(grid, sh_x - d, sh_y - d, "C", sz)
                put_px(grid, sh_x + d, sh_y - d, "C", sz)
                put_px(grid, sh_x - d, sh_y + d, "C", sz)

    return add_outline(grid, size=sz)


def grid_to_image(grid: list, palette: dict, out_size: int = 144) -> Image.Image:
    sz = len(grid)
    im = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    px = im.load()
    for y in range(sz):
        for x in range(sz):
            ch = grid[y][x]
            if ch in palette:
                px[x, y] = palette[ch]
    return im.resize((out_size, out_size), Image.Resampling.NEAREST)


def generate_all():
    modes = [
        (0, "idle"),
        (1, "wander"),
        (2, "eating"),
        (3, "thinking"),
    ]
    # 1. Generate Anthropic Clawd Mascot (assets/clawd)
    clawd_dir = os.path.join(ASSETS_DIR, "clawd")
    os.makedirs(clawd_dir, exist_ok=True)
    for row_idx, mode in modes:
        for c in range(8):
            grid = draw_anthropic_clawd(c, mode)
            img = grid_to_image(grid, PALETTE_CLAWD, out_size=144)
            img.save(os.path.join(clawd_dir, f"frame_{row_idx}_{c}.png"))
    print(f"[Pixel Art] Generated 32 Anthropic Clawd mascot sprites in {clawd_dir}")

    # 2. Generate Low-Crouch Greninja & Shiny Greninja
    for folder, pal in [("greninja_crouch", PALETTE_STANDARD), ("greninja_shiny", PALETTE_SHINY)]:
        out_dir = os.path.join(ASSETS_DIR, folder)
        os.makedirs(out_dir, exist_ok=True)
        for row_idx, mode in modes:
            for c in range(8):
                grid = draw_crouching_greninja(c, mode)
                img = grid_to_image(grid, pal, out_size=144)
                img.save(os.path.join(out_dir, f"frame_{row_idx}_{c}.png"))
        print(f"[Pixel Art] Generated 32 crouching Greninja sprites in {out_dir}")


if __name__ == "__main__":
    generate_all()
