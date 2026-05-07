use gbatopy_disasm::arm::ArmDecoder;

#[test]
fn test_ldrh_immediate_offset() {
    let decoder = ArmDecoder::new();
    // LDRH: bits[23:20] = 1011 = 0xB
    // 0xE1B10002 = 1110 0001 1011 0001 0000 0000 0000 0010
    let word = 0xE1B10002;
    let (opcode, operands, _) = decoder.decode(word, 0);
    assert_eq!(opcode, "LDRH");
    assert_eq!(operands.len(), 2);
}

#[test]
fn test_ldrh_from_even_address() {
    let decoder = ArmDecoder::new();
    let word = 0xE1B10000;
    let (opcode, operands, _) = decoder.decode(word, 0);
    assert_eq!(opcode, "LDRH");
    assert_eq!(operands.len(), 2);
}

#[test]
fn test_strh_immediate_offset() {
    let decoder = ArmDecoder::new();
    // STRH: bits[23:20] = 1010 = 0xA
    // 0xE1A10002 = 1110 0001 1010 0001 0000 0000 0000 0010
    let word = 0xE1A10002;
    let (opcode, operands, _) = decoder.decode(word, 0);
    assert_eq!(opcode, "STRH");
    assert_eq!(operands.len(), 2);
}

#[test]
fn test_ldrsb_immediate_offset() {
    let decoder = ArmDecoder::new();
    // LDRSB: bits[23:20] = 1101 = 0xD
    let word = 0xE1D10002;
    let (opcode, operands, _) = decoder.decode(word, 0);
    assert_eq!(opcode, "LDRSB");
    assert_eq!(operands.len(), 2);
}

#[test]
fn test_ldrsh_immediate_offset() {
    let decoder = ArmDecoder::new();
    // LDRSH: bits[23:20] = 1111 = 0xF
    let word = 0xE1F10002;
    let (opcode, operands, _) = decoder.decode(word, 0);
    assert_eq!(opcode, "LDRSH");
    assert_eq!(operands.len(), 2);
}

#[test]
fn test_ldrsb_from_even_address() {
    let decoder = ArmDecoder::new();
    let word = 0xE1D10000;
    let (opcode, operands, _) = decoder.decode(word, 0);
    assert_eq!(opcode, "LDRSB");
    assert_eq!(operands.len(), 2);
}

#[test]
fn test_ldrsh_from_even_address() {
    let decoder = ArmDecoder::new();
    let word = 0xE1F10000;
    let (opcode, operands, _) = decoder.decode(word, 0);
    assert_eq!(opcode, "LDRSH");
    assert_eq!(operands.len(), 2);
}
