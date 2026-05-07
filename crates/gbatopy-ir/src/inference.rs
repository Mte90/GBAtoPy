use crate::types::GbaType;
use crate::IrModule;
use std::collections::HashMap;

/// MMIO register addresses
const MMIO_BASE: u32 = 0x04000000;
const MMIO_END: u32 = 0x04000400;
/// VRAM base address
const VRAM_BASE: u32 = 0x06000000;
const VRAM_END: u32 = 0x06018000;
/// OAM base address
const OAM_BASE: u32 = 0x07000000;
const OAM_END: u32 = 0x07000400;
/// Palette RAM
const PALETTE_BASE: u32 = 0x05000000;
const PALETTE_END: u32 = 0x05000400;

pub struct TypeInferencer {
    pub reg_types: [GbaType; 16],
}

#[derive(Debug, Clone, PartialEq)]
pub enum InferenceResult {
    Incomplete,
    Success {
        types: HashMap<String, GbaType>,
        confidence: f32,
    },
    Error(String),
}

/// Register values observed from oracle trace
#[derive(Debug, Clone, Default)]
pub struct RegisterObservations {
    pub r0: Vec<u32>,
    pub r1: Vec<u32>,
    pub r2: Vec<u32>,
    pub r3: Vec<u32>,
    pub r4: Vec<u32>,
    pub r5: Vec<u32>,
    pub r6: Vec<u32>,
    pub r7: Vec<u32>,
    pub r8: Vec<u32>,
    pub r9: Vec<u32>,
    pub r10: Vec<u32>,
    pub r11: Vec<u32>,
    pub r12: Vec<u32>,
    pub sp: Vec<u32>,
    pub lr: Vec<u32>,
    pub pc: Vec<u32>,
}

impl TypeInferencer {
    pub fn new() -> Self {
        let mut reg_types = [GbaType::Unknown; 16];
        // Default: SP (13), LR (14), PC (15) are pointers
        reg_types[13] = GbaType::Ptr;
        reg_types[14] = GbaType::Ptr;
        reg_types[15] = GbaType::Ptr;
        Self { reg_types }
    }

    /// Infer types from oracle trace final register state
    pub fn infer_from_trace(&mut self, regs: &[u32; 16]) {
        for (i, &val) in regs.iter().enumerate() {
            self.reg_types[i] = self.infer_type_from_value(val);
        }
    }

    /// Infer a single type from an observed value
    fn infer_type_from_value(&self, val: u32) -> GbaType {
        // Check for MMIO pointer (0x04000000-0x040003FF)
        if val >= MMIO_BASE && val < MMIO_END {
            return GbaType::Ptr;
        }
        // Check for VRAM pointer
        if val >= VRAM_BASE && val < VRAM_END {
            return GbaType::Ptr;
        }
        // Check for OAM pointer
        if val >= OAM_BASE && val < OAM_END {
            return GbaType::Ptr;
        }
        // Check for Palette pointer
        if val >= PALETTE_BASE && val < PALETTE_END {
            return GbaType::Ptr;
        }
        // Check for ROM address (0x08000000-0x09FFFFFF)
        if val >= 0x08000000 && val < 0x0A000000 {
            return GbaType::Ptr;
        }
        // Check for RAM address (0x02000000-0x03000000)
        if val >= 0x02000000 && val < 0x03000000 {
            return GbaType::Ptr;
        }
        // Small values can be u8 or u16
        if val <= 0xFF {
            return GbaType::U8;
        }
        if val <= 0xFFFF {
            return GbaType::U16;
        }
        // Default to u32
        GbaType::U32
    }

    /// Add observed values to enhance inference
    pub fn add_observations(&mut self, obs: &RegisterObservations) {
        let all_regs = [
            &obs.r0, &obs.r1, &obs.r2, &obs.r3, &obs.r4, &obs.r5, &obs.r6, &obs.r7, &obs.r8,
            &obs.r9, &obs.r10, &obs.r11, &obs.r12, &obs.sp, &obs.lr, &obs.pc,
        ];

        for (i, reg_vals) in all_regs.iter().enumerate() {
            if reg_vals.is_empty() {
                continue;
            }

            // Check if all values are the same (constant)
            let all_same = reg_vals.iter().all(|&v| v == reg_vals[0]);

            if all_same {
                // Constant value - use it for inference
                let val = reg_vals[0];
                self.reg_types[i] = self.infer_type_from_value(val);
            } else {
                // Variable value - try to infer from range
                let max = *reg_vals.iter().max().unwrap();

                // If range fits in small type, use that
                if max <= 0xFF {
                    self.reg_types[i] = GbaType::U8;
                } else if max <= 0xFFFF {
                    self.reg_types[i] = GbaType::U16;
                } else {
                    self.reg_types[i] = GbaType::U32;
                }
            }
        }
    }

    pub fn infer_module(&self, module: &mut IrModule) -> InferenceResult {
        let mut types = HashMap::new();

        // Annotate functions with type information
        for func in &module.functions {
            // Add parameter types
            for (i, _param) in func.params.iter().enumerate() {
                let name = format!("{}_param{}", func.name, i);
                types.insert(name, GbaType::U32);
            }

            // Add return type if known
            if let Some(ret_ty) = &func.return_type {
                let name = format!("{}_ret", func.name);
                types.insert(name, ret_ty.clone());
            }
        }

        // Annotate globals with their types
        for global in &module.globals {
            types.insert(global.name.clone(), global.ty);
        }

        InferenceResult::Success {
            types,
            confidence: 0.8,
        }
    }

    /// Generate a type annotation string for a register
    pub fn type_annotation(&self, reg_idx: usize) -> String {
        if reg_idx >= 16 {
            return String::new();
        }

        match self.reg_types[reg_idx] {
            GbaType::Ptr => format!("# Ptr"),
            GbaType::U8 => format!("# U8"),
            GbaType::U16 => format!("# U16"),
            GbaType::U32 => format!("# U32"),
            GbaType::I8 => format!("# I8"),
            GbaType::I16 => format!("# I16"),
            GbaType::I32 => format!("# I32"),
            GbaType::Bool => format!("# Bool"),
            GbaType::Array { size } => format!("# [{}]", size),
            GbaType::Struct => format!("# Struct"),
            GbaType::Function => format!("# Fn"),
            GbaType::Void => format!("# Void"),
            GbaType::Unknown => String::new(),
        }
    }
}

impl Default for TypeInferencer {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_type_inferencer_creation() {
        let _ = TypeInferencer::new();
    }
}
