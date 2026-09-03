use gbatopy_disasm::thumb::ThumbDecoder;

#[test]
fn test_format7_register_offset_decode() {
    let d = ThumbDecoder::new();
    let cases: &[(u16, &str)] = &[
        (0x5000, "STR"),
        (0x5200, "STRH"),
        (0x5400, "STRB"),
        (0x5600, "LDRSB"),
        (0x5800, "LDR"),
        (0x5A00, "LDRH"),
        (0x5C00, "LDRB"),
        (0x5E00, "LDRSH"),
        (0x58FC, "LDR"),
        (0x5039, "STR"),
        (0x5239, "STRH"),
        (0x5439, "STRB"),
        (0x5639, "LDRSB"),
        (0x5A39, "LDRH"),
        (0x5C39, "LDRB"),
        (0x5E39, "LDRSH"),
    ];
    for (hw, want) in cases {
        let (got, ops, _) = d.decode(*hw, 0);
        assert_eq!(
            got, *want,
            "opcode 0x{:04X}: got {} want {}",
            hw, got, want
        );
        assert_eq!(ops.len(), 3, "opcode 0x{:04X}: expected 3 operands", hw);
    }
}
