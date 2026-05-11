// Old codegen modules removed - PyBoyAdvance pipeline doesn't need ARM/Thumb codegen
// This module is kept for potential future use but currently empty

use std::collections::HashMap;

// Placeholder for future codegen if needed
pub struct CodeGenerator {
    _templates: HashMap<String, String>,
}

impl CodeGenerator {
    pub fn new(_assets_dir: &std::path::Path) -> Result<Self, String> {
        Ok(CodeGenerator {
            _templates: HashMap::new(),
        })
    }

    pub fn new_with_pyboyadvance() -> Result<Self, String> {
        // New PyBoyAdvance-based generator doesn't use templates
        Ok(CodeGenerator {
            _templates: HashMap::new(),
        })
    }
}
