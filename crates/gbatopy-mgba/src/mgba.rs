use log::debug;

use crate::{types::*, Error};

#[derive(Debug)]
pub struct MgbaConfig {
    pub rom_path: String,
    pub max_instructions: u64,
    pub timeout_seconds: u64,
    pub output_path: String,
}

pub struct MgbaOracle {
    config: MgbaConfig,
}

impl MgbaOracle {
    pub fn new(config: MgbaConfig) -> Self {
        Self { config }
    }

    pub fn run(&self) -> Result<OracleTrace> {
        debug!("Starting mGBA oracle trace");
        debug!(
            "ROM: {}, Max instructions: {}",
            self.config.rom_path, self.config.max_instructions
        );

        let rom_data = std::fs::read(&self.config.rom_path).map_err(|e| Error::IoError(e))?;

        let rom_size = rom_data.len();
        let output_path = format!("/tmp/oracle_trace_{}.json", std::process::id());
        let lua_script_path = format!("/tmp/oracle_{}.lua", std::process::id());

        let lua_script = format!(
            r##"
local max_instructions = {}
local output_file = "{}"
local instructions = 0
local trace = {{}}

function onInstruction()
    instructions = instructions + 1
    if instructions > max_instructions then
        emu.registerStop()
        return
    end
    table.insert(trace, {{ address = emu.getregister("pc"), opcode = "ARM" }})
end

emu.registerbefore(onInstruction)

local function onSave()
    local file = io.open(output_file, 'w')
    if file then
        file:write("{{")
        file:write('"entries":[')
        for i, e in ipairs(trace) do
            if i > 1 then file:write(',') end
            file:write('{{')
            file:write('"address":')
            file:write(e.address)
            file:write(',"opcode":"')
            file:write(e.opcode)
            file:write('"}}')
        end
        file:write('],"metadata":{{')
        file:write('"instruction_count":')
        file:write(#trace)
        file:write('}}')
        file:write('}}')
        file:close()
    end
end

emu.registerexit(onSave)
print("Oracle started")
"##,
            self.config.max_instructions, output_path
        );

        std::fs::write(&lua_script_path, lua_script).map_err(|e| Error::IoError(e))?;

        let output = std::process::Command::new("mgba/build/sdl/mgba")
            .arg("-C")
            .arg(format!("scripting.file={}", lua_script_path))
            .arg(&self.config.rom_path)
            .arg("--no-audio")
            .arg("--no-video")
            .output()
            .map_err(|e| Error::MgbaLaunch(format!("mGBA failed: {}", e)))?;

        std::fs::remove_file(&lua_script_path).ok();

        if !output.status.success() {
            return Err(Error::MgbaLaunch(format!("mGBA exit: {:?}", output.status)));
        }

        if std::path::Path::new(&output_path).exists() {
            let json = std::fs::read_to_string(&output_path)?;
            std::fs::remove_file(&output_path).ok();
            let trace: OracleTrace = serde_json::from_str(&json)?;
            Ok(trace)
        } else {
            self.run_fallback(rom_size)
        }
    }

    fn run_fallback(&self, rom_size: usize) -> Result<OracleTrace> {
        debug!("Running static-only fallback mode");

        let entries = Vec::new();

        let metadata = TraceMetadata {
            timestamp: chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string(),
            mgba_version: None,
            mode: OracleMode::StaticOnly,
            instruction_count: 0,
            duration_ms: 0,
            mode_switches: Vec::new(),
        };

        Ok(OracleTrace {
            rom_path: self.config.rom_path.clone(),
            rom_size,
            entries,
            metadata,
        })
    }
}
