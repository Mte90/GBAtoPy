use gbatopy_disasm::arm::ArmDecoder;

#[test]
fn test_mul_instruction() {
    let decoder = ArmDecoder::new();
    let word = 0x00200190;
    let (opcode, operands, sets_flags) = decoder.decode(word, 0);

    assert_eq!(opcode, "MULeq");
    assert!(!sets_flags);
    assert_eq!(operands.len(), 3);
}

#[test]
fn test_mla_instruction() {
    let decoder = ArmDecoder::new();
    let word = 0x00300190;
    let (opcode, operands, sets_flags) = decoder.decode(word, 0);

    assert_eq!(opcode, "MLAeq");
    assert!(!sets_flags);
    assert_eq!(operands.len(), 4);
}

#[test]
fn test_mul_various_registers() {
    let decoder = ArmDecoder::new();
    let word = 0x00230795;
    let (opcode, operands, _) = decoder.decode(word, 0);

    assert_eq!(opcode, "MULeq");
    assert_eq!(operands.len(), 3);
}
