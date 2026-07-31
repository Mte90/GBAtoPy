use gbatopy_disasm::CfgBuilder;
use std::fs;

fn main() {
    let rom = fs::read("test_roms/roms/bgpd.gba").unwrap();
    let mut cfg = CfgBuilder::new();
    cfg.build_from_entry(&rom, 0x08000000);
    let reachable = cfg.get_reachable_addresses();
    
    println!("Total reachable: {}", reachable.len());
    println!("\nChecking addresses 0x08000390-0x08000410:");
    for addr in (0x08000390..0x08000410).step_by(4) {
        if reachable.contains(&addr) {
            println!("  0x{:08x}: REACHABLE", addr);
        } else {
            println!("  0x{:08x}: ---", addr);
        }
    }
}
