use gbatopy_disasm::{ArmMode, DecodedInstruction};

mod arm;
mod thumb;

use crate::{IrExpr, IrStatement, IrValue};

/// Lifter context - tracks SSA version numbers for registers and variables
pub struct LifterContext {
    /// Current SSA version for each register (r0-r15)
    reg_versions: [u32; 16],
    /// Current SSA version counter
    version_counter: u32,
    /// Current CPU mode
    pub mode: ArmMode,
}

impl LifterContext {
    pub fn new() -> Self {
        Self {
            reg_versions: [0; 16],
            version_counter: 0,
            mode: ArmMode::Arm,
        }
    }

    /// Get current version of a register
    pub fn reg_version(&self, r: u8) -> u32 {
        if r < 16 {
            self.reg_versions[r as usize]
        } else {
            0
        }
    }

    /// Increment and return new version for a register
    pub fn next_reg_version(&mut self, r: u8) -> u32 {
        if r < 16 {
            self.version_counter += 1;
            self.reg_versions[r as usize] = self.version_counter;
            self.version_counter
        } else {
            0
        }
    }

    /// Create a register expression with current version
    pub fn reg_expr(&self, r: u8) -> IrExpr {
        IrExpr::Value(IrValue::Register(r))
    }

    /// Create a variable expression with next version
    pub fn var_expr(&mut self, name: String, ty: crate::GbaType) -> IrExpr {
        self.version_counter += 1;
        IrExpr::Value(IrValue::Variable {
            name,
            version: self.version_counter,
            ty,
        })
    }
}

impl Default for LifterContext {
    fn default() -> Self {
        Self::new()
    }
}

/// Main lifter that converts disassembled instructions to IR
pub struct Lifter {
    ctx: LifterContext,
}

impl Lifter {
    pub fn new() -> Self {
        Self {
            ctx: LifterContext::new(),
        }
    }

    /// Lift a single instruction to IR statements
    pub fn lift(&mut self, instr: &DecodedInstruction) -> Vec<IrStatement> {
        self.ctx.mode = instr.mode;

        // Delegate to architecture-specific lifters
        match instr.mode {
            ArmMode::Arm => arm::lift_data_processing(&mut self.ctx, instr),
            ArmMode::Thumb => thumb::lift_thumb(&mut self.ctx, instr),
        }
    }
    /// Lift multiple instructions
    pub fn lift_batch(&mut self, instructions: &[DecodedInstruction]) -> Vec<IrStatement> {
        instructions
            .iter()
            .filter(|instr| !instr.is_data)
            .flat_map(|instr| self.lift(instr))
            .collect()
    }
}

impl Default for Lifter {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    use crate::values::IrValue;

    #[test]
    fn test_lifter_context_versions() {
        let mut ctx = LifterContext::new();

        assert_eq!(ctx.reg_version(0), 0);

        let v1 = ctx.next_reg_version(0);
        assert_eq!(v1, 1);
        assert_eq!(ctx.reg_version(0), 1);

        let v2 = ctx.next_reg_version(0);
        assert_eq!(v2, 2);
        assert_eq!(ctx.reg_version(0), 2);
    }

    #[cfg(test)]
mod tests {
    use super::*;

    use gbatopy_disasm::Condition;

    #[test]
    fn test_lifter_context_creation() {
        let ctx = LifterContext::new();
        
        assert_eq!(ctx.version_counter, 0);
        assert_eq!(ctx.mode, ArmMode::Arm);
        
        // All register versions should be 0
        for i in 0..16 {
            assert_eq!(ctx.reg_version(i as u8), 0);
        }
    }

    #[test]
    fn test_lifter_context_versions() {
        let mut ctx = LifterContext::new();

        assert_eq!(ctx.reg_version(0), 0);

        let v1 = ctx.next_reg_version(0);
        assert_eq!(v1, 1);
        assert_eq!(ctx.reg_version(0), 1);

        let v2 = ctx.next_reg_version(0);
        assert_eq!(v2, 2);
        assert_eq!(ctx.reg_version(0), 2);
    }

    #[test]
    fn test_lifter_context_invalid_register() {
        let mut ctx = LifterContext::new();
        
        // Invalid register (>= 16) should return 0
        assert_eq!(ctx.reg_version(16), 0);
        assert_eq!(ctx.reg_version(20), 0);
        assert_eq!(ctx.next_reg_version(16), 0);
        assert_eq!(ctx.next_reg_version(255), 0);
    }

