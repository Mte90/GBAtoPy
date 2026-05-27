"""Debug overlay module for GBA runtime.

Provides debug graphics overlay to display:
- CPU register values
- FPS and timing information
- Memory breakpoints and watchpoints
- Execution statistics
"""

import pygame
from typing import Optional, List, Dict, Any, Tuple
import time


class DebugOverlay:
    """Manages debug overlay rendering on screen."""
    
    # Color constants
    BACKGROUND_COLOR = (0, 0, 0, 180)
    TEXT_COLOR = (255, 255, 255)
    HEADER_COLOR = (0, 255, 0, 128)
    BRIGHT_COLOR = (255, 0, 0)
    
    def __init__(self, screen: Optional[pygame.Surface] = None):
        """Initialize debug overlay.
        
        Args:
            screen: Pygame surface to draw on (optional)
        """
        self._screen = screen
        self._enabled = False
        self._font = pygame.font.Font(None, 12)
        self._small_font = pygame.font.Font(None, 10)
        self._frame_count = 0
        self._start_time: Optional[float] = None
        self._last_fps_time: float = time.time()
        self._fps = 0
        self._stats: Dict[str, Any] = {
            "cpu_cycles": 0,
            "python_ops": 0,
            "breakpoints": [],
            "watchpoints": [],
        }
    
    def enable(self) -> None:
        """Enable debug overlay."""
        self._enabled = True
    
    def disable(self) -> None:
        """Disable debug overlay."""
        self._enabled = False
    
    def is_enabled(self) -> bool:
        """Check if overlay is enabled."""
        return self._enabled
    
    def set_font(self, font: pygame.font.Font) -> None:
        """Set custom font for overlay."""
        self._font = font
        self._small_font = pygame.font.Font(None, font.get_height() - 2)
    
    def increment_frame(self) -> None:
        self._frame_count += 1
        self._start_time = self._start_time or time.time()
        current_time = time.time()
        if current_time - self._last_fps_time >= 1.0:
            self._fps = self._frame_count / (current_time - self._last_fps_time)
            self._frame_count = 0
            self._last_fps_time = current_time
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current execution statistics."""
        return self._stats.copy()
    
    def set_stats(self, stats: Dict[str, Any]) -> None:
        """Update execution statistics."""
        for key, value in stats.items():
            if key in self._stats:
                self._stats[key] = value
    
    def register_breakpoint(self, addr: int) -> None:
        """Register a memory breakpoint."""
        if "breakpoints" not in self._stats:
            self._stats["breakpoints"] = []
        self._stats["breakpoints"].append(addr)
    
    def register_watchpoint(self, addr: int) -> None:
        """Register a memory watchpoint."""
        if "watchpoints" not in self._stats:
            self._stats["watchpoints"] = []
        self._stats["watchpoints"].append(addr)
    
    def _draw_header(self, screen: pygame.Surface, title: str, y: int, color: Tuple[int, int, int, int]) -> int:
        rect = pygame.Rect(0, y, screen.get_width(), 1)
        pygame.draw.rect(screen, color, rect)
        text_surface = self._font.render(title, True, color)
        screen.blit(text_surface, (2, y + 3))
        return y + 20
    
    def _draw_label_value(self, screen: pygame.Surface, label: str, value: str, 
                          y: int, font: pygame.font.Font = None, color: Tuple[int, int, int] = None) -> int:
        if font is None:
            font = self._font
        if color is None:
            color = self.TEXT_COLOR
        label_surface = font.render(f"{label}", True, color)
        screen.blit(label_surface, (2, y))
        value_surface = font.render(value, True, color)
        screen.blit(value_surface, (50, y))
        return y + 14
    
    def _draw_section(
        self, 
        screen: pygame.Surface, 
        title: str, 
        items: List[Tuple[str, str]], 
        y: int,
        width: int = 240
    ) -> int:
        pygame.draw.rect(screen, self.HEADER_COLOR, (0, y, screen.get_width(), 1))
        pygame.draw.rect(screen, self.HEADER_COLOR, (0, y, 1, screen.get_height()))
        title_surface = self._font.render(title, True, self.TEXT_COLOR)
        screen.blit(title_surface, (2, y + 2))
        y += 16
        
        for i, (label, value) in enumerate(items):
            value_lines = self._wrap_text(value, width - 70)
            for line_num, line in enumerate(value_lines):
                if len(label) > 15:
                    label = label[:12] + "..."
                line_text = f"{label} {line}"
                if line_num > 0:
                    line_text = " " + line_text
                text_surface = self._small_font.render(line_text, True, self.TEXT_COLOR)
                screen.blit(text_surface, (2, y + line_num * 10))
            y += 10 + len(value_lines) * 10
        return y
    
    def _wrap_text(self, text: str, max_width: int) -> List[str]:
        if max_width <= 0:
            return [text]
        words = text.split()
        if len(words) <= max_width:
            return [text]
        lines = []
        current_line = words[0]
        for word in words[1:]:
            if len(current_line + " " + word) <= max_width:
                current_line += " " + word
            else:
                lines.append(current_line)
                current_line = word
        lines.append(current_line)
        return lines
    
    def draw(self) -> None:
        if not self._enabled or self._screen is None:
            return
        
        screen = self._screen
        width = screen.get_width()
        height = screen.get_height()
        
        if self._start_time:
            elapsed = time.time() - self._start_time
            elapsed_frames = self._frame_count + 1
        else:
            elapsed = 0
            elapsed_frames = 0
        
        fps_text = f"FPS: {self._fps:.1f}"
        frame_text = f"Frame: {elapsed_frames}"
        fps_surface = self._font.render(fps_text, True, self.BRIGHT_COLOR)
        frame_surface = self._font.render(frame_text, True, self.TEXT_COLOR)
        
        screen.blit(fps_surface, (2, 2))
        screen.blit(frame_surface, (50, 2))
        
        time_text = f"{elapsed:.3f}s"
        time_surface = self._small_font.render(time_text, True, self.TEXT_COLOR)
        screen.blit(time_surface, (100, 2))
        
        y = 18
        reg_items = []
        for name in ["R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11", "R12", "SP", "LR", "PC"]:
            reg_items.append((name, f"{self._get_value_at(name):08X}"))
        
        pygame.draw.rect(screen, self.HEADER_COLOR, (0, y, 1, height - y))
        pygame.draw.rect(screen, self.HEADER_COLOR, (0, y, width, 1))
        reg_title = self._font.render("CPU Registers", True, self.TEXT_COLOR)
        screen.blit(reg_title, (2, y + 2))
        y += 18
        
        for label, value in reg_items:
            label_surface = self._font.render(f"{label}", True, self.TEXT_COLOR)
            screen.blit(label_surface, (2, y))
            if label == "PC":
                value_color = self.BRIGHT_COLOR
            else:
                value_color = self.TEXT_COLOR
            value_surface = self._font.render(value, True, value_color)
            screen.blit(value_surface, (50, y))
            y += 14
        
        y = y + 14
        flags_title = self._font.render("Condition Flags", True, self.TEXT_COLOR)
        screen.blit(flags_title, (2, y + 2))
        y += 18
        
        flags_items = [("N", "Neg"), ("Z", "Zero"), ("C", "Carry"), ("V", "Overflow")]
        
        for i, (flag, name) in enumerate(flags_items):
            flag_value = "1"
            color = self.BRIGHT_COLOR if flag_value == "1" else self.TEXT_COLOR
            flag_text = f"{flag} ({name}): {flag_value}"
            flag_surface = self._font.render(flag_text, True, color)
            screen.blit(flag_surface, (2, y + i * 14))
        
        y = y + (len(flags_items) * 14) + 10
        
        if self._stats.get("breakpoints"):
            pygame.draw.rect(screen, self.HEADER_COLOR, (0, y, 1, height - y))
            pygame.draw.rect(screen, self.HEADER_COLOR, (0, y, width, 1))
            bp_title = self._font.render("Breakpoints", True, self.TEXT_COLOR)
            screen.blit(bp_title, (2, y + 2))
            y += 18
            for i, addr in enumerate(self._stats["breakpoints"]):
                bp_text = f"BP[{i}]: {addr:08X}"
                bp_surface = self._small_font.render(bp_text, True, self.TEXT_COLOR)
                screen.blit(bp_surface, (2, y + i * 12))
            y += len(self._stats["breakpoints"]) * 12 + 10
        
        if self._stats.get("watchpoints"):
            pygame.draw.rect(screen, self.HEADER_COLOR, (0, y, 1, height - y))
            pygame.draw.rect(screen, self.HEADER_COLOR, (0, y, width, 1))
            wp_title = self._font.render("Watchpoints", True, self.TEXT_COLOR)
            screen.blit(wp_title, (2, y + 2))
            y += 18
            for i, addr in enumerate(self._stats["watchpoints"]):
                wp_text = f"WP[{i}]: {addr:08X}"
                wp_surface = self._small_font.render(wp_text, True, self.TEXT_COLOR)
                screen.blit(wp_surface, (2, y + i * 12))
        
        y = height - 20
        stats_text = f"Cycles: {self._stats.get('cpu_cycles', 0):,} | Python ops: {self._stats.get('python_ops', 0):,}"
        stats_surface = self._small_font.render(stats_text, True, (100, 100, 100))
        screen.blit(stats_surface, (2, y))
        pause_surface = self._small_font.render("[P] Pause [R] Reset [ESC] Exit", True, (150, 150, 150))
        screen.blit(pause_surface, (2, y + 12))
    
    def _get_value_at(self, name: str) -> int:
        """Get register/memory value at address.
        
        Override in subclass to provide actual register/memory access.
        
        Args:
            name: Register name or memory address
            
        Returns:
            Register or memory value
        """
        return 0


def draw_registers(screen: pygame.Surface, registers: Dict[str, int], y: int = 20) -> int:
    font = pygame.font.Font(None, 12)
    
    pygame.draw.rect(screen, (0, 255, 0, 128), (0, y, 1, screen.get_height() - y))
    pygame.draw.rect(screen, (0, 255, 0, 128), (0, y, screen.get_width(), 1))
    title = font.render("CPU Registers", True, (255, 255, 255))
    screen.blit(title, (2, y + 2))
    y += 18
    
    for i in range(13):
        reg_name = f"R{i}"
        if reg_name in registers:
            reg_value = registers[reg_name]
        else:
            reg_value = 0
        label_text = font.render(f"{reg_name}", True, (255, 255, 255))
        screen.blit(label_text, (2, y))
        value_text = font.render(f"{reg_value:08X}", True, (255, 0, 0) if reg_name == "PC" else (255, 255, 255))
        screen.blit(value_text, (50, y))
        y += 14
    
    for reg_name in ["SP", "LR"]:
        if reg_name in registers:
            label_text = font.render(f"{reg_name}", True, (255, 255, 255))
            screen.blit(label_text, (2, y))
            value_text = font.render(f"{registers[reg_name]:08X}", True, (255, 255, 255))
            screen.blit(value_text, (50, y))
            y += 14
    
    if "PC" in registers:
        label_text = font.render("PC:", True, (255, 255, 255))
        screen.blit(label_text, (2, y))
        value_text = font.render(f"{registers['PC']:08X}", True, (255, 0, 0))
        screen.blit(value_text, (50, y))
        y += 14
    
    return y


def draw_fps_and_timing(screen: pygame.Surface, fps: float, frame_count: int, start_time: float, y: int = 2) -> int:
    font = pygame.font.Font(None, 12)
    small_font = pygame.font.Font(None, 10)
    
    fps_text = font.render(f"FPS: {fps:.1f}", True, (255, 0, 0))
    screen.blit(fps_text, (2, y))
    y += 12
    
    frame_text = font.render(f"Frame: {frame_count}", True, (255, 255, 255))
    screen.blit(frame_text, (50, y))
    y += 12
    
    if start_time:
        elapsed = time.time() - start_time
        elapsed_text = small_font.render(f"{elapsed:.3f}s", True, (255, 255, 255))
        screen.blit(elapsed_text, (100, y))
        y += 12
    
    return y


def debug_overlay_main_loop(screen: pygame.Surface, registers: Dict[str, int], fps: float, frame_count: int, start_time: float, enabled: bool = True) -> None:
    if not enabled:
        return
    
    overlay_alpha = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    overlay_alpha.fill((0, 0, 0, 180))
    screen.blit(overlay_alpha, (0, 0))
    
    draw_fps_and_timing(screen, fps, frame_count, start_time, y=2)
    draw_registers(screen, registers, y=18)


if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((240, 160))
    pygame.display.set_caption("GBA Debug Overlay Test")
    
    test_registers = {
        "R0": 0x12345678,
        "R1": 0x0,
        "R2": 0x0,
        "R3": 0x0,
        "R4": 0xABCD,
        "R5": 0x1234,
        "R6": 0x0,
        "R7": 0x0,
        "R8": 0xDEAD,
        "R9": 0xBEEF,
        "R10": 0xCAFEBABE,
        "R11": 0xCAFEBABE,
        "R12": 0x0,
        "SP": 0x03000000,
        "LR": 0x08000000,
        "PC": 0x08000200,
    }
    
    clock = pygame.time.Clock()
    frame_count = 0
    start_time = time.time()
    fps = 60.0
    
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                if event.key == pygame.K_r:
                    test_registers["PC"] = 0x08000000
                    test_registers["SP"] = 0x03000000
        
        frame_count += 1
        fps = clock.tick(60) / 1000.0
        
        screen.fill((30, 30, 30))
        debug_overlay_main_loop(screen, test_registers, fps, frame_count, start_time)
        pygame.display.flip()
    
    pygame.quit()
