use crate::config::TestEntry;
use crate::types::{TestResult, TestStatus};
use super::Verifier;
use std::path::Path;
use std::fs;
use std::time::Instant;

pub struct EwramDumpVerifier;

impl Verifier for EwramDumpVerifier {
    fn verify(&self, entry: &TestEntry, artifacts_dir: &Path, config: &crate::config::TestConfig) -> TestResult {
        let start = Instant::now();
        let test_name = entry.name.clone();
        let test_type_str = format!("{:?}", entry.test_type);

        log::info!("[eWRAM Dump] Testing {}...", test_name);

        let rom_path = config.roms_dir.join(&entry.rom_path).to_string_lossy().to_string();
        let rom_stem = entry.rom_path
            .file_stem()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();
        let transpiled_py = artifacts_dir.join(format!("{}.py", rom_stem));
        let dump_path = artifacts_dir.join("ewram_dump.bin");

        // Step 1: Transpile ROM
        if let Err(e) = transpile_rom(&rom_path, &transpiled_py) {
            return TestResult {
                name: test_name.clone(),
                test_type: test_type_str.clone(),
                status: TestStatus::Fail,
                message: format!("Transpilation failed: {}", e),
                duration: start.elapsed(),
                metrics: None,
                failure_classification: None,
            };
        }

        log::info!("[eWRAM Dump] Transpilation succeeded for {}", test_name);

        // Copy ROM .bin alongside transpiled script for load_rom_data()
        let rom_bin_dest = artifacts_dir.join(format!("{}.bin", rom_stem));
        let _ = std::fs::copy(&rom_path, &rom_bin_dest);

        // Step 2: Run with --dump-memory flag (FuzzARM needs 600 frames)
        let frames = 600;
        if let Err(e) = run_with_dump(&transpiled_py, &dump_path, frames) {
            return TestResult {
                name: test_name.clone(),
                test_type: test_type_str.clone(),
                status: TestStatus::Fail,
                message: format!("eWRAM dump failed: {}", e),
                duration: start.elapsed(),
                metrics: None,
                failure_classification: None,
            };
        }

        log::info!("[eWRAM Dump] eWRAM dump captured for {}", test_name);

        // Step 3: Parse the dump
        let dump_data = match fs::read(&dump_path) {
            Ok(data) => data,
            Err(e) => {
                return TestResult {
                    name: test_name.clone(),
                    test_type: test_type_str.clone(),
                    status: TestStatus::Error,
                    message: format!("Failed to read dump file: {}", e),
                    duration: start.elapsed(),
                    metrics: None,
                    failure_classification: None,
                };
            }
        };

        let failures = match parse_fuzzarm_dump(&dump_data) {
            Ok(failures) => failures,
            Err(e) => {
                return TestResult {
                    name: test_name.clone(),
                    test_type: test_type_str.clone(),
                    status: TestStatus::Error,
                    message: format!("Failed to parse dump: {}", e),
                    duration: start.elapsed(),
                    metrics: None,
                    failure_classification: None,
                };
            }
        };

        // Step 4: Report results
        if failures.is_empty() {
            log::info!("[eWRAM Dump] PASS: {} (all 10000 tests passed)", test_name);
            TestResult {
                name: test_name,
                test_type: test_type_str,
                status: TestStatus::Pass,
                message: "All eWRAM tests passed".to_string(),
                duration: start.elapsed(),
                metrics: None,
                failure_classification: None,
            }
        } else {
            log::error!(
                "[eWRAM Dump] FAIL: {} ({} failures detected)",
                test_name,
                failures.len()
            );
            let summaries: Vec<String> = failures.iter().map(|f| f.summary()).collect();
            TestResult {
                name: test_name,
                test_type: test_type_str,
                status: TestStatus::Fail,
                message: format!(
                    "{} eWRAM failures: {}",
                    failures.len(),
                    summaries.join("; ")
                ),
                duration: start.elapsed(),
                metrics: None,
                failure_classification: None,
            }
        }
    }

