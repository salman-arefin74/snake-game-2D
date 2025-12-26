from __future__ import annotations

import math
import os
import random
import sys
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

import pygame

from highscores import HighScoreEntry, load_highscores, save_highscore


# -----------------------------
# Config
# -----------------------------

APP_TITLE = "Snake Vibes"

CELL = 24
GRID_W = 32  # 32 * 24 = 768
GRID_H = 24  # 24 * 24 = 576

HUD_H = 96
WIN_W = GRID_W * CELL
WIN_H = GRID_H * CELL + HUD_H

FPS = 120
MOVE_HZ_START = 8.5
MOVE_HZ_MAX = 18.0

SCORE_PER_FOOD = 10


# -----------------------------
# Small utilities
# -----------------------------


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_color(c1: Tuple[int, int, int], c2: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    t = clamp(t, 0.0, 1.0)
    return (
        int(lerp(c1[0], c2[0], t)),
        int(lerp(c1[1], c2[1], t)),
        int(lerp(c1[2], c2[2], t)),
    )


def add_alpha(rgb: Tuple[int, int, int], a: int) -> Tuple[int, int, int, int]:
    return (rgb[0], rgb[1], rgb[2], int(clamp(a, 0, 255)))


def grid_to_px(x: int, y: int) -> Tuple[int, int]:
    return x * CELL, HUD_H + y * CELL


def rect_for_cell(x: int, y: int) -> pygame.Rect:
    px, py = grid_to_px(x, y)
    return pygame.Rect(px, py, CELL, CELL)


def rand_empty_cell(occupied: set[Tuple[int, int]]) -> Tuple[int, int]:
    # Guaranteed to find a spot unless grid is full.
    attempts = 0
    while True:
        x = random.randrange(0, GRID_W)
        y = random.randrange(0, GRID_H)
        if (x, y) not in occupied:
            return x, y
        attempts += 1
        if attempts > 10_000:
            # Fallback: scan (should never happen in normal gameplay)
            for yy in range(GRID_H):
                for xx in range(GRID_W):
                    if (xx, yy) not in occupied:
                        return xx, yy


def draw_rounded_rect(surf: pygame.Surface, rect: pygame.Rect, color, radius: int) -> None:
    pygame.draw.rect(surf, color, rect, border_radius=radius)


def draw_text(
    surf: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    pos: Tuple[int, int],
    color: Tuple[int, int, int],
    *,
    align: str = "topleft",
) -> pygame.Rect:
    img = font.render(text, True, color)
    r = img.get_rect()
    # pygame.Rect supports a fixed set of anchor attribute names.
    # We allow a few friendly aliases to avoid runtime crashes.
    align_map = {
        "centerleft": "midleft",
        "centerright": "midright",
        "centertop": "midtop",
        "centerbottom": "midbottom",
    }
    anchor = align_map.get(align, align)
    if hasattr(r, anchor):
        setattr(r, anchor, pos)
    else:
        # Safe fallback
        r.topleft = pos
    surf.blit(img, r)
    return r


# -----------------------------
# Game state
# -----------------------------


@dataclass
class Snake:
    body: List[Tuple[int, int]]  # head at index 0
    dir: Tuple[int, int]
    pending_dir: Optional[Tuple[int, int]] = None

    def occupied(self) -> set[Tuple[int, int]]:
        return set(self.body)

    def head(self) -> Tuple[int, int]:
        return self.body[0]

    def set_dir(self, new_dir: Tuple[int, int]) -> None:
        # Prevent reversing into itself.
        if (-new_dir[0], -new_dir[1]) == self.dir:
            return
        self.pending_dir = new_dir

    def step(self, grow: bool) -> None:
        if self.pending_dir is not None:
            self.dir = self.pending_dir
            self.pending_dir = None
        hx, hy = self.head()
        dx, dy = self.dir
        nx, ny = hx + dx, hy + dy
        self.body.insert(0, (nx, ny))
        if not grow:
            self.body.pop()


class Scene:
    START = "start"
    PLAY = "play"
    GAME_OVER = "game_over"
    HIGHSCORES = "highscores"


@dataclass
class Game:
    scene: str
    snake: Snake
    food: Tuple[int, int]
    score: int
    paused: bool

    # Timing
    move_hz: float
    move_accum: float
    # For interpolation between steps
    last_body: List[Tuple[int, int]]

    # Game-over name entry
    name: str
    saved: bool

    def reset(self) -> None:
        start_x = GRID_W // 2
        start_y = GRID_H // 2
        self.snake = Snake(body=[(start_x, start_y), (start_x - 1, start_y)], dir=(1, 0))
        self.score = 0
        self.paused = False
        self.move_hz = MOVE_HZ_START
        self.move_accum = 0.0
        self.last_body = list(self.snake.body)
        self.name = ""
        self.saved = False
        self.spawn_food()

    def spawn_food(self) -> None:
        occ = self.snake.occupied()
        self.food = rand_empty_cell(occ)


# -----------------------------
# Rendering helpers (vibes)
# -----------------------------


def make_background(size: Tuple[int, int]) -> pygame.Surface:
    w, h = size
    bg = pygame.Surface((w, h)).convert()
    top = (13, 18, 38)
    bot = (24, 10, 38)
    for y in range(h):
        t = y / max(1, h - 1)
        c = lerp_color(top, bot, t)
        pygame.draw.line(bg, c, (0, y), (w, y))
    return bg


def draw_grid(surf: pygame.Surface, tsec: float) -> None:
    # Subtle animated grid glow
    base = (255, 255, 255)
    alpha = int(22 + 10 * math.sin(tsec * 1.2))
    col = add_alpha(base, alpha)
    grid = pygame.Surface((WIN_W, WIN_H - HUD_H), pygame.SRCALPHA)
    for x in range(0, WIN_W + 1, CELL):
        pygame.draw.line(grid, col, (x, 0), (x, WIN_H - HUD_H))
    for y in range(0, WIN_H - HUD_H + 1, CELL):
        pygame.draw.line(grid, col, (0, y), (WIN_W, y))
    surf.blit(grid, (0, HUD_H))


def draw_hud(
    surf: pygame.Surface,
    font_big: pygame.font.Font,
    font: pygame.font.Font,
    score: int,
    move_hz: float,
    paused: bool,
    tsec: float,
) -> None:
    hud = pygame.Surface((WIN_W, HUD_H), pygame.SRCALPHA)
    # Glassy HUD panel
    panel = pygame.Rect(16, 16, WIN_W - 32, HUD_H - 24)
    draw_rounded_rect(hud, panel, add_alpha((10, 12, 26), 200), 18)
    pygame.draw.rect(hud, add_alpha((255, 255, 255), 34), panel, width=2, border_radius=18)

    accent = lerp_color((255, 78, 205), (0, 232, 255), 0.5 + 0.5 * math.sin(tsec * 0.9))
    # Less cramped layout: title left, paused right, stats on one line,
    # controls split across two lines.
    font_small = pygame.font.Font(None, 22)

    draw_text(hud, font_big, "SNAKE VIBES", (32, 26), accent, align="topleft")
    if paused:
        draw_text(hud, font_big, "PAUSED", (WIN_W - 32, 26), (255, 220, 120), align="topright")

    stats = f"Score: {score}    Speed: {move_hz:.1f} Hz"
    draw_text(hud, font, stats, (32, 58), (236, 240, 255), align="topleft")

    draw_text(hud, font_small, "Move: Arrows/WASD   Pause: P   Restart: R", (WIN_W - 32, 52), (170, 180, 210), align="topright")
    draw_text(hud, font_small, "High Scores: H   Quit: Esc", (WIN_W - 32, 72), (170, 180, 210), align="topright")
    surf.blit(hud, (0, 0))


def draw_food(surf: pygame.Surface, food: Tuple[int, int], tsec: float) -> None:
    x, y = food
    r = rect_for_cell(x, y)

    # Pulse
    p = 0.5 + 0.5 * math.sin(tsec * 6.0)
    glow = int(90 + 70 * p)

    base = (255, 183, 0)
    hot = (255, 60, 200)
    c = lerp_color(base, hot, p)

    gsurf = pygame.Surface((CELL * 3, CELL * 3), pygame.SRCALPHA)
    center = (CELL * 1.5, CELL * 1.5)
    for i in range(7, 0, -1):
        rr = int((CELL * 0.6) + i * 2)
        aa = int(glow * (i / 7) * 0.20)
        pygame.draw.circle(gsurf, add_alpha(c, aa), center, rr)
    surf.blit(gsurf, (r.centerx - CELL * 1.5, r.centery - CELL * 1.5))

    draw_rounded_rect(surf, r.inflate(-6, -6), add_alpha(c, 255), 10)


def draw_snake(
    surf: pygame.Surface,
    body_interp: List[Tuple[float, float]],
    dir_vec: Tuple[int, int],
    tsec: float,
) -> None:
    # Neon gradient along body
    c1 = (0, 240, 255)
    c2 = (255, 70, 220)
    c3 = (140, 255, 120)

    # Glow surface
    glow_s = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)

    for i, (gx, gy) in enumerate(body_interp):
        px = gx * CELL
        py = HUD_H + gy * CELL
        rect = pygame.Rect(px, py, CELL, CELL)

        t = i / max(1, len(body_interp) - 1)
        mid = lerp_color(c1, c2, 0.6)
        col = lerp_color(mid, c3, 0.35 + 0.35 * math.sin(tsec * 1.5 + t * 2.0))
        col = lerp_color(col, c2, t)

        # Slightly shrink segments for a modern look
        inner = rect.inflate(-6, -6)

        # Glow per segment
        g = pygame.Surface((CELL * 2, CELL * 2), pygame.SRCALPHA)
        center = (CELL, CELL)
        for k in range(6, 0, -1):
            rr = int(CELL * 0.45 + k * 2)
            aa = int(50 * (k / 6) * (1.0 - 0.7 * t))
            pygame.draw.circle(g, add_alpha(col, aa), center, rr)
        glow_s.blit(g, (rect.centerx - CELL, rect.centery - CELL))

        draw_rounded_rect(surf, inner, add_alpha(col, 255), 10)

    # Head face
    hx, hy = body_interp[0]
    head = pygame.Rect(hx * CELL, HUD_H + hy * CELL, CELL, CELL).inflate(-4, -4)
    eye_c = (10, 12, 26)
    # Eyes based on direction
    dx, dy = dir_vec
    ex_offset = 4 if dx >= 0 else -4
    ey_offset = 4 if dy >= 0 else -4
    e1 = (head.centerx + ex_offset - 6, head.centery + ey_offset - 4)
    e2 = (head.centerx + ex_offset + 2, head.centery + ey_offset - 4)
    pygame.draw.circle(surf, eye_c, e1, 3)
    pygame.draw.circle(surf, eye_c, e2, 3)

    surf.blit(glow_s, (0, 0), special_flags=pygame.BLEND_PREMULTIPLIED)


