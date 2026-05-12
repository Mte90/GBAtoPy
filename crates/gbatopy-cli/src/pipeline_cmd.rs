use std::fs;
use std::path::Path;

use gbatopy_disasm::Disassembler;

use crate::ppu::generate_ppu_code;

pub fn run_pipeline(
    rom_path: &str,
    output_path: &str,
    assets_dir: &Path,
    _use_ir: bool,
) -> Result<(), String> {
    let rom = fs::read(rom_path).map_err(|e| format!("Failed to read ROM: {}", e))?;

    eprintln!("Step 1: Disassembly");
    let mut disasm = Disassembler::new();
    let instructions = disasm.disassemble(&rom, 0x08000000);
    eprintln!("  Disassembled {} instructions", instructions.len());

    eprintln!("Step 2: Asset Extraction");
    eprintln!("  (Asset extraction skipped - not implemented yet)");

    eprintln!("Step 3: Python Code Generation (direct from disassembly)");

    // Generate Python directly from disassembled instructions
    let mut code = String::new();

    // Add required imports
    code.push_str("import pygame\n");
    code.push_str("import argparse\n");
    code.push_str("import numpy as np\n\n");

    code.push_str("# Global ARM registers (r0-r15, cpsr, spsr)\n");
    code.push_str("r0 = r1 = r2 = r3 = r4 = r5 = r6 = r7 = 0\n");
    code.push_str("r8 = r9 = r10 = r11 = r12 = r13 = r14 = r15 = 0\n");
    code.push_str("cpsr = 0  # Current Program Status Register\n");
    code.push_str("spsr = 0  # Saved Program Status Register\n\n");

    // Embed PPU code
    code.push_str("# PPU (Picture Processing Unit) - Graphics rendering\n");
    code.push_str(&format!("{}\n\n", generate_ppu_code()));

    // T2 FIX: Generate MULTIPLE functions based on branch targets
    let mut func_map_entries = Vec::new();

    // Step 1: Find all function start addresses (branch targets + entry point)
    let mut func_starts: std::collections::BTreeSet<u32> = std::collections::BTreeSet::new();

    // Entry point is always a function start
    let entry_point = if let Some(first) = instructions.first() {
        first.address
    } else {
        0x08000000
    };
    func_starts.insert(entry_point);

    // Scan for branch targets
    for inst in &instructions {
        let opcode = &inst.opcode;
        let base_opcode = opcode
            .split_whitespace()
            .next()
            .unwrap_or(opcode)
            .trim_end_matches("eq")
            .trim_end_matches("ne")
            .trim_end_matches("cs")
            .trim_end_matches("cc")
            .trim_end_matches("hs")
            .trim_end_matches("lo")
            .trim_end_matches("mi")
            .trim_end_matches("pl")
            .trim_end_matches("vs")
            .trim_end_matches("vc")
            .trim_end_matches("hi")
            .trim_end_matches("ls")
            .trim_end_matches("ge")
            .trim_end_matches("lt")
            .trim_end_matches("gt")
            .trim_end_matches("le")
            .trim_end_matches("al");

        match base_opcode {
            "B" | "BL" => {
                if let Some(target_str) = inst.operands.first() {
                    if let gbatopy_disasm::Operand::Immediate(target) = target_str {
                        // The disassembler already calculates the absolute target address
                        func_starts.insert(*target);
                    }
                }
            }
            "BLX" | "BX" => {
                // BX/BLX targets are in registers, can't resolve statically
                // Skip for now
            }
            _ => {}
        }
    }

    // Step 2: Group instructions by function
    let mut func_groups: std::collections::BTreeMap<u32, Vec<gbatopy_disasm::DecodedInstruction>> =
        std::collections::BTreeMap::new();

    for inst in &instructions {
        // Find which function this instruction belongs to
        let mut current_func = None;
        for &start_addr in &func_starts {
            if inst.address >= start_addr {
                current_func = Some(start_addr);
            } else {
                break;
            }
        }

        if let Some(func_addr) = current_func {
            func_groups
                .entry(func_addr)
                .or_insert_with(Vec::new)
                .push(inst.clone());
        }
    }

    // Helper function to generate Python from ARM instruction
    fn generate_python_from_instruction(inst: &gbatopy_disasm::DecodedInstruction) -> String {
        use gbatopy_disasm::Operand;

        let opcode = &inst.opcode;
        let ops = &inst.operands;

        // Remove condition suffix from opcode (eq, ne, cs, cc, etc.)
        let base_opcode = opcode.split_whitespace().next().unwrap_or(opcode);
        let base_opcode = base_opcode
            .trim_end_matches("eq")
            .trim_end_matches("ne")
            .trim_end_matches("cs")
            .trim_end_matches("cc")
            .trim_end_matches("hs")
            .trim_end_matches("lo")
            .trim_end_matches("mi")
            .trim_end_matches("pl")
            .trim_end_matches("vs")
            .trim_end_matches("vc")
            .trim_end_matches("hi")
            .trim_end_matches("ls")
            .trim_end_matches("ge")
            .trim_end_matches("lt")
            .trim_end_matches("gt")
            .trim_end_matches("le")
            .trim_end_matches("al");

        // Generate Python based on opcode type
        match base_opcode {
            // MOV Rd, #imm
            "MOV" => {
                if ops.len() == 2 {
                    if let Operand::Register(rd) = ops[0] {
                        if let Operand::Immediate(imm) = ops[1] {
                            return format!("r{} = {}", rd, imm);
                        }
                    }
                }
            }
            // MOV Rd, Rm
            "MOV" if ops.len() == 2 => {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Register(rm) = ops[1] {
                        return format!("r{} = r{}", rd, rm);
                    }
                }
            }
            // ADD Rd, Rn, #imm
            "ADD" => {
                if ops.len() >= 2 {
                    if let Operand::Register(rd) = ops[0] {
                        if let Operand::Register(rn) = ops[1] {
                            if ops.len() == 3 {
                                if let Operand::Immediate(imm) = ops[2] {
                                    return format!("r{} = (r{} + {}) & 0xFFFFFFFF", rd, rn, imm);
                                }
                            } else if let Operand::Register(rm) = ops[2] {
                                return format!("r{} = (r{} + r{}) & 0xFFFFFFFF", rd, rn, rm);
                            }
                        }
                    }
                }
            }
            // ADD Rd, Rn, Rm
            "ADD" if ops.len() == 3 => {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Register(rn) = ops[1] {
                        if let Operand::Register(rm) = ops[2] {
                            return format!("r{} = (r{} + r{}) & 0xFFFFFFFF", rd, rn, rm);
                        }
                    }
                }
            }
            // SUB Rd, Rn, #imm
            "SUB" => {
                if ops.len() >= 2 {
                    if let Operand::Register(rd) = ops[0] {
                        if let Operand::Register(rn) = ops[1] {
                            if ops.len() == 3 {
                                if let Operand::Immediate(imm) = ops[2] {
                                    return format!("r{} = (r{} - {}) & 0xFFFFFFFF", rd, rn, imm);
                                }
                            }
                        }
                    }
                }
            }
            // SUB Rd, Rn, Rm
            "SUB" if ops.len() == 3 => {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Register(rn) = ops[1] {
                        if let Operand::Register(rm) = ops[2] {
                            return format!("r{} = (r{} - r{}) & 0xFFFFFFFF", rd, rn, rm);
                        }
                    }
                }
            }
            // AND, EOR, ORR, BIC
            "AND" | "EOR" | "ORR" | "BIC" => {
                if ops.len() == 3 {
                    if let Operand::Register(rd) = ops[0] {
                        if let Operand::Register(rn) = ops[1] {
                            if let Operand::Register(rm) = ops[2] {
                                let op = match base_opcode {
                                    "AND" => "&",
                                    "EOR" => "^",
                                    "ORR" => "|",
                                    "BIC" => "& ~",
                                    _ => "&",
                                };
                                return format!("r{} = (r{} {} r{}) & 0xFFFFFFFF", rd, rn, op, rm);
                            }
                        }
                    }
                }
            }
            // MVN Rd, Rm
            "MVN" if ops.len() == 2 => {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Register(rm) = ops[1] {
                        return format!("r{} = (~r{}) & 0xFFFFFFFF", rd, rm);
                    }
                }
            }
            // B, BL - Branch instructions
            "B" | "BL" => {
                if ops.len() == 1 {
                    if let Operand::Immediate(offset) = ops[0] {
                        if base_opcode == "BL" {
                            // BL: Link register to return address (PC + 4)
                            return format!(
                                "r14, r15 = r15 + 4, r15 + {}\n# Branch with link",
                                offset
                            );
                        } else {
                            // B: Unconditional branch
                            return format!("r15 = r15 + {}\n# Branch", offset);
                        }
                    }
                }
                return format!("# {} (parsing failed)", base_opcode);
            }
            "BX" => {
                // BX: Branch exchange (branch to address in register)
                if ops.len() == 1 {
                    if let Operand::Register(rn) = ops[0] {
                        return format!("r15 = {}\n# Branch exchange", rn);
                    }
                }
                return format!("# BX (parsing failed)");
            }
            // LDR Rd, [Rn, #offset] - Load word from memory
            "LDR" => {
                if ops.len() >= 2 {
                    if let Operand::Register(rd) = ops[0] {
                        if let Operand::Register(rn) = ops[1] {
                            let offset = if ops.len() == 3 {
                                match &ops[2] {
                                    Operand::Immediate(off) => *off as i32,
                                    _ => 0,
                                }
                            } else {
                                0
                            };
                            return format!(
                                "r{} = memory.read_32(r{} + {})",
                                rd,
                                rn,
                                if offset >= 0 {
                                    format!("{}", offset)
                                } else {
                                    format!("({})", offset)
                                }
                            );
                        }
                    }
                }
                return format!("# LDR (parsing failed)");
            }
            // STR Rd, [Rn, #offset] - Store word to memory
            "STR" => {
                if ops.len() >= 2 {
                    if let Operand::Register(rd) = ops[0] {
                        if let Operand::Register(rn) = ops[1] {
                            let offset = if ops.len() == 3 {
                                match &ops[2] {
                                    Operand::Immediate(off) => *off as i32,
                                    _ => 0,
                                }
                            } else {
                                0
                            };
                            return format!(
                                "memory.write_32(r{} + {}, r{})",
                                rn,
                                if offset >= 0 {
                                    format!("{}", offset)
                                } else {
                                    format!("({})", offset)
                                },
                                rd
                            );
                        }
                    }
                }
                return format!("# STR (parsing failed)");
            }
            // LDM/STM - Block transfer (not implemented yet)
            "LDM" | "STM" => {
                return format!("# {} (block transfer not implemented)", base_opcode);
            }
            // LDRB/STRB - Byte transfer (not implemented yet)
            "LDRB" | "STRB" => {
                return format!("# {} (byte transfer not implemented)", base_opcode);
            }
            // LDRH/STRH - Halfword transfer (not implemented yet)
            "LDRH" | "STRH" => {
                return format!("# {} (halfword transfer not implemented)", base_opcode);
            }
            // Branch instructions
            "B" | "BL" => {
                return format!("# {} branch (not implemented)", base_opcode);
            }
            "BX" => {
                return format!("# BX (branch exchange not implemented)");
            }
            // Multiply instructions
            "MUL" | "MLA" | "UMULL" | "SMULL" | "UMLAL" | "SMLAL" => {
                // MUL/MLA - Multiply (operand parsing issue in disassembler, skip for now)
                return format!(
                    "# {} (multiply - needs disassembler operand fix)",
                    base_opcode
                );
            } // CMP, CMN, TST, TEQ (condition tests)
            "CMP" | "CMN" | "TST" | "TEQ" => {
                return format!("# {} (condition test not implemented)", base_opcode);
            }
            _ => {
                // Fallback to comment for unimplemented opcodes
                let ops_str = ops
                    .iter()
                    .map(|op| format!("{:?}", op))
                    .collect::<Vec<_>>()
                    .join(", ");
                return format!("# {} {}", base_opcode, ops_str);
            }
        }

        // Default fallback
        let ops_str = ops
            .iter()
            .map(|op| format!("{:?}", op))
            .collect::<Vec<_>>()
            .join(", ");
        format!("# {} {}", base_opcode, ops_str)
    }

    // Embed ROM data FIRST (before GBA class needs it)
    code.push_str("# Full ROM data\n");
    code.push_str("ROM_DATA = bytearray([\n");
    for (i, byte) in rom.iter().enumerate() {
        if i > 0 {
            code.push_str(", ");
        }
        if i % 16 == 0 {
            code.push_str("\n    ");
        }
        code.push_str(&format!("0x{:02X}", byte));
    }
    code.push_str("\n])\n\n");

    // Embed GBA memory class ONCE (before all functions)
    code.push_str(
        r#"# GBA Memory Map Implementation
class GBA:
    def __init__(self, rom_data):
        self.bios = bytearray(0x4000)
        self.ewram = bytearray(0x40000)
        self.iwram = bytearray(0x8000)
        self.mmio = {}
        self.palette = bytearray(0x400)
        self.vram = bytearray(0x18000)
        self.oam = bytearray(0x400)
        self.rom = rom_data

    def read_8(self, addr):
        if 0x00000000 <= addr <= 0x00003FFF:
            return self.bios[addr - 0x00000000] if (addr - 0x00000000) < len(self.bios) else 0
        elif 0x02000000 <= addr <= 0x0203FFFF:
            return self.ewram[addr - 0x02000000] if (addr - 0x02000000) < len(self.ewram) else 0
        elif 0x03000000 <= addr <= 0x03007FFF:
            return self.iwram[addr - 0x03000000] if (addr - 0x03000000) < len(self.iwram) else 0
        elif 0x04000000 <= addr <= 0x040003FF:
            return self.mmio.get(addr - 0x04000000, 0)
        elif 0x05000000 <= addr <= 0x050003FF:
            return self.palette[addr - 0x05000000] if (addr - 0x05000000) < len(self.palette) else 0
        elif 0x06000000 <= addr <= 0x06017FFF:
            return self.vram[addr - 0x06000000] if (addr - 0x06000000) < len(self.vram) else 0
        elif 0x07000000 <= addr <= 0x070003FF:
            return self.oam[addr - 0x07000000] if (addr - 0x07000000) < len(self.oam) else 0
        elif 0x08000000 <= addr <= 0x09FFFFFF:
            return self.rom[addr - 0x08000000] if (addr - 0x08000000) < len(self.rom) else 0
        return 0

    def read_32(self, addr):
        b0 = self.read_8(addr)
        b1 = self.read_8(addr + 1)
        b2 = self.read_8(addr + 2)
        b3 = self.read_8(addr + 3)
        return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)

    def write_8(self, addr, value):
        if 0x02000000 <= addr <= 0x0203FFFF:
            offset = addr - 0x02000000
            if offset < len(self.ewram): self.ewram[offset] = value
        elif 0x03000000 <= addr <= 0x03007FFF:
            offset = addr - 0x03000000
            if offset < len(self.iwram): self.iwram[offset] = value
        elif 0x04000000 <= addr <= 0x040003FF:
            self.mmio[addr - 0x04000000] = value
        elif 0x05000000 <= addr <= 0x050003FF:
            offset = addr - 0x05000000
            if offset < len(self.palette): self.palette[offset] = value
        elif 0x06000000 <= addr <= 0x06017FFF:
            offset = addr - 0x06000000
            if offset < len(self.vram): self.vram[offset] = value
        elif 0x07000000 <= addr <= 0x070003FF:
            offset = addr - 0x07000000
            if offset < len(self.oam): self.oam[offset] = value

    def write_32(self, addr, value):
        self.write_8(addr, value & 0xFF)
        self.write_8(addr + 1, (value >> 8) & 0xFF)
        self.write_8(addr + 2, (value >> 16) & 0xFF)
        self.write_8(addr + 3, (value >> 24) & 0xFF)

