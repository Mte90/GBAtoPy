pub fn generate_sram_init() -> String {
    r#"
# SRAM (Save RAM) - 32KB persistent storage
# Mapped at 0x0E000000-0x0E007FFF (mirrored)
sram_data = bytearray(32768)  # 32KB SRAM

def sram_read(addr):
    """Read byte from SRAM"""
    offset = (addr - 0x0E000000) & 0x7FFF
    return sram_data[offset]

def sram_write(addr, value):
    """Write byte to SRAM"""
    offset = (addr - 0x0E000000) & 0x7FFF
    sram_data[offset] = value & 0xFF

def sram_save(filename):
    """Save SRAM data to file"""
    with open(filename, 'wb') as f:
        f.write(sram_data)

def sram_load(filename):
    """Load SRAM data from file"""
    try:
        with open(filename, 'rb') as f:
            data = f.read(32768)
            for i, b in enumerate(data):
                sram_data[i] = b
    except FileNotFoundError:
        pass  # No save file yet
"#
    .to_string()
}

pub fn generate_sram_access(addr: u32, operation: &str, value: Option<u32>) -> String {
    let offset = addr - 0x0E000000;

    match operation {
        "read" => format!("# SRAM read at 0x{:08X}\nr15 += 1\n", addr),
        "write" => {
            let value_str = match value {
                Some(v) => format!("0x{:02X}", v),
                None => "value".to_string(),
            };
            format!(
                "# SRAM write at 0x{:08X}\nsram_write(0x{:08X}, {})\nr15 += 1\n",
                addr, addr, value_str
            )
        }
        _ => format!("# Unknown SRAM operation\n"),
    }
}