def interpolate_body(prev: List[Tuple[int, int]], cur: List[Tuple[int, int]], alpha: float) -> List[Tuple[float, float]]:
    # Interpolate by index; if lengths differ, fall back for missing.
    out: List[Tuple[float, float]] = []
    n = max(len(prev), len(cur))
    for i in range(n):
        if i < len(prev):
            px, py = prev[i]
        else:
            px, py = prev[-1]
        if i < len(cur):
            cx, cy = cur[i]
        else:
            cx, cy = cur[-1]
        out.append((lerp(px, cx, alpha), lerp(py, cy, alpha)))
    return out


# -----------------------------
# Main loop
# -----------------------------


def main() -> int:
    os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
    pygame.init()
    pygame.display.set_caption(APP_TITLE)
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    clock = pygame.time.Clock()

    font_big = pygame.font.Font(None, 44)
    font = pygame.font.Font(None, 26)
    font_mono = pygame.font.Font(None, 28)

    bg = make_background((WIN_W, WIN_H))

    g = Game(
        scene=Scene.START,
        snake=Snake(body=[(0, 0)], dir=(1, 0)),
        food=(0, 0),
        score=0,
        paused=False,
        move_hz=MOVE_HZ_START,
        move_accum=0.0,
        last_body=[],
        name="",
        saved=False,
    )
    g.reset()

    def go_start() -> None:
        g.scene = Scene.START
        g.paused = False

    def go_play() -> None:
        g.scene = Scene.PLAY
        g.paused = False

    def go_game_over() -> None:
        g.scene = Scene.GAME_OVER
        g.paused = False
        g.name = ""
        g.saved = False

    def go_highscores() -> None:
        g.scene = Scene.HIGHSCORES
        g.paused = False

    go_start()

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        tsec = pygame.time.get_ticks() / 1000.0

        # Input
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
                break

            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                    break

                if g.scene in (Scene.START, Scene.HIGHSCORES):
                    if ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                        g.reset()
                        go_play()
                    elif ev.key == pygame.K_h:
                        go_highscores()
                    elif ev.key == pygame.K_r:
                        g.reset()
                        go_start()

                elif g.scene == Scene.PLAY:
                    if ev.key in (pygame.K_UP, pygame.K_w):
                        g.snake.set_dir((0, -1))
                    elif ev.key in (pygame.K_DOWN, pygame.K_s):
                        g.snake.set_dir((0, 1))
                    elif ev.key in (pygame.K_LEFT, pygame.K_a):
                        g.snake.set_dir((-1, 0))
                    elif ev.key in (pygame.K_RIGHT, pygame.K_d):
                        g.snake.set_dir((1, 0))
                    elif ev.key == pygame.K_p:
                        g.paused = not g.paused
                    elif ev.key == pygame.K_r:
                        g.reset()
                        go_play()
                    elif ev.key == pygame.K_h:
                        go_highscores()

                elif g.scene == Scene.GAME_OVER:
                    if ev.key == pygame.K_r:
                        g.reset()
                        go_play()
                    elif ev.key == pygame.K_h:
                        go_highscores()
                    elif ev.key == pygame.K_RETURN:
                        if not g.saved:
                            save_highscore(g.name, g.score)
                            g.saved = True
                    elif ev.key == pygame.K_BACKSPACE:
                        if not g.saved and g.name:
                            g.name = g.name[:-1]
                    else:
                        # Name entry (basic, but feels native enough)
                        if not g.saved and ev.unicode:
                            ch = ev.unicode
                            if ch.isprintable() and ch not in "\r\n\t":
                                if len(g.name) < 16:
                                    g.name += ch

        # Update (gameplay)
        if g.scene == Scene.PLAY and not g.paused:
            g.move_accum += dt * g.move_hz
            while g.move_accum >= 1.0:
                g.move_accum -= 1.0

                # Snapshot for interpolation
                g.last_body = list(g.snake.body)

                # Determine if we grow this step.
                # IMPORTANT: use the *effective* direction (pending_dir takes effect on this step).
                eff_dir = g.snake.pending_dir if g.snake.pending_dir is not None else g.snake.dir
                nx, ny = g.snake.head()[0] + eff_dir[0], g.snake.head()[1] + eff_dir[1]
                will_eat = (nx, ny) == g.food

                g.snake.step(grow=will_eat)

                hx, hy = g.snake.head()

                # Wall collision -> game over (keeps gameplay crisp)
                if hx < 0 or hx >= GRID_W or hy < 0 or hy >= GRID_H:
                    go_game_over()
                    break

                # Self collision -> game over
                if (hx, hy) in g.snake.body[1:]:
                    go_game_over()
                    break

                if will_eat:
                    g.score += SCORE_PER_FOOD
                    # Slight speed-up for "modern" pacing
                    g.move_hz = clamp(g.move_hz + 0.25, MOVE_HZ_START, MOVE_HZ_MAX)
                    g.spawn_food()

        # Render
        screen.blit(bg, (0, 0))
        draw_grid(screen, tsec)

        if g.scene == Scene.START:
            draw_hud(screen, font_big, font, 0, MOVE_HZ_START, False, tsec)
            center = (WIN_W // 2, WIN_H // 2 + 30)

            accent = lerp_color((255, 78, 205), (0, 232, 255), 0.5 + 0.5 * math.sin(tsec * 1.4))
            draw_text(screen, font_big, "Press Enter to Start", center, accent, align="center")
            draw_text(screen, font, "Eat the glowing food (+10). Don’t touch yourself.", (WIN_W // 2, center[1] + 40), (230, 235, 255), align="center")
            draw_text(screen, font, "H: High Scores • Esc: Quit", (WIN_W // 2, center[1] + 70), (180, 190, 220), align="center")

        elif g.scene == Scene.PLAY:
            draw_hud(screen, font_big, font, g.score, g.move_hz, g.paused, tsec)

            # Interpolate between last and current body for smoothness
            alpha = clamp(g.move_accum, 0.0, 1.0)
            if not g.last_body:
                g.last_body = list(g.snake.body)
            body_i = interpolate_body(g.last_body, g.snake.body, alpha)

            draw_food(screen, g.food, tsec)
            draw_snake(screen, body_i, g.snake.dir, tsec)

        elif g.scene == Scene.GAME_OVER:
            draw_hud(screen, font_big, font, g.score, g.move_hz, False, tsec)

            # Dim overlay
            overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            overlay.fill(add_alpha((8, 8, 14), 160))
            screen.blit(overlay, (0, 0))

            panel = pygame.Rect(WIN_W // 2 - 280, WIN_H // 2 - 140, 560, 280)
            draw_rounded_rect(screen, panel, add_alpha((14, 16, 34), 230), 22)
            pygame.draw.rect(screen, add_alpha((255, 255, 255), 40), panel, width=2, border_radius=22)

            accent = lerp_color((255, 70, 220), (0, 240, 255), 0.5 + 0.5 * math.sin(tsec * 1.2))
            draw_text(screen, font_big, "GAME OVER", (panel.centerx, panel.top + 36), accent, align="center")
            draw_text(screen, font, f"Score: {g.score}", (panel.centerx, panel.top + 76), (236, 240, 255), align="center")

            if g.saved:
                draw_text(screen, font, "Saved!", (panel.centerx, panel.top + 116), (140, 255, 160), align="center")
                draw_text(screen, font, "Press H for High Scores or R to Restart", (panel.centerx, panel.top + 156), (210, 220, 245), align="center")
            else:
                draw_text(screen, font, "Enter your name (max 16) and press Enter to save:", (panel.centerx, panel.top + 116), (210, 220, 245), align="center")

                name_box = pygame.Rect(panel.left + 90, panel.top + 150, panel.width - 180, 44)
                draw_rounded_rect(screen, name_box, add_alpha((6, 7, 16), 230), 14)
                pygame.draw.rect(screen, add_alpha((255, 255, 255), 55), name_box, width=2, border_radius=14)

                caret = "_" if int(tsec * 2) % 2 == 0 else " "
                shown = (g.name if g.name else "PLAYER") + caret
                draw_text(screen, font_mono, shown, (name_box.centerx, name_box.centery), (240, 245, 255), align="center")

                draw_text(screen, font, "R: Restart • H: High Scores • Esc: Quit", (panel.centerx, panel.bottom - 44), (170, 180, 210), align="center")

        elif g.scene == Scene.HIGHSCORES:
            draw_hud(screen, font_big, font, g.score if g.score else 0, g.move_hz, False, tsec)

            panel = pygame.Rect(WIN_W // 2 - 320, WIN_H // 2 - 220, 640, 420)
            draw_rounded_rect(screen, panel, add_alpha((14, 16, 34), 220), 22)
            pygame.draw.rect(screen, add_alpha((255, 255, 255), 40), panel, width=2, border_radius=22)

            accent = lerp_color((0, 240, 255), (255, 70, 220), 0.5 + 0.5 * math.sin(tsec * 1.1))
            draw_text(screen, font_big, "HIGH SCORES (Top 5)", (panel.centerx, panel.top + 40), accent, align="center")

            scores = load_highscores()[:5]
            if not scores:
                draw_text(screen, font, "No scores yet — be the first!", (panel.centerx, panel.top + 120), (230, 235, 255), align="center")
            else:
                y = panel.top + 105
                for idx, e in enumerate(scores, start=1):
                    row = pygame.Rect(panel.left + 70, y, panel.width - 140, 46)
                    fill = add_alpha((10, 12, 26), 160 if idx % 2 == 0 else 120)
                    draw_rounded_rect(screen, row, fill, 14)
                    pygame.draw.rect(screen, add_alpha((255, 255, 255), 26), row, width=2, border_radius=14)
                    draw_text(screen, font, f"{idx}.", (row.left + 18, row.centery), (190, 200, 230), align="midleft")
                    draw_text(screen, font, e.name, (row.left + 58, row.centery), (240, 245, 255), align="midleft")
                    draw_text(screen, font, f"{e.score}", (row.right - 18, row.centery), (255, 220, 140), align="midright")
                    y += 56

            draw_text(screen, font, "Enter/Space: Play • R: Reset • Esc: Quit", (panel.centerx, panel.bottom - 48), (170, 180, 210), align="center")

        pygame.display.flip()

    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


