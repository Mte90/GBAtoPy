use gbatopy_disasm::{Instruction, Operand};

/// Generate SRAM initialization code
pub fn generate_sram_init(rom_path: &str, sram_size: usize) -> String {
    format!(
        r#"
# SRAM for persistent save data
try:
    from .sram import SRAM
    sram = SRAM(size={size}, save_file="{rom_name}")
except ImportError:
    sram = None

"#,
        size = sram_size,
        rom_name = rom_path.replace('/', '_').replace('\\', '_').replace('.', '_').replace('-', '_')
    )
}

/// Generate SRAM load code (called on game start)
pub fn generate_sram_load(sram_size: usize) -> String {
    if sram_size == 0 {
        return "sram = None\n".to_string();
    }
    format!(
        r#"
if sram is not None:
    sram.load()
"#
    )
}

/// Generate SRAM save code (called on game exit)
pub fn generate_sram_save() -> String {
    format!(
        r#"
if sram is not None:
    sram.save()
"#
    )
}

/// Generate code to handle reads to SRAM region
pub fn generate_sram_read(addr: u32) -> String {
    let low_addr = addr & 0xFFFF;
    format!(
        r#"
if sram is not None:
    offset = {} - 0x0E000000
    if 0 <= offset < len(sram.data):
        return sram.read_u8(offset)
"#,
        addr
    )
}

/// Generate code to handle writes to SRAM region
pub fn generate_sram_write(addr: u32) -> String {
    let low_addr = addr & 0xFFFF;
    format!(
        r#"
if sram is not None:
    offset = {} - 0x0E000000
    if 0 <= offset < len(sram.data):
        sram.write_u8(offset, value)
"#,
        addr
    )
}
