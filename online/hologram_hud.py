"""
Pepper's Ghost 4-Axis Arc Reactor Hologram HUD for Project A.R.C.
Designed for pygames 4-quadrant reflected display.
"""

import sys
import math
import time
import threading
import numpy as np

try:
    import pygame
except ImportError:
    pygame = None


class HologramHUD:
    def __init__(self, width: int = 800, height: int = 800):
        self.width = width
        self.height = height
        self.running = False
        self.thread = None
        self.state = "STANDBY"  # STANDBY, LISTENING, TRANSCRIBING, THINKING, SPEAKING, RELAY
        self.audio_amplitude = 0.0
        self.last_text = ""
        self.relay_info = ""
        self.angle = 0.0

    def start(self):
        if pygame is None:
            print("[hud] Pygame not installed. Running headless HUD mode.")
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

    def set_state(self, state: str, text: str = "", relay_info: str = ""):
        self.state = state
        if text:
            self.last_text = text
        if relay_info:
            self.relay_info = relay_info

    def set_audio_amplitude(self, amp: float):
        self.audio_amplitude = max(0.0, min(1.0, amp))

    def _run_loop(self):
        try:
            pygame.init()
        except pygame.error as exc:
            print(f"[hud] Pygame init failed: {exc}")
            return
        screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
        pygame.display.set_caption("Project A.R.C. — Pepper's Ghost Hologram HUD")
        clock = pygame.time.Clock()

        cyan = (0, 255, 224)
        cyan_dim = (0, 100, 90)
        red = (255, 45, 61)
        black = (0, 0, 0)
        white = (255, 255, 255)

        font_large = pygame.font.SysFont("monospace", 16, bold=True)
        font_small = pygame.font.SysFont("monospace", 12)

        def draw_hud_quadrant(surface, cx, cy, radius, pulse, rot_angle):
            # Outer rotating ring
            rect = pygame.Rect(cx - radius, cy - radius, radius * 2, radius * 2)
            pygame.draw.arc(surface, cyan, rect, rot_angle, rot_angle + math.pi * 1.2, 2)
            pygame.draw.arc(surface, cyan_dim, rect, rot_angle + math.pi * 1.3, rot_angle + math.pi * 1.9, 1)

            # Arc Reactor Core
            core_r = int(radius * (0.3 + 0.15 * pulse))
            pygame.draw.circle(surface, cyan if self.state != "RELAY" else red, (cx, cy), core_r, 2)
            pygame.draw.circle(surface, (0, 180, 160) if self.state != "RELAY" else (180, 30, 40), (cx, cy), max(2, int(core_r * 0.5)))

            # Inner Triangles / Segments
            num_segments = 6
            for i in range(num_segments):
                a = rot_angle * 1.5 + (i * (2 * math.pi / num_segments))
                r1 = radius * 0.45
                r2 = radius * 0.7
                x1 = cx + int(r1 * math.cos(a))
                y1 = cy + int(r1 * math.sin(a))
                x2 = cx + int(r2 * math.cos(a))
                y2 = cy + int(r2 * math.sin(a))
                pygame.draw.line(surface, cyan_dim, (x1, y1), (x2, y2), 1)

            # Text status inside quadrant
            status_surf = font_large.render(f"// {self.state}", True, cyan if self.state != "RELAY" else red)
            surface.blit(status_surf, (cx - status_surf.get_width() // 2, cy + int(radius * 0.75)))

            if self.relay_info and self.state == "RELAY":
                relay_surf = font_small.render(self.relay_info.upper(), True, red)
                surface.blit(relay_surf, (cx - relay_surf.get_width() // 2, cy + int(radius * 0.75) + 20))

        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    return

            screen.fill(black)
            w, h = screen.get_size()
            cx, cy = w // 2, h // 2
            size = min(w, h) // 4

            self.angle += 0.03
            pulse = self.audio_amplitude if self.state == "SPEAKING" else (0.5 + 0.5 * math.sin(time.time() * 4))

            # 4-Quadrant HUD for Pepper's Ghost Reflection Prism
            # Top
            draw_hud_quadrant(screen, cx, cy - size * 1.3, size, pulse, self.angle)
            # Bottom (Flipped)
            draw_hud_quadrant(screen, cx, cy + size * 1.3, size, pulse, -self.angle)
            # Left
            draw_hud_quadrant(screen, cx - size * 1.3, cy, size, pulse, self.angle * 0.8)
            # Right
            draw_hud_quadrant(screen, cx + size * 1.3, cy, size, pulse, -self.angle * 0.8)

            pygame.display.flip()
            clock.tick(30)

        pygame.quit()
