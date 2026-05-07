use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ArmMode {
    Arm,
    Thumb,
}

impl ArmMode {
    pub fn name(&self) -> &'static str {
        match self {
            ArmMode::Arm => "Arm",
            ArmMode::Thumb => "Thumb",
        }
    }
}

pub struct ModeTracker {
    current_mode: ArmMode,
    mode_switches: Vec<(u32, ArmMode)>,
}

impl ModeTracker {
    pub fn new() -> Self {
        Self {
            current_mode: ArmMode::Arm,
            mode_switches: Vec::new(),
        }
    }

    pub fn current(&self) -> ArmMode {
        self.current_mode
    }

    pub fn switch_to(&mut self, address: u32, new_mode: ArmMode) {
        if new_mode != self.current_mode {
            self.mode_switches.push((address, new_mode));
            self.current_mode = new_mode;
        }
    }

    pub fn get_switches(&self) -> &[(u32, ArmMode)] {
        &self.mode_switches
    }

    pub fn instruction_width(&self) -> u8 {
        match self.current_mode {
            ArmMode::Arm => 4,
            ArmMode::Thumb => 2,
        }
    }
}

impl Default for ModeTracker {
    fn default() -> Self {
        Self::new()
    }
}
