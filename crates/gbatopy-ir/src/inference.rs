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
        if (MMIO_BASE..MMIO_END).contains(&val) {
            return GbaType::Ptr;
        }
        // Check for VRAM pointer
        if (VRAM_BASE..VRAM_END).contains(&val) {
            return GbaType::Ptr;
        }
        // Check for OAM pointer
        if (OAM_BASE..OAM_END).contains(&val) {
            return GbaType::Ptr;
        }
        // Check for Palette pointer
        if (PALETTE_BASE..PALETTE_END).contains(&val) {
            return GbaType::Ptr;
        }
        // Check for ROM address (0x08000000-0x09FFFFFF)
        if (0x08000000..0x0A000000).contains(&val) {
            return GbaType::Ptr;
        }
        // Check for RAM address (0x02000000-0x03000000)
        if (0x02000000..0x03000000).contains(&val) {
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
                types.insert(name, *ret_ty);
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
            GbaType::Ptr => "# Ptr".to_string(),
            GbaType::U8 => "# U8".to_string(),
            GbaType::U16 => "# U16".to_string(),
            GbaType::U32 => "# U32".to_string(),
            GbaType::I8 => "# I8".to_string(),
            GbaType::I16 => "# I16".to_string(),
            GbaType::I32 => "# I32".to_string(),
            GbaType::Bool => "# Bool".to_string(),
            GbaType::Array { size } => format!("# [{}]", size),
            GbaType::Struct => "# Struct".to_string(),
            GbaType::Function => "# Fn".to_string(),
            GbaType::Void => "# Void".to_string(),
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
    use crate::blocks::IrFunction;
    use crate::values::IrExpr;
    use crate::ArmMode;
    use crate::IrGlobal;


    #[test]
    fn test_type_inferencer_creation() {
        let inferencer = TypeInferencer::new();
        
        // SP, LR, PC should be pointers by default
        assert_eq!(inferencer.reg_types[13], GbaType::Ptr);
        assert_eq!(inferencer.reg_types[14], GbaType::Ptr);
        assert_eq!(inferencer.reg_types[15], GbaType::Ptr);
        
        // Other registers should be unknown
        for i in 0..13 {
            assert_eq!(inferencer.reg_types[i], GbaType::Unknown);
        }
    }

    #[test]
    fn test_infer_small_values() {
        let mut inferencer = TypeInferencer::new();
        
        // Small values (<= 0xFF) should be inferred as U8
        let regs = [0x00, 0x42, 0xFF, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
        inferencer.infer_from_trace(&regs);
        
        assert_eq!(inferencer.reg_types[0], GbaType::U8);
        assert_eq!(inferencer.reg_types[1], GbaType::U8);
        assert_eq!(inferencer.reg_types[2], GbaType::U8);
    }

    #[test]
    fn test_infer_medium_values() {
        let mut inferencer = TypeInferencer::new();
        
        // Values > 0xFF but <= 0xFFFF should be U16
        let regs = [0x100, 0x1234, 0xFFFF, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
        inferencer.infer_from_trace(&regs);
        
        assert_eq!(inferencer.reg_types[0], GbaType::U16);
        assert_eq!(inferencer.reg_types[1], GbaType::U16);
        assert_eq!(inferencer.reg_types[2], GbaType::U16);
    }

    #[test]
    fn test_infer_large_values() {
        let mut inferencer = TypeInferencer::new();
        
        // Values > 0xFFFF should be U32
        let regs = [0x10000, 0x12345678, 0xFFFFFFFF, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
        inferencer.infer_from_trace(&regs);
        
        assert_eq!(inferencer.reg_types[0], GbaType::U32);
        assert_eq!(inferencer.reg_types[1], GbaType::U32);
        assert_eq!(inferencer.reg_types[2], GbaType::U32);
    }

    #[test]
    fn test_infer_mmio_pointers() {
        let mut inferencer = TypeInferencer::new();
        
        // MMIO addresses should be inferred as Ptr
        let regs = [0x04000000, 0x04000100, 0x040003FF, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
        inferencer.infer_from_trace(&regs);
        
        assert_eq!(inferencer.reg_types[0], GbaType::Ptr);
        assert_eq!(inferencer.reg_types[1], GbaType::Ptr);
        assert_eq!(inferencer.reg_types[2], GbaType::Ptr);
    }

    #[test]
    fn test_infer_vram_pointers() {
        let mut inferencer = TypeInferencer::new();
        
        // VRAM addresses should be inferred as Ptr
        let regs = [0x06000000, 0x06008000, 0x06017FFF, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
        inferencer.infer_from_trace(&regs);
        
        assert_eq!(inferencer.reg_types[0], GbaType::Ptr);
        assert_eq!(inferencer.reg_types[1], GbaType::Ptr);
        assert_eq!(inferencer.reg_types[2], GbaType::Ptr);
    }

    #[test]
    fn test_infer_oam_pointers() {
        let mut inferencer = TypeInferencer::new();
        
        // OAM addresses should be inferred as Ptr
        let regs = [0x07000000, 0x07000200, 0x070003FF, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
        inferencer.infer_from_trace(&regs);
        
        assert_eq!(inferencer.reg_types[0], GbaType::Ptr);
        assert_eq!(inferencer.reg_types[1], GbaType::Ptr);
        assert_eq!(inferencer.reg_types[2], GbaType::Ptr);
    }

    #[test]
    fn test_infer_palette_pointers() {
        let mut inferencer = TypeInferencer::new();
        
        // Palette addresses should be inferred as Ptr
        let regs = [0x05000000, 0x05000200, 0x050003FF, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
        inferencer.infer_from_trace(&regs);
        
        assert_eq!(inferencer.reg_types[0], GbaType::Ptr);
        assert_eq!(inferencer.reg_types[1], GbaType::Ptr);
        assert_eq!(inferencer.reg_types[2], GbaType::Ptr);
    }

    #[test]
    fn test_infer_rom_pointers() {
        let mut inferencer = TypeInferencer::new();
        
        // ROM addresses should be inferred as Ptr
        let regs = [0x08000000, 0x08001234, 0x08010000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
        inferencer.infer_from_trace(&regs);
        
        assert_eq!(inferencer.reg_types[0], GbaType::Ptr);
        assert_eq!(inferencer.reg_types[1], GbaType::Ptr);
        assert_eq!(inferencer.reg_types[2], GbaType::Ptr);
    }

    #[test]
    fn test_infer_ram_pointers() {
        let mut inferencer = TypeInferencer::new();
        
        // RAM addresses should be inferred as Ptr
        let regs = [0x02000000, 0x02001234, 0x02FFFFFF, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
        inferencer.infer_from_trace(&regs);
        
        assert_eq!(inferencer.reg_types[0], GbaType::Ptr);
        assert_eq!(inferencer.reg_types[1], GbaType::Ptr);
        assert_eq!(inferencer.reg_types[2], GbaType::Ptr);
    }

    #[test]
    fn test_observations_constant_values() {
        let mut inferencer = TypeInferencer::new();
        let mut obs = RegisterObservations::default();
        
        // All R0 values are the same constant
        obs.r0 = vec![42, 42, 42, 42];
        
        inferencer.add_observations(&obs);
        assert_eq!(inferencer.reg_types[0], GbaType::U8);
    }

    #[test]
    fn test_observations_variable_values() {
        let mut inferencer = TypeInferencer::new();
        let mut obs = RegisterObservations::default();
        
        // R0 has varying values, max is 0x1000
        obs.r0 = vec![0, 100, 500, 0x1000];
        
        inferencer.add_observations(&obs);
        assert_eq!(inferencer.reg_types[0], GbaType::U16);
    }

    #[test]
    fn test_observations_empty() {
        let mut inferencer = TypeInferencer::new();
        let obs = RegisterObservations::default();
        
        // Empty observations should not change types
        inferencer.add_observations(&obs);
        
        // SP, LR, PC should still be pointers
        assert_eq!(inferencer.reg_types[13], GbaType::Ptr);
        assert_eq!(inferencer.reg_types[14], GbaType::Ptr);
        assert_eq!(inferencer.reg_types[15], GbaType::Ptr);
    }

    #[test]
    fn test_type_annotation_ptr() {
        let mut inferencer = TypeInferencer::new();
        inferencer.reg_types[0] = GbaType::Ptr;
        
        assert_eq!(inferencer.type_annotation(0), "# Ptr");
    }

    #[test]
    fn test_type_annotation_u8() {
        let mut inferencer = TypeInferencer::new();
        inferencer.reg_types[1] = GbaType::U8;
        
        assert_eq!(inferencer.type_annotation(1), "# U8");
    }

    #[test]
    fn test_type_annotation_u16() {
        let mut inferencer = TypeInferencer::new();
        inferencer.reg_types[2] = GbaType::U16;
        
        assert_eq!(inferencer.type_annotation(2), "# U16");
    }

    #[test]
    fn test_type_annotation_u32() {
        let mut inferencer = TypeInferencer::new();
        inferencer.reg_types[3] = GbaType::U32;
        
        assert_eq!(inferencer.type_annotation(3), "# U32");
    }

    #[test]
    fn test_type_annotation_unknown() {
        let inferencer = TypeInferencer::new();
        
        // Unknown type should return empty string
        assert_eq!(inferencer.type_annotation(0), "");
    }

    #[test]
    fn test_type_annotation_invalid_reg() {
        let inferencer = TypeInferencer::new();
        
        // Invalid register index should return empty string
        assert_eq!(inferencer.type_annotation(16), "");
        assert_eq!(inferencer.type_annotation(20), "");
    }

    #[test]
    fn test_infer_module_annotations() {
        let mut inferencer = TypeInferencer::new();
        let mut module = IrModule::new();
        
        // Add a function with return type
        let func = IrFunction {
            name: "test_func".to_string(),
            address: 0x08000000,
            params: vec![IrExpr::register(0), IrExpr::register(1)],
            blocks: vec![],
            return_type: Some(GbaType::U32),
            mode: ArmMode::Arm,
            mode_switches: vec![],
        };
        module.add_function(func);
        
        // Add a global
        module.add_global(IrGlobal {
            name: "test_global".to_string(),
            address: 0x03000000,
            ty: GbaType::U16,
            initial_value: Some(100),
        });
        
        let result = inferencer.infer_module(&mut module);
        
        match result {
            InferenceResult::Success { types, confidence } => {
                assert_eq!(confidence, 0.8);
                assert!(types.contains_key("test_func_param0"));
                assert!(types.contains_key("test_func_param1"));
                assert!(types.contains_key("test_func_ret"));
                assert!(types.contains_key("test_global"));
            }
            _ => unreachable!("Expected InferenceResult::Success"),
        }
    }
}
