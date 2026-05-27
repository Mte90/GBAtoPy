"""GBA Runtime - Python implementation of GBA hardware"""

import pygame
from typing import Dict, Any, Optional

from .memory import Memory
from .ppu import PPU
from .apu import APU
from .dma import DMA
from .timers import Timers
from .input import Input, KEY_A, KEY_B, KEY_START, KEY_SELECT, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT
from .rom import ROM
from .interrupts import InterruptController
from .exceptions import GBARuntimeError, InvalidROMError
from .arm7tdmi import ARM7TDMI
from .arm7tdmi import ISRHandler
from .timing import initialize_timing, get_calibrator

from .text_lib import text_init, text_color, m_vsync, text_glyph_data, text_glyph, text_char, GLYPHS
from .screenshot import auto_capture_screenshot, get_capture_output_path

# Global runtime state
_runtime: Optional[Dict[str, Any]] = None
_screen: Optional[pygame.Surface] = None
_running: bool = False

_memory = Memory()
_input = Input()
_memory.attach_input(_input)

# CPSR flag variables (N, Z, C, V)
cpsr_n = False  # Negative flag
cpsr_z = False  # Zero flag
cpsr_c = False  # Carry flag
cpsr_v = False  # Overflow flag


def read_memory(addr: int) -> int:
    return _memory.read_u32(addr) if addr < 0x10000000 else 0


def write_memory(addr: int, value: int):
    if addr < 0x10000000:
        _memory.write_u32(addr, value)


def load_rom(path: str, memory=None):
    from .rom import ROM

    rom = ROM(path)
    if memory is not None:
        memory.load_rom(rom.data, 0x08000000)
    return rom


def poll_input() -> bool:
    pygame.event.pump()
    keys = pygame.key.get_pressed()
    return any(
        [
            keys[pygame.K_UP],
            keys[pygame.K_DOWN],
            keys[pygame.K_LEFT],
            keys[pygame.K_RIGHT],
            keys[pygame.K_z],
            keys[pygame.K_x],
            keys[pygame.K_RETURN],
            keys[pygame.K_RSHIFT],
        ]
    )


def create_runtime():
    """Create and return a fully configured GBA runtime"""
    memory = Memory()
    ppu = PPU(memory)
    apu = APU()
    dma = DMA()
    timers = Timers()
    input = Input()
    irq = InterruptController()
    
    # Create ISR handler and setup in IWRAM
    isr_handler = ISRHandler(memory, irq)
    
    memory.attach_ppu(ppu)
    memory.attach_apu(apu)
    memory.attach_dma(dma)
    memory.attach_timers(timers)
    memory.attach_input(input)
    memory.attach_interrupts(irq)
    timers.attach_interrupts(irq)
    memory.setup_isr_handler(isr_handler)

    cpu = ARM7TDMI(memory)

    return {
        "cpu": cpu,
        "memory": memory,
        "ppu": ppu,
        "apu": apu,
        "dma": dma,
        "timers": timers,
        "input": input,
        "irq": irq,
    }


def load_assets():
    """Load assets (palette, tiles, sprites) from generated Python files.

    This MUST be called before pygame.init() to ensure proper initialization order.
    """
    global _runtime
    if _runtime is not None:
        # Assets already loaded
        return

    # Load assets from generated code (if available)
    # These will be defined in the generated Python file
    try:
        # Import assets from generated code
        # The generated file should define: PALETTE_BG, TILES_4BPP, SPRITES, TILEMAP
        import sys
        import importlib.util

        # Try to load from generated code namespace
        if "generated_assets" in sys.modules:
            assets = sys.modules["generated_assets"]
            if hasattr(assets, "PALETTE_BG"):
                _runtime = create_runtime()
                memory = _runtime["memory"]
                # Load palette
                if hasattr(assets, "PALETTE_BG"):
                    memory.write_palette(0, assets.PALETTE_BG)
                # Load tiles
                if hasattr(assets, "TILES_4BPP"):
                    memory.write_vram(0x06000000, assets.TILES_4BPP)
                # Load sprites
                if hasattr(assets, "SPRITES"):
                    memory.write_vram(0x06018000, assets.SPRITES)
                # Load tilemap
                if hasattr(assets, "TILEMAP"):
                    memory.write_vram(0x06001800, assets.TILEMAP)
    except ImportError:
        pass  # No assets loaded, will be handled by generated code


