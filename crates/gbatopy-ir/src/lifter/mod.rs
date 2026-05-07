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

    use gbatopy_disasm::Condition;

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
}
