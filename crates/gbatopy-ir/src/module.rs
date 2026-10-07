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

    #[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_module_new_creates_empty() {
        let module = IrModule::new();
        
        assert!(module.functions.is_empty());
        assert!(module.globals.is_empty());
    }

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
    fn test_add_function() {
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
        
        module.add_function(func.clone());
        
        assert_eq!(module.functions.len(), 1);
        assert_eq!(module.functions[0].name, "main");
    }

    #[test]
    fn test_add_multiple_functions() {
        let mut module = IrModule::new();
        
        module.add_function(crate::blocks::IrFunction {
            name: "func1".to_string(),
            address: 0x08000000,
            params: vec![],
            blocks: vec![],
            return_type: None,
            mode: crate::ArmMode::Arm,
            mode_switches: vec![],
        });
        
        module.add_function(crate::blocks::IrFunction {
            name: "func2".to_string(),
            address: 0x08000100,
            params: vec![],
            blocks: vec![],
            return_type: None,
            mode: crate::ArmMode::Thumb,
            mode_switches: vec![],
        });
        
        assert_eq!(module.functions.len(), 2);
    }

    #[test]
    fn test_add_global() {
        let mut module = IrModule::new();
        let global = IrGlobal {
            name: "counter".to_string(),
            address: 0x03000000,
            ty: GbaType::U32,
            initial_value: Some(0),
        };
        
        module.add_global(global);
        
        assert_eq!(module.globals.len(), 1);
        assert_eq!(module.globals[0].name, "counter");
    }

    #[test]
    fn test_add_multiple_globals() {
        let mut module = IrModule::new();
        
        module.add_global(IrGlobal {
            name: "global1".to_string(),
            address: 0x03000000,
            ty: GbaType::U32,
            initial_value: None,
        });
        
        module.add_global(IrGlobal {
            name: "global2".to_string(),
            address: 0x03000004,
            ty: GbaType::U16,
            initial_value: Some(42),
        });
        
        assert_eq!(module.globals.len(), 2);
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

    #[test]
    fn test_find_function_by_address() {
        let mut module = IrModule::new();
        
        module.add_function(crate::blocks::IrFunction {
            name: "func1".to_string(),
            address: 0x08000000,
            params: vec![],
            blocks: vec![],
            return_type: None,
            mode: crate::ArmMode::Arm,
            mode_switches: vec![],
        });
        
        module.add_function(crate::blocks::IrFunction {
            name: "func2".to_string(),
            address: 0x08000100,
            params: vec![],
            blocks: vec![],
            return_type: None,
            mode: crate::ArmMode::Arm,
            mode_switches: vec![],
        });
        
        assert!(module.find_function_by_address(0x08000000).is_some());
        assert!(module.find_function_by_address(0x08000100).is_some());
        assert!(module.find_function_by_address(0x08000050).is_none());
    }

    #[test]
    fn test_find_function_case_sensitive() {
        let mut module = IrModule::new();
        module.add_function(crate::blocks::IrFunction {
            name: "Main".to_string(),
            address: 0x08000000,
            params: vec![],
            blocks: vec![],
            return_type: None,
            mode: crate::ArmMode::Arm,
            mode_switches: vec![],
        });
        
        // Should be case-sensitive
        assert!(module.find_function("Main").is_some());
        assert!(module.find_function("main").is_none());
        assert!(module.find_function("MAIN").is_none());
    }

    #[test]
    fn test_ir_global_default_values() {
        let global = IrGlobal {
            name: "test".to_string(),
            address: 0x03000000,
            ty: GbaType::U32,
            initial_value: None,
        };
        
        assert_eq!(global.name, "test");
        assert_eq!(global.address, 0x03000000);
        assert_eq!(global.ty, GbaType::U32);
        assert!(global.initial_value.is_none());
    }

    #[test]
    fn test_ir_module_default() {
        let module = IrModule::default();
        
        assert!(module.functions.is_empty());
        assert!(module.globals.is_empty());
    }

    #[test]
    fn test_module_clone() {
        let mut module = IrModule::new();
        module.add_function(crate::blocks::IrFunction {
            name: "test".to_string(),
            address: 0x08000000,
            params: vec![],
            blocks: vec![],
            return_type: Some(GbaType::U32),
            mode: crate::ArmMode::Arm,
            mode_switches: vec![],
        });
        
        let cloned = module.clone();
        
        assert_eq!(module.functions.len(), cloned.functions.len());
        assert_eq!(module.functions[0].name, cloned.functions[0].name);
    }

    #[test]
    fn test_module_equality() {
        let mut module1 = IrModule::new();
        module1.add_function(crate::blocks::IrFunction {
            name: "test".to_string(),
            address: 0x08000000,
            params: vec![],
            blocks: vec![],
            return_type: None,
            mode: crate::ArmMode::Arm,
            mode_switches: vec![],
        });
        
        let mut module2 = IrModule::new();
        module2.add_function(crate::blocks::IrFunction {
            name: "test".to_string(),
            address: 0x08000000,
            params: vec![],
            blocks: vec![],
            return_type: None,
            mode: crate::ArmMode::Arm,
            mode_switches: vec![],
        });
        
        assert_eq!(module1, module2);
    }

    #[test]
    fn test_module_inequality() {
        let mut module1 = IrModule::new();
        module1.add_function(crate::blocks::IrFunction {
            name: "test1".to_string(),
            address: 0x08000000,
            params: vec![],
            blocks: vec![],
            return_type: None,
            mode: crate::ArmMode::Arm,
            mode_switches: vec![],
        });
        
        let mut module2 = IrModule::new();
        module2.add_function(crate::blocks::IrFunction {
            name: "test2".to_string(),
            address: 0x08000000,
            params: vec![],
            blocks: vec![],
            return_type: None,
            mode: crate::ArmMode::Arm,
            mode_switches: vec![],
        });
        
        assert_ne!(module1, module2);
    }
}
}
