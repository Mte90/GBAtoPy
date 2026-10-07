// Reachability-based scan for ARM LDM/STM with S-bit (bit 22).
// Uses the SAME CFG + selective_disassemble path as the transpiler pipeline,
// so only REACHABLE instructions (no data/header false positives) are considered.
//
// S-bit (bit 22) on LDM/STM:
//   - LDM with PC (R15) in list AND S=1  -> exception return (restore CPSR from SPSR). HANDLED by codegen.
//   - everything else with S=1            -> user-bank register access. HANDLED by codegen (load_store.rs:601).
//
// Usage: cargo run --release --example sbit_reachable -- <rom.gba | dir>
use gbatopy_disasm::{
    operand::{AddressingMode, Operand},
    ArmMode, CfgBuilder, Disassembler,
};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

fn is_sbit_block(inst: &gbatopy_disasm::DecodedInstruction) -> Option<(u8, &Vec<u8>, bool, bool)> {
    let op = inst.opcode.as_str();
    if !(op.starts_with("LDM") || op.starts_with("STM")) {
        return None;
    }
    if inst.mode != ArmMode::Arm || inst.is_data {
        return None;
    }
    if !inst.sets_flags {
        return None;
    }
    for opnd in &inst.operands {
        if let Operand::MemoryAddress { base, offset, .. } = opnd {
            if let AddressingMode::Multi { registers, s_bit, .. } = offset {
                if *s_bit {
                    let is_load = op.starts_with("LDM");
                    return Some((*base, registers, *s_bit, is_load));
                }
            }
        }
    }
    None
}

fn scan_rom(path: &Path) -> (usize, usize, usize, usize, usize, Vec<(String, u32, u8, Vec<u8>, bool, bool)>) {
    // returns (total_sbit, exception_return, user_bank, ub_base_not_in_list, ub_base_in_list, samples)
    let rom = match fs::read(path) {
        Ok(d) => d,
        Err(e) => {
            eprintln!("  read error: {e}");
            return (0, 0, 0, 0, 0, vec![]);
        }
    };
    let mut cfg = CfgBuilder::new();
    cfg.build_from_entry(&rom, 0x08000000);
    let reachable = cfg.get_reachable_addresses().to_vec();
    let mut disasm = Disassembler::new();
    let mut instructions = disasm.selective_disassemble(&rom, &reachable, &cfg.mode_map);
    let _ = disasm.mark_data_regions(&mut instructions);

    let mut total = 0usize;
    let mut exc_ret = 0usize;
    let mut user_bank = 0usize;
    let mut ub_base_not_in_list = 0usize;
    let mut ub_base_in_list = 0usize;
    let mut ub_samples = vec![];
    for inst in &instructions {
        if let Some((base, regs, _sbit, is_load)) = is_sbit_block(inst) {
            total += 1;
            let has_pc = regs.contains(&15);
            let base_in_list = regs.contains(&base);
            if is_load && has_pc {
                exc_ret += 1;
            } else {
                user_bank += 1;
                if base_in_list { ub_base_in_list += 1; } else { ub_base_not_in_list += 1; }
                if ub_samples.len() < 8 {
                    ub_samples.push((
                        inst.opcode.clone(),
                        inst.address,
                        base,
                        regs.clone(),
                        is_load,
                        base_in_list,
                    ));
                }
            }
        }
    }
    (total, exc_ret, user_bank, ub_base_not_in_list, ub_base_in_list, ub_samples)
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.is_empty() {
        eprintln!("usage: sbit_reachable <rom.gba | dir>");
        std::process::exit(2);
    }
    let mut roms: Vec<PathBuf> = vec![];
    for a in &args {
        let p = PathBuf::from(a);
        if p.is_dir() {
            let mut sub: Vec<PathBuf> = fs::read_dir(&p)
                .unwrap()
                .filter_map(|e| e.ok())
                .map(|e| e.path())
                .filter(|p| p.extension().and_then(|s| s.to_str()) == Some("gba"))
                .collect();
            sub.sort();
            roms.extend(sub);
        } else {
            roms.push(p);
        }
    }
    eprintln!("Scanning {} ROM (reachability-filtered)...", roms.len());

    let mut grand_total = 0usize;
    let mut grand_exc = 0usize;
    let mut grand_ub = 0usize;
    let mut grand_ub_bnil = 0usize;
    let mut grand_ub_bil = 0usize;
    let mut roms_sbit = 0usize;
    let mut roms_ub = 0usize;
    let mut roms_with_ub: Vec<(String, usize, usize, usize, Vec<_>)> = vec![];

    for r in &roms {
        let (total, exc, ub, ub_bnil, ub_bil, samples) = scan_rom(r);
        grand_total += total;
        grand_exc += exc;
        grand_ub += ub;
        grand_ub_bnil += ub_bnil;
        grand_ub_bil += ub_bil;
        if total > 0 {
            roms_sbit += 1;
        }
        if ub > 0 {
            roms_ub += 1;
            roms_with_ub.push((r.file_name().unwrap().to_string_lossy().into(), total, exc, ub, samples));
        }
        if total > 0 {
            eprintln!(
                "  {:45} total_sbit={:3} exc_ret={:3} user_bank={:3} (base_NOT_in_list={:3}, base_IN_list={:3})",
                r.file_name().unwrap().to_string_lossy(),
                total,
                exc,
                ub,
                ub_bnil,
                ub_bil
            );
        }
    }
    println!("\n===== REACHABILITY-FILTERED SUMMARY (real reachable ARM code only) =====");
    println!("ROMs scanned:                                   {}", roms.len());
    println!("ROMs with any S-bit LDM/STM:                    {}", roms_sbit);
    println!("ROMs with USER-BANK variant (S=1, not LDM+PC):  {}", roms_ub);
    println!("Total S-bit LDM/STM (reachable):                 {}", grand_total);
    println!("  exception_return (LDM^ with PC, HANDLED):      {}", grand_exc);
    println!("  user_bank (STM^, LDM^ w/o PC):  {}", grand_ub);
    println!("    of which base NOT in list (task framing):       {}", grand_ub_bnil);
    println!("    of which base IN list (still user-bank!):       {}", grand_ub_bil);

    if !roms_with_ub.is_empty() {
        println!("\n--- USER-BANK S-bit LDM/STM samples (REACHABLE, real code) ---");
        for (name, total, exc, ub, samples) in &roms_with_ub {
            println!("\n  {} (total_sbit={}, exc_ret={}, user_bank={})", name, total, exc, ub);
            for (op, addr, base, regs, is_load, base_in) in samples {
                let r: Vec<String> = regs.iter().map(|r| format!("R{r}")).collect();
                println!(
                    "    {} R{}, {{{}}}  @0x{:08X}  is_load={} base_in_list={}",
                    op, base, r.join(","), addr, is_load, base_in
                );
            }
        }
    } else {
        println!("\nNO reachable user-bank S-bit LDM/STM found in any ROM.");
    }
}