def main_entry(
    rom_path: str, frames: int = 60, headless: bool = False, screenshot_path: Optional[str] = None
):
    """Main entry point for running a GBA ROM in Python.

    Args:
        rom_path: Path to the generated Python file (not the ROM binary)
        frames: Number of frames to run (default: 60)
        headless: Run without display (default: False)
        screenshot_path: Path to save screenshot at end (optional)
    """
    global _runtime, _screen, _running

    print(f"=== GBAtoPy Runtime ===")
    print(f"ROM: {rom_path}")
    print(f"Frames: {frames}")
    print(f"Headless: {headless}")

    # STEP 1: Load assets FIRST (before pygame init)
    print("\n[1/6] Loading assets...")
    load_assets()

    # STEP 2: Initialize pygame
    print("[2/6] Initializing pygame...")
    pygame.init()

    if not headless:
        _screen = pygame.display.set_mode((240, 160))
        pygame.display.set_caption("GBAtoPy")
    else:
        _screen = None

    # STEP 3: Create runtime
    print("[3/6] Creating runtime...")
    _runtime = create_runtime()
    cpu = _runtime["cpu"]
    memory = _runtime["memory"]
    ppu = _runtime["ppu"]
    apu = _runtime["apu"]
    input = _runtime["input"]
    
    # Initialize timing calibration
    print("[Timing] Initializing timing calibration...")
    initialize_timing()

    # STEP 4: Start APU audio (if not headless)
    if not headless:
        print("[4/6] Starting audio...")
        apu.start()

    # STEP 5: Execute the generated code
    # The generated Python file should have a main() function or func_map
    print("[5/6] Executing ROM code...")

    # Import the generated code
    import importlib.util

    spec = importlib.util.spec_from_file_location("generated_rom", rom_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load generated ROM: {rom_path}")

    generated = importlib.util.module_from_spec(spec)
    sys.modules["generated_rom"] = generated
    spec.loader.exec_module(generated)

    # Check if func_map exists and call entry point
    if hasattr(generated, "func_map") and 0x08000000 in generated.func_map:
        print("  Entry point found: func_map[0x08000000]")
        # Note: We don't call it directly here - the game loop will handle execution
    elif hasattr(generated, "main"):
        print("  Entry point found: main()")
    else:
        print("  WARNING: No entry point found in generated code")

    # STEP 6: Run game loop
    print("[6/6] Running game loop...")
    _running = True
    clock = pygame.time.Clock()

    for frame in range(frames):
        if not _running:
            print(f"\nGame stopped at frame {frame}")
            break

        # Event handling
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _running = False
                break
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    _running = False
                    break

        if not _running:
            break

        # Poll input
        input.poll()

        # Execute CPU with timeout to prevent infinite loops
        if hasattr(generated, "func_map") and 0x08000000 in generated.func_map:
            import threading

            result = {"exception": None}

            def run_rom():
                try:
                    generated.func_map[0x08000000]()
                except Exception as e:
                    result["exception"] = e

            rom_thread = threading.Thread(target=run_rom)
            rom_thread.daemon = True
            rom_thread.start()
            rom_thread.join(timeout=0.016667)

            if rom_thread.is_alive():
                if hasattr(generated, "z"):
                    generated.z = 1
            elif result["exception"]:
                print(f"  WARNING: ROM execution raised exception: {result['exception']}")
                break
        elif hasattr(generated, "main"):
            try:
                generated.main()
            except Exception as e:
                print(f"  WARNING: main() raised exception: {e}")
                break

        # Render frame
        if _screen is not None:
            ppu.render_frame()

            # Copy PPU buffer to screen
            surface_data = ppu.get_surface_data()
            if surface_data is not None:
                _screen.blit(surface_data, (0, 0))

            pygame.display.flip()

        # APU audio update
        if not headless and _runtime is not None:
            apu.update()
            # Fire FIFO empty triggers to refill DMA3 FIFOs
            _runtime["dma"].fifo_a_empty_fire()
            _runtime["dma"].fifo_b_empty_fire()

        # Advance timers and trigger timer DMA
        if _runtime is not None:
            _runtime["timers"].step(1540)
            _runtime["dma"].timer_trigger(0)  # Timer triggers custom DMA

        # Trigger VBlank interrupt
        if _runtime is not None:
            _runtime["dma"].vblank_fire()
            _runtime["dma"].hblank_fire()
            
            # Fire VBlank interrupt to set IF bit and check for dispatch
            irq = _runtime["irq"]
            irq.vblank_irq()  # This sets IF bit and calls handler if enabled
            
            # Check for pending interrupts and dispatch to ISR
            if irq.has_pending_interrupt():
                # Read ISR address from IWRAM (0x03007FFC)
                isr_addr = _memory.read_u32(0x03007FFC)
                if isr_addr != 0 and isr_addr != 0xFFFFFFFF:
                    # Call ISR through func_map if registered
                    if hasattr(generated, "func_map") and isr_addr in generated.func_map:
                        try:
                            generated.func_map[isr_addr]()
                        except Exception as e:
                            print(f"  WARNING: ISR raised exception: {e}")

        # VBlank simulation
        # Set z=1 to unblock VBlank wait loops
        if hasattr(generated, "z"):
            generated.z = 1

        # Frame timing
        clock.tick(60)  # Target 60 FPS

        if (frame + 1) % 10 == 0:
            print(f"  Frame {frame + 1}/{frames}")

    print("\n=== Game finished! ===")
    print(f"Total frames: {frame + 1}")

    # Capture screenshot if requested
    if screenshot_path and _screen is not None:
        pygame.image.save(_screen, screenshot_path)
        print(f"Screenshot saved to: {screenshot_path}")

    # Cleanup
    if not headless:
        apu.stop()

    pygame.quit()
    _runtime = None
    _screen = None
    _running = False
