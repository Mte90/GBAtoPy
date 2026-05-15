use crate::ppu::generate_ppu_code;
use std::fs;
use std::path::Path;

#[allow(dead_code)]
fn embed_pyboyadvance(_runtime_dir: &str) -> Result<String, String> {
    Ok(String::new())
}

#[allow(dead_code)]
fn strip_cython_guards(code: &str) -> String {
    let mut result = String::new();
    let mut in_cython_guard = false;

    for line in code.lines() {
        let trimmed = line.trim();

        if trimmed.starts_with("# ifndef CYTHON") || trimmed.starts_with("#if !CYTHON") {
            in_cython_guard = true;
            continue;
        }

        if trimmed == "# endif" || trimmed.starts_with("#endif") {
            if in_cython_guard {
                in_cython_guard = false;
                continue;
            }
        }

        if in_cython_guard {
            continue;
        }

        result.push_str(line);
        result.push('\n');
    }

    result
}

pub fn generate_game_loop() -> String {
    r#"
# ============================================================================
# Game Loop - Transpiled GBA execution with func_map dispatch
# ============================================================================

import pygame
import argparse
import sys
import os

# Global ARM registers (r0-r15, cpsr, spsr)
# These are modified by the generated func_* functions
r0 = r1 = r2 = r3 = r4 = r5 = r6 = r7 = 0
r8 = r9 = r10 = r11 = r12 = r13 = r14 = r15 = 0
cpsr = 0  # Current Program Status Register
spsr = 0  # Saved Program Status Register

# Stack pointers for different modes (simplified)
usr_sp = irq_sp = svc_sp = 0

# Entry point - GBA ROM starts at 0x08000000
GBA_ENTRY = 0x08000000
r15 = GBA_ENTRY

# Memory placeholders (will be replaced by PPU code with actual VRAM/palette)
memory_vram = bytearray(0x18000)  # VRAM
memory_palette = bytearray(0x400)  # Palette

def run_transpiled(headless=False, frame_limit=None, screenshot_path=None, scale=1):
    """Execute transpiled GBA code using func_map dispatch"""
    
    frame_count = 0
    max_instructions = 1000000  # Safety limit
    instruction_count = 0
    
    print(f"Starting transpiled execution at PC=0x{r15:08X}")
    
    # Main execution loop
    while instruction_count < max_instructions:
        pc = r15
        
        # Look up function by address
        if pc not in func_map:
            print(f"Unknown PC: 0x{pc:08X} - execution halted")
            break
        
        # Get the function and call it
        func = func_map[pc]
        func()  # This updates r15 (PC) for next instruction
        
        instruction_count += 1
        
        # If PC didn't change, we're in an infinite loop
        if r15 == pc:
            print(f"PC unchanged at 0x{pc:08X} - infinite loop detected")
            break
        
        # Progress reporting every 10000 instructions
        if instruction_count % 10000 == 0:
            print(f"Executed {instruction_count} instructions, PC=0x{r15:08X}")
        
        # Frame limit check
        if frame_limit and frame_count >= frame_limit:
            break
        
        # For now, each instruction counts as ~1 frame
        # Real implementation would count actual frame cycles
        if instruction_count % 1000 == 0:
            frame_count += 1
    
    print(f"Execution stopped after {instruction_count} instructions")
    print(f"Final PC: 0x{r15:08X}")
    
    return frame_count

def run_with_pygame(headless=False, frame_limit=None, screenshot_path=None, scale=1):
    """Run transpiled GBA code with pygame display and input"""
    
    pygame.init()
    
    if not headless:
        screen = pygame.display.set_mode((240 * scale, 160 * scale))
        pygame.display.set_caption("GBAtoPy - Transpiled GBA")
    else:
        screen = None
    
    clock = pygame.time.Clock()
    frame_count = 0
    running = True
    
    # Input state
    keys_down = {}
    
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                # Map pygame keys to GBA inputs (stored in registers for game code)
                elif event.key == pygame.K_UP:
                    keys_down['UP'] = True
                elif event.key == pygame.K_DOWN:
                    keys_down['DOWN'] = True
                elif event.key == pygame.K_LEFT:
                    keys_down['LEFT'] = True
                elif event.key == pygame.K_RIGHT:
                    keys_down['RIGHT'] = True
                elif event.key == pygame.K_z:
                    keys_down['A'] = True
                elif event.key == pygame.K_x:
                    keys_down['B'] = True
                elif event.key == pygame.K_RETURN:
                    keys_down['START'] = True
                elif event.key == pygame.K_BACKSPACE:
                    keys_down['SELECT'] = True
                elif event.key == pygame.K_a:
                    keys_down['L'] = True
                elif event.key == pygame.K_s:
                    keys_down['R'] = True
            elif event.type == pygame.KEYUP:
                if event.key == pygame.K_UP:
                    keys_down.pop('UP', None)
                elif event.key == pygame.K_DOWN:
                    keys_down.pop('DOWN', None)
                elif event.key == pygame.K_LEFT:
                    keys_down.pop('LEFT', None)
                elif event.key == pygame.K_RIGHT:
                    keys_down.pop('RIGHT', None)
                elif event.key == pygame.K_z:
                    keys_down.pop('A', None)
                elif event.key == pygame.K_x:
                    keys_down.pop('B', None)
                elif event.key == pygame.K_RETURN:
                    keys_down.pop('START', None)
                elif event.key == pygame.K_BACKSPACE:
                    keys_down.pop('SELECT', None)
                elif event.key == pygame.K_a:
                    keys_down.pop('L', None)
                elif event.key == pygame.K_s:
                    keys_down.pop('R', None)
        
        # Render PPU framebuffer to screen
        # Create minimal Memory object for PPU
        class MemorySimple:
            def __init__(self, vram, palette):
                self.vram = vram
                self.palette = palette
            
            def read_8(self, addr):
                if addr < len(self.vram):
                    return self.vram[addr]
                return 0
            
            def read_16(self, addr):
                if addr + 1 < len(self.vram):
                    return self.vram[addr] | (self.vram[addr + 1] << 8)
                return 0
            
            def read_32(self, addr):
                if addr + 3 < len(self.vram):
                    return (self.vram[addr] | (self.vram[addr + 1] << 8) |
                           (self.vram[addr + 2] << 16) | (self.vram[addr + 3] << 24))
                return 0
            
            def write_8(self, addr, value):
                if addr < len(self.vram):
                    self.vram[addr] = value & 0xFF
            
            def write_16(self, addr, value):
                if addr < len(self.vram):
                    self.vram[addr] = value & 0xFF
                    if addr + 1 < len(self.vram):
                        self.vram[addr + 1] = (value >> 8) & 0xFF
            
            def write_32(self, addr, value):
                if addr < len(self.vram):
                    self.vram[addr] = value & 0xFF
                    if addr + 1 < len(self.vram):
                        self.vram[addr + 1] = (value >> 8) & 0xFF
                    if addr + 2 < len(self.vram):
                        self.vram[addr + 2] = (value >> 16) & 0xFF
                    if addr + 3 < len(self.vram):
                        self.vram[addr + 3] = (value >> 24) & 0xFF
        
        memory_simple = MemorySimple(memory_vram, memory_palette)
        ppu_instance = PPU(memory_simple)
        ppu_instance.render_frame()
        if screen:
            screen.blit(ppu_instance.screen, (0, 0))
            pygame.display.flip()
        
        frame_count += 1
        clock.tick(60)
        
        if frame_limit and frame_count >= frame_limit:
            break
    
    # Save screenshot if requested
    if screenshot_path:
        if screen:
            pygame.image.save(screen, screenshot_path)
        else:
            # Headless mode: save from PPU framebuffer
            surface = pygame.Surface((240, 160))
            surface.blit(ppu_instance.screen, (0, 0))
            pygame.image.save(surface, screenshot_path)
        print(f"Screenshot saved to: {screenshot_path}")
    
    pygame.quit()
    return frame_count

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GBAtoPy Transpiled GBA")
    parser.add_argument("--headless", action="store_true", help="Run without display")
    parser.add_argument("--frame", type=int, default=None, help="Number of frames to run")
    parser.add_argument("--screenshot", type=str, default=None, help="Screenshot output path")
    parser.add_argument("--scale", type=int, default=1, help="Display scale factor")
    parser.add_argument("--benchmark", action="store_true", help="Run benchmark (1000 instructions)")
    
    args = parser.parse_args()
    
    if args.benchmark:
        import time
        start = time.time()
        frames = run_transpiled(headless=True, frame_limit=1000)
        elapsed = time.time() - start
        print(f"Benchmark: {frames} frames in {elapsed:.3f}s")
    else:
        # Use pygame version for interactive display
        frames = run_with_pygame(
            headless=args.headless,
            frame_limit=args.frame,
            screenshot_path=args.screenshot,
            scale=args.scale
        )
        print(f"Ran {frames} frames")
"#
    .to_string()
}

