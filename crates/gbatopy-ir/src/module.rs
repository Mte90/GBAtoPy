use serde::{Deserialize, Serialize};

use crate::blocks::IrFunction;
use crate::types::GbaType;

/// A global variable in the IR
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct IrGlobal {
    /// Global variable name
    pub name: String,

    /// Address in memory (for GBA globals)
    pub address: u32,

    /// Type of the global
    pub ty: GbaType,

    /// Initial value (if known)
    pub initial_value: Option<u32>,
}

/// The complete IR module containing all functions and globals
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub struct IrModule {
    /// All functions in the module
    pub functions: Vec<IrFunction>,

    /// All global variables
    pub globals: Vec<IrGlobal>,
}

impl IrModule {
    /// Create a new empty module
    pub fn new() -> Self {
        Self {
            functions: Vec::new(),
            globals: Vec::new(),
        }
    }

    /// Add a function to the module
    pub fn add_function(&mut self, func: IrFunction) {
        self.functions.push(func);
    }

    /// Add a global to the module
    pub fn add_global(&mut self, global: IrGlobal) {
        self.globals.push(global);
    }

    /// Find a function by name
    pub fn find_function(&self, name: &str) -> Option<&IrFunction> {
        self.functions.iter().find(|f| f.name == name)
    }

    /// Find a function by address
    pub fn find_function_by_address(&self, address: u32) -> Option<&IrFunction> {
        self.functions.iter().find(|f| f.address == address)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_module_serialization() {
        let mut module = IrModule::new();
        module.add_global(IrGlobal {
            name: "test_global".to_string(),
            address: 0x03000000,
            ty: GbaType::U32,
            initial_value: Some(42),
        });

        let json = serde_json::to_string_pretty(&module).unwrap();
        assert!(json.contains("test_global"));
        assert!(json.contains("50331648")); // 0x03000000 in decimal

        let deserialized: IrModule = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.globals.len(), 1);
        assert_eq!(deserialized.globals[0].name, "test_global");
    }

    #[test]
    fn test_find_function() {
        let mut module = IrModule::new();
        let func = crate::blocks::IrFunction {
            name: "main".to_string(),
            address: 0x08000000,
            params: vec![],
            blocks: vec![],
            return_type: None,
            mode: crate::ArmMode::Arm,
            mode_switches: vec![],
        };
        module.add_function(func);

        assert!(module.find_function("main").is_some());
        assert!(module.find_function("nonexistent").is_none());
        assert!(module.find_function_by_address(0x08000000).is_some());
    }
}
