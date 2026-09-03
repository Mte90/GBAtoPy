use gbatopy_disasm::arm::ArmDecoder;

#[test]
fn test_ldrh_immediate_offset() {
    let decoder = ArmDecoder::new();
    // LDRH R0, [R1, #2]: bits 7-4 = 1 0 1 1 (S=0, H=1), L=1, I(bit22)=1
    // 0xE1D100B2 = 1110 0001 1101 0001 0000 0000 1011 0010
    let word = 0xE1D100B2;
    let (opcode, operands, _) = decoder.decode(word, 0);
    assert_eq!(opcode, "LDRH");
    assert_eq!(operands.len(), 2);
}

#[test]
fn test_ldrh_from_even_address() {
    let decoder = ArmDecoder::new();
    // LDRH R0, [R1, #0]: offset=0, bits 7-4 = 1011
    // 0xE1D100B0 = 1110 0001 1101 0001 0000 0000 1011 0000
    let word = 0xE1D100B0;
    let (opcode, operands, _) = decoder.decode(word, 0);
    assert_eq!(opcode, "LDRH");
    assert_eq!(operands.len(), 2);
}

#[test]
fn test_strh_immediate_offset() {
    let decoder = ArmDecoder::new();
    // STRH R0, [R1, #2]: bits 7-4 = 1011 (S=0, H=1), L=0, I(bit22)=1
    // 0xE1C100B2 = 1110 0001 1100 0001 0000 0000 1011 0010
    let word = 0xE1C100B2;
    let (opcode, operands, _) = decoder.decode(word, 0);
    assert_eq!(opcode, "STRH");
    assert_eq!(operands.len(), 2);
}

#[test]
fn test_ldrsb_immediate_offset() {
    let decoder = ArmDecoder::new();
    // LDRSB R0, [R1, #2]: bits 7-4 = 1 1 0 1 (S=1, H=0), L=1, I(bit22)=1
    // 0xE1D100D2 = 1110 0001 1101 0001 0000 0000 1101 0010
    let word = 0xE1D100D2;
    let (opcode, operands, _) = decoder.decode(word, 0);
    assert_eq!(opcode, "LDRSB");
    assert_eq!(operands.len(), 2);
}

#[test]
fn test_ldrsh_immediate_offset() {
    let decoder = ArmDecoder::new();
    // LDRSH R0, [R1, #2]: bits 7-4 = 1 1 1 1 (S=1, H=1), L=1, I(bit22)=1
    // 0xE1D100F2 = 1110 0001 1101 0001 0000 0000 1111 0010
    let word = 0xE1D100F2;
    let (opcode, operands, _) = decoder.decode(word, 0);
    assert_eq!(opcode, "LDRSH");
    assert_eq!(operands.len(), 2);
}

#[test]
fn test_ldrsb_from_even_address() {
    let decoder = ArmDecoder::new();
    // LDRSB R0, [R1, #0]: offset=0, bits 7-4 = 1101
    // 0xE1D100D0 = 1110 0001 1101 0001 0000 0000 1101 0000
    let word = 0xE1D100D0;
    let (opcode, operands, _) = decoder.decode(word, 0);
    assert_eq!(opcode, "LDRSB");
    assert_eq!(operands.len(), 2);
}

#[test]
fn test_ldrsh_from_even_address() {
    let decoder = ArmDecoder::new();
    // LDRSH R0, [R1, #0]: offset=0, bits 7-4 = 1111
    // 0xE1D100F0 = 1110 0001 1101 0001 0000 0000 1111 0000
    let word = 0xE1D100F0;
    let (opcode, operands, _) = decoder.decode(word, 0);
    assert_eq!(opcode, "LDRSH");
    assert_eq!(operands.len(), 2);
}