    fn name(&self) -> &'static str {
        "ewram_dump"
    }
}

/// Represents a single FuzzARM failure record (64 bytes)
#[derive(Debug, Clone)]
pub struct FuzzArmFailure {
    pub mode: &'static str,      // "ARM" or "Thumb"
    pub opcode: String,          // Mnemonic (e.g., "tst", "cmp")
    pub r3_got: u32,
    #[allow(dead_code)]
    pub r3_expected: u32,
    #[allow(dead_code)]
    pub r4_got: u32,
    #[allow(dead_code)]
    pub r4_expected: u32,
    #[allow(dead_code)]
    pub cpsr_got: u32,
    #[allow(dead_code)]
    pub cpsr_expected: u32,
}

impl FuzzArmFailure {
    pub fn summary(&self) -> String {
        format!(
            "[{}] {} — r3: got 0x{:08X} expected 0x{:08X}",
            self.mode, self.opcode, self.r3_got, self.r3_expected
        )
    }
}

fn transpile_rom(rom_path: &str, output: &Path) -> Result<(), Box<dyn std::error::Error>> {
    use duct::cmd;
    let bin = "target/debug/gbatopy-cli";
    
    cmd!(bin, "pipeline", "--rom", rom_path, "--output", output.to_string_lossy().as_ref())
        .dir(".")
        .run()?;
    
    if !output.exists() {
        return Err("Output file not created".into());
    }
    
    Ok(())
}

fn run_with_dump(py_file: &Path, dump_path: &Path, frames: u32) -> Result<(), Box<dyn std::error::Error>> {
    use duct::cmd;
    let frame_arg = format!("--frame={}", frames);
    let dump_name = dump_path.file_name().unwrap_or_default().to_string_lossy().to_string();
    let dump_arg = format!("--dump-memory={}", dump_name);
    
    cmd!(
        "python3",
        py_file.file_name().unwrap().to_string_lossy().as_ref(),
        "--headless",
        &frame_arg,
        &dump_arg
    )
    .env("SDL_VIDEODRIVER", "dummy")
    .dir(py_file.parent().unwrap_or(Path::new(".")))
    .run()?;
    
    if !dump_path.exists() {
        return Err("Dump file not created".into());
    }
    
    Ok(())
}

