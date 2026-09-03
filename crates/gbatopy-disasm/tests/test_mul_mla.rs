use gbatopy_disasm::arm::ArmDecoder;

#[test]
fn test_mul_instruction() {
    let decoder = ArmDecoder::new();
    // MULeq R0, R0, R1: cond=0000(EQ), bits27-24=0000, bits23-21=000(A=0),
    // bits19-16=0000(Rd), bits11-8=0001(Rs), bits7-4=1001, bits3-0=0000(Rm)
    let word = 0x00000190;
    let (opcode, operands, sets_flags) = decoder.decode(word, 0);

    assert_eq!(opcode, "MULeq");
    assert!(!sets_flags);
    assert_eq!(operands.len(), 3);
}

#[test]
fn test_mla_instruction() {
    let decoder = ArmDecoder::new();
    // MLAeq R0, R0, R1, R0: cond=0000(EQ), bits27-24=0000, bits23-21=001(A=1),
    // bit20=0(S=0), Rd=0, Ra=0, Rs=1, bits7-4=1001, Rm=0
    let word = 0x00200190;
    let (opcode, operands, sets_flags) = decoder.decode(word, 0);

    assert_eq!(opcode, "MLAeq");
    assert!(!sets_flags);
    assert_eq!(operands.len(), 4);
}

#[test]
fn test_mul_various_registers() {
    let decoder = ArmDecoder::new();
    // MULeq R3, R5, R7: cond=0000(EQ), A=0, Rd=3, Rs=7, Rm=5
    let word = 0x00030795;
    let (opcode, operands, _) = decoder.decode(word, 0);

    assert_eq!(opcode, "MULeq");
    assert_eq!(operands.len(), 3);
}