    #[test]
    fn test_lifter_context_multiple_registers() {
        let mut ctx = LifterContext::new();
        
        // Different registers should have independent version tracking
        let r0_v1 = ctx.next_reg_version(0);
        let r1_v1 = ctx.next_reg_version(1);
        let r0_v2 = ctx.next_reg_version(0);
        
        assert_eq!(r0_v1, 1);
        assert_eq!(r1_v1, 2);
        assert_eq!(r0_v2, 3);
        
        assert_eq!(ctx.reg_version(0), 3);
        assert_eq!(ctx.reg_version(1), 2);
    }

    #[test]
    fn test_lifter_context_reg_expr() {
        let ctx = LifterContext::new();
        
        let expr = ctx.reg_expr(5);
        
        assert!(matches!(expr, IrExpr::Value(IrValue::Register(5))));
    }

    #[test]
    fn test_lifter_context_var_expr() {
        let mut ctx = LifterContext::new();
        
        let expr1 = ctx.var_expr("test_var".to_string(), crate::GbaType::U32);
        let expr2 = ctx.var_expr("test_var2".to_string(), crate::GbaType::U16);
        
        // Each var_expr should increment the version counter
        assert!(matches!(expr1, IrExpr::Value(IrValue::Variable { version: 1, .. })));
        assert!(matches!(expr2, IrExpr::Value(IrValue::Variable { version: 2, .. })));
    }

    #[test]
    fn test_lifter_context_default() {
        let ctx = LifterContext::default();
        
        assert_eq!(ctx.version_counter, 0);
        assert_eq!(ctx.mode, ArmMode::Arm);
    }

    #[test]
    fn test_lifter_creation() {
        let _lifter = Lifter::new();
        
        // Lifter should have internal context
        // We can't directly access ctx, but we can test lift operations
    }

    #[test]
    fn test_lifter_default() {
        let lifter = Lifter::default();
        
        // Should be equivalent to new()
        let _ = lifter;
    }

    #[test]
    fn test_lifter_empty() {
        let mut lifter = Lifter::new();

        let instr = DecodedInstruction {
            address: 0x08000000,
            opcode: "NOP".to_string(),
            operands: vec![],
            condition: Some(Condition::Al),
            mode: ArmMode::Arm,
            raw: 0,
            sets_flags: false,
            width: 4,
            is_data: false,
        };

        let statements = lifter.lift(&instr);
        assert_eq!(statements.len(), 1);
        assert!(matches!(statements[0], IrStatement::Nop));
    }

    #[test]
    fn test_lifter_lift_mov_arm() {
        let mut lifter = Lifter::new();

        let instr = DecodedInstruction {
            address: 0x08000000,
            opcode: "MOV".to_string(),
            operands: vec![
                gbatopy_disasm::Operand::Register(0),
                gbatopy_disasm::Operand::Immediate(42),
            ],
            condition: Some(Condition::Al),
            mode: ArmMode::Arm,
            raw: 0,
            sets_flags: false,
            width: 4,
            is_data: false,
        };

        let statements = lifter.lift(&instr);
        assert_eq!(statements.len(), 1);
        assert!(matches!(statements[0], IrStatement::Assign { .. }));
    }

    #[test]
    fn test_lifter_lift_add_arm() {
        let mut lifter = Lifter::new();

        let instr = DecodedInstruction {
            address: 0x08000000,
            opcode: "ADD".to_string(),
            operands: vec![
                gbatopy_disasm::Operand::Register(0),
                gbatopy_disasm::Operand::Register(1),
                gbatopy_disasm::Operand::Register(2),
            ],
            condition: Some(Condition::Al),
            mode: ArmMode::Arm,
            raw: 0,
            sets_flags: false,
            width: 4,
            is_data: false,
        };

        let statements = lifter.lift(&instr);
        assert_eq!(statements.len(), 1);
        assert!(matches!(statements[0], IrStatement::Assign { .. }));
    }