pub fn generate_rom_data(rom_data: &[u8]) -> String {
    let mut code = String::new();
    code.push_str("\n# Full ROM data for runtime memory mapping\n");
    code.push_str("ROM_DATA = bytearray([");

    for (i, byte) in rom_data.iter().enumerate() {
        if i > 0 {
            code.push_str(", ");
        }
        if i % 16 == 0 {
            code.push_str("\n    ");
        }
        code.push_str(&format!("0x{:02X}", byte));
    }

    code.push_str("\n])\n");
    code
}

pub fn generate_bios() -> String {
    let bios_path = "python/gba_runtime/bios_minimal.py";

    if let Ok(bios_content) = std::fs::read_to_string(bios_path) {
        let mut code = String::new();
        code.push_str("\n# Embedded GBA BIOS (minimal Python implementation)\n");
        code.push_str("# Provides: Halt(), VSync(), Div(), Sqrt()\n\n");
        code.push_str(&bios_content);
        code.push('\n');
        return code;
    }

    r#"
# Minimal GBA BIOS fallback (when bios_minimal.py not found)

def Halt():
    """Freeze loop when ROM calls BIOS Halt (most common)."""
    pass

def VSync():
    """Trigger VBlank interrupt for save states and frame sync."""
    pass

def Div(numerator, denominator):
    """32-bit integer division."""
    if denominator == 0:
        return (0, numerator)
    quotient = int(numerator / denominator)
    remainder = numerator % denominator
    if quotient > 0x7FFFFFFF:
        quotient -= 0x100000000
    if remainder > 0x7FFFFFFF:
        remainder -= 0x100000000
    return (quotient, remainder)

def Sqrt(value):
    """Integer square root."""
    if value <= 0:
        return 0
    guess = value >> 1
    if guess == 0:
        guess = 1
    while True:
        next_guess = (guess + value // guess) >> 1
        if next_guess >= guess:
            return guess
        guess = next_guess
"#
    .to_string()
}

pub fn run_pipeline(
    rom_path: &str,
    output_path: &str,
    _assets_dir: &Path,
    _use_ir: bool,
) -> Result<(), String> {
    println!("Running PyBoyAdvance-based pipeline on: {}", rom_path);

    let rom_data = fs::read(rom_path).map_err(|e| format!("Failed to read ROM: {}", e))?;

    let mut python_code = String::new();

    println!("Phase 1: Embedding GBA runtime...");
    let runtime_code = std::fs::read_to_string("crates/gbatopy-cli/assets/gba_runtime_embedded.py")
        .map_err(|e| format!("Failed to read runtime: {}", e))?;
    python_code.push_str(&runtime_code);
    python_code.push('\n');

    println!("Phase 2: Generating PPU code...");
    let ppu_code = generate_ppu_code();
    python_code.push_str(&ppu_code);
    python_code.push('\n');

    println!("Phase 3: Embedding BIOS...");
    let bios_code = generate_bios();
    python_code.push_str(&bios_code);

    println!("Phase 3: Generating ROM data...");
    let rom_data_code = generate_rom_data(&rom_data);
    python_code.push_str(&rom_data_code);

    println!("Phase 4: Adding game loop...");
    let game_loop = generate_game_loop();
    python_code.push_str(&game_loop);

    fs::write(output_path, &python_code).map_err(|e| format!("Failed to write output: {}", e))?;

    println!("Generated Python written to: {}", output_path);
    println!("Pipeline complete!");
    Ok(())
}

fn strip_relative_imports(code: &str) -> String {
    code.lines()
        .filter(|line| {
            // Completely remove relative import lines and gba_runtime imports
            let trimmed = line.trim();
            if trimmed.starts_with("from .") {
                false
            } else if trimmed.starts_with("import .") {
                false
            } else if trimmed.starts_with("from gba_runtime.") {
                false
            } else if trimmed.starts_with("import gba_runtime") {
                false
            } else {
                true
            }
        })
        .collect::<Vec<&str>>()
        .join("\n")
}