"#,
    );

    code.push_str("memory = GBA(ROM_DATA)\n\n");

    // Generate a function for each group
    for (&func_addr, func_instructions) in &func_groups {
        let func_name = format!("func_{:08X}", func_addr);

        code.push_str(&format!("def {}():\n", func_name));
        code.push_str(
            "    global r0, r1, r2, r3, r4, r5, r6, r7, r8, r9, r10, r11, r12, r13, r14, r15\n",
        );
        code.push_str("    global cpsr, spsr\n");

        for inst in func_instructions {
            let py_stmt = generate_python_from_instruction(inst);
            code.push_str(&format!("    {}\n", py_stmt));
        }

        code.push_str("\n");
        func_map_entries.push(format!("    0x{:08X}: {},", func_addr, func_name));
    }

    // Generate func_map
    code.push_str("# Function map for dynamic dispatch\n");
    code.push_str("func_map = {\n");
    code.push_str(&func_map_entries.join("\n"));
    code.push_str("\n}\n\n");

    // Add game loop (from generate_game_loop in pipeline.rs)
    code.push_str(&generate_game_loop());

    fs::write(output_path, &code).map_err(|e| format!("Failed to write output: {}", e))?;

    println!(
        "Generated {} lines of Python to {}",
        code.lines().count(),
        output_path
    );
    Ok(())
}

// Helper function to generate game loop (copied from cmds/pipeline.rs)
fn generate_game_loop() -> String {
    r#"
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
        
        # TODO: Render PPU framebuffer to screen
        # For now, show a placeholder
        if not headless and screen:
            screen.fill((0, 0, 0))  # Black background
            # TODO: Render actual PPU output
            pygame.display.flip()
        
        frame_count += 1
        clock.tick(60)
        
        if frame_limit and frame_count >= frame_limit:
            break
    
    # Save screenshot if requested
    if screenshot_path:
        if screen is None:
            # In headless mode, create a blank surface
            screen = pygame.Surface((240, 160))
        pygame.image.save(screen, screenshot_path)
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
// Force rebuild ven 1 mag 2026, 13:30:36, CEST