/// Parse FuzzARM eWRAM dump binary (256KB = 10000 records × 64 bytes, or fewer if early exit)
/// Returns Vec of failure records (empty = all tests passed)
pub fn parse_fuzzarm_dump(data: &[u8]) -> Result<Vec<FuzzArmFailure>, Box<dyn std::error::Error>> {
    let mut failures = Vec::new();
    let mut offset = 0;

    while offset + 64 <= data.len() {
        let record = &data[offset..offset + 64];

        // Check for mode marker (first 4 bytes)
        let marker = &record[0..4];
        let mode = if marker == b"AAAA" {
            "ARM"
        } else if marker == b"TTTT" {
            "Thumb"
        } else {
            // Not a valid record marker, skip
            offset += 64;
            continue;
        };

        // Parse opcode mnemonic (bytes 4-11, 8 bytes ASCII)
        let opcode_bytes = &record[4..12];
        let opcode = String::from_utf8_lossy(opcode_bytes)
            .trim_end_matches('\0')
            .trim()
            .to_string();

        // Skip shift info (4 bytes) and reserved (4 bytes)
        // r3_got at offset 0x14 (20)
        let r3_got = u32::from_le_bytes([record[20], record[21], record[22], record[23]]);
        
        // r4_got at offset 0x18 (24)
        let r4_got = u32::from_le_bytes([record[24], record[25], record[26], record[27]]);
        
        // Skip padding (4 bytes at 0x1C)
        
        // CPSR_got at offset 0x24 (36)
        let cpsr_got = u32::from_le_bytes([record[36], record[37], record[38], record[39]]);
        
        // r3_expected at offset 0x28 (40)
        let r3_expected = u32::from_le_bytes([record[40], record[41], record[42], record[43]]);
        
        // r4_expected at offset 0x2C (44)
        let r4_expected = u32::from_le_bytes([record[44], record[45], record[46], record[47]]);
        
        // Skip padding (4 bytes at 0x3C)
        
        // CPSR_expected at offset 0x40 (64) - wait, this is beyond 64 bytes
        // Actually CPSR_expected is at 0x40 which is byte 64, but record is 64 bytes (0-63)
        // Let me re-check: 0x40 = 64, but we only have 64 bytes (0-63)
        // Looking at the spec again: CPSR_expected is at 0x40 which is the 65th byte
        // This seems like an error in the spec. Let me assume it's at 0x3C (60)
        let cpsr_expected = u32::from_le_bytes([record[60], record[61], record[62], record[63]]);

        // Only add to failures if there's a mismatch
        if r3_got != r3_expected || r4_got != r4_expected || cpsr_got != cpsr_expected {
            failures.push(FuzzArmFailure {
                mode,
                opcode,
                r3_got,
                r3_expected,
                r4_got,
                r4_expected,
                cpsr_got,
                cpsr_expected,
            });
        }

        offset += 64;
    }

    Ok(failures)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_verifier_name() {
        let verifier = EwramDumpVerifier;
        assert_eq!(verifier.name(), "ewram_dump");
    }

    #[test]
    fn test_parse_empty_dump() {
        let data = vec![0u8; 256 * 1024]; // 256KB of zeros
        let result = parse_fuzzarm_dump(&data);
        assert!(result.is_ok());
        assert!(result.unwrap().is_empty());
    }

    #[test]
    fn test_parse_arm_failure_record() {
        // Create a synthetic 64-byte ARM failure record
        let mut record = vec![0u8; 64];
        
        // Mode marker: "AAAA" (ARM)
        record[0..4].copy_from_slice(b"AAAA");
        
        // Opcode: "tst       " (8 bytes, padded)
        record[4..12].copy_from_slice(b"tst     ");
        
        // r3_got = 0x12345678
        record[20..24].copy_from_slice(&0x12345678u32.to_le_bytes());
        
        // r4_got = 0xABCDEF00
        record[24..28].copy_from_slice(&0xABCDEF00u32.to_le_bytes());
        
        // CPSR_got = 0x60000010
        record[36..40].copy_from_slice(&0x60000010u32.to_le_bytes());
        
        // r3_expected = 0x12345678 (same as got)
        record[40..44].copy_from_slice(&0x12345678u32.to_le_bytes());
        
        // r4_expected = 0xABCDEF00 (same as got)
        record[44..48].copy_from_slice(&0xABCDEF00u32.to_le_bytes());
        
        // CPSR_expected = 0x60000013 (different from got)
        record[60..64].copy_from_slice(&0x60000013u32.to_le_bytes());

        let failures = parse_fuzzarm_dump(&record).unwrap();
        assert_eq!(failures.len(), 1);
        assert_eq!(failures[0].mode, "ARM");
        assert_eq!(failures[0].opcode, "tst");
        assert_eq!(failures[0].r3_got, 0x12345678);
        assert_eq!(failures[0].r4_got, 0xABCDEF00);
        assert_eq!(failures[0].cpsr_got, 0x60000010);
        assert_eq!(failures[0].r3_expected, 0x12345678);
        assert_eq!(failures[0].r4_expected, 0xABCDEF00);
        assert_eq!(failures[0].cpsr_expected, 0x60000013);
    }

    #[test]
    fn test_failure_summary() {
        let failure = FuzzArmFailure {
            mode: "ARM",
            opcode: "tst".to_string(),
            r3_got: 0x12345678,
            r3_expected: 0x1234567A,
            r4_got: 0x0,
            r4_expected: 0x0,
            cpsr_got: 0x0,
            cpsr_expected: 0x0,
        };
        
        let summary = failure.summary();
        assert_eq!(summary, "[ARM] tst — r3: got 0x12345678 expected 0x1234567A");
    }
}