    #[test]
    fn test_lifter_lift_swi_arm() {
        let mut lifter = Lifter::new();

        let instr = DecodedInstruction {
            address: 0x08000000,
            opcode: "SWI".to_string(),
            operands: vec![gbatopy_disasm::Operand::Immediate(0x12)],
            condition: Some(Condition::Al),
            mode: ArmMode::Arm,
            raw: 0,
            sets_flags: false,
            width: 4,
            is_data: false,
        };

        let statements = lifter.lift(&instr);
        assert_eq!(statements.len(), 1);
        
        if let IrStatement::Swi { number } = statements[0] {
            assert_eq!(number, 0x12);
        } else {
            unreachable!("Expected Swi statement");
        }
    }

    #[test]
    fn test_lifter_lift_bx_arm() {
        let mut lifter = Lifter::new();

        let instr = DecodedInstruction {
            address: 0x08000000,
            opcode: "BX".to_string(),
            operands: vec![gbatopy_disasm::Operand::Register(14)], // LR
            condition: Some(Condition::Al),
            mode: ArmMode::Arm,
            raw: 0,
            sets_flags: false,
            width: 4,
            is_data: false,
        };

        let statements = lifter.lift(&instr);
        assert_eq!(statements.len(), 1);
        assert!(matches!(statements[0], IrStatement::ModeSwitch { .. }));
    }

    #[test]
    fn test_lifter_lift_batch() {
        let mut lifter = Lifter::new();

        let instructions = vec![
            DecodedInstruction {
                address: 0x08000000,
                opcode: "NOP".to_string(),
                operands: vec![],
                condition: Some(Condition::Al),
                mode: ArmMode::Arm,
                raw: 0,
                sets_flags: false,
                width: 4,
                is_data: false,
            },
            DecodedInstruction {
                address: 0x08000004,
                opcode: "ADD".to_string(),
                operands: vec![
                    gbatopy_disasm::Operand::Register(0),
                    gbatopy_disasm::Operand::Register(1),
                    gbatopy_disasm::Operand::Register(2),
                ],
                condition: Some(Condition::Al),
                mode: ArmMode::Arm,
                raw: 0,
                sets_flags: false,
                width: 4,
                is_data: false,
            },
        ];

        let statements = lifter.lift_batch(&instructions);
        
        // Should lift both instructions
        assert_eq!(statements.len(), 2);
    }

    #[test]
    fn test_lifter_lift_batch_filters_data() {
        let mut lifter = Lifter::new();

        let instructions = vec![
            DecodedInstruction {
                address: 0x08000000,
                opcode: "NOP".to_string(),
                operands: vec![],
                condition: Some(Condition::Al),
                mode: ArmMode::Arm,
                raw: 0,
                sets_flags: false,
                width: 4,
                is_data: true, // This should be filtered out
            },
            DecodedInstruction {
                address: 0x08000004,
                opcode: "ADD".to_string(),
                operands: vec![
                    gbatopy_disasm::Operand::Register(0),
                    gbatopy_disasm::Operand::Register(1),
                    gbatopy_disasm::Operand::Register(2),
                ],
                condition: Some(Condition::Al),
                mode: ArmMode::Arm,
                raw: 0,
                sets_flags: false,
                width: 4,
                is_data: false,
            },
        ];

        let statements = lifter.lift_batch(&instructions);
        
        // Should only lift the non-data instruction
        assert_eq!(statements.len(), 1);
    }

    #[test]
    fn test_lifter_mode_tracking() {
        let mut lifter = Lifter::new();

        // Lift an ARM instruction
        let arm_instr = DecodedInstruction {
            address: 0x08000000,
            opcode: "NOP".to_string(),
            operands: vec![],
            condition: Some(Condition::Al),
            mode: ArmMode::Arm,
            raw: 0,
            sets_flags: false,
            width: 4,
            is_data: false,
        };
        let _ = lifter.lift(&arm_instr);

        // Lift a Thumb instruction
        let thumb_instr = DecodedInstruction {
            address: 0x08000002,
            opcode: "MOV".to_string(),
            operands: vec![
                gbatopy_disasm::Operand::Register(0),
                gbatopy_disasm::Operand::Immediate(42),
            ],
            condition: Some(Condition::Al),
            mode: ArmMode::Thumb,
            raw: 0x2000,
            sets_flags: false,
            width: 2,
            is_data: false,
        };
        let statements = lifter.lift(&thumb_instr);
        
        assert_eq!(statements.len(), 1);
    }
}
}
