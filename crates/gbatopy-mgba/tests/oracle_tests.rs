use gbatopy_disasm::ArmMode;
use gbatopy_mgba::AccessKind;
use gbatopy_mgba::OracleTrace;
use gbatopy_mgba::TraceMetadata;
use gbatopy_mgba::OracleMode;
use gbatopy_mgba::MemoryAccess;
use gbatopy_mgba::RegisterState;


#[test]
fn test_register_state_serialization() {
    let state = RegisterState {
        r0: 0x1234,
        r1: 0x5678,
        r2: 0,
        r3: 0,
        r4: 0,
        r5: 0,
        r6: 0,
        r7: 0,
        r8: 0,
        r9: 0,
        r10: 0,
        r11: 0,
        r12: 0,
        sp: 0x20000000,
        lr: 0x08000100,
        pc: 0x08000000,
        cpsr: 0x10,
    };

    let json = serde_json::to_string(&state).unwrap();
    assert!(json.contains("4660")); // 0x1234 in decimal

    let _deserialized: RegisterState = serde_json::from_str(&json).unwrap();
}

#[test]
fn test_memory_access_serialization() {
    let access = MemoryAccess {
        kind: AccessKind::Read,
        address: 0x20000000,
        size: 4,
        value: 0xDEADBEEF,
    };

    let json = serde_json::to_string(&access).unwrap();
    assert!(json.contains("Read"));
}

#[test]
fn test_trace_metadata_static_only() {
    let metadata = TraceMetadata {
        timestamp: "2026-04-08T12:00:00Z".to_string(),
        mgba_version: None,
        mode: OracleMode::StaticOnly,
        instruction_count: 0,
        duration_ms: 0,
        mode_switches: vec![],
    };

    assert_eq!(metadata.mode, OracleMode::StaticOnly);
    assert_eq!(metadata.instruction_count, 0);
}

#[test]
fn test_arm_mode_serialization() {
    let arm = ArmMode::Arm;
    let thumb = ArmMode::Thumb;

    let arm_json = serde_json::to_string(&arm).unwrap();
    let thumb_json = serde_json::to_string(&thumb).unwrap();

    assert!(!arm_json.is_empty());
    assert!(!thumb_json.is_empty());
}

#[test]
fn test_oracle_trace_empty() {
    let trace = OracleTrace {
        rom_path: "test.gb".to_string(),
        rom_size: 0x10000,
        entries: vec![],
        metadata: TraceMetadata {
            timestamp: "2026-04-08T12:00:00Z".to_string(),
            mgba_version: None,
            mode: OracleMode::StaticOnly,
            instruction_count: 0,
            duration_ms: 0,
            mode_switches: vec![],
        },
    };

    assert_eq!(trace.entries.len(), 0);
    assert_eq!(trace.metadata.instruction_count, 0);
    assert_eq!(trace.rom_size, 0x10000);
}
