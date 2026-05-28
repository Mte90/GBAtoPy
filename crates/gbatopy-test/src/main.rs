use clap::Parser;
use std::path::{Path, PathBuf};

use gbatopy_test::config::{TestConfig, TestEntry, TestType};
use gbatopy_test::report::Reporter;
use gbatopy_test::runner::TestRunner;
use gbatopy_test::types::TestStatus;

#[derive(Parser, Debug)]
#[command(name = "gbatopy-test")]
#[command(about = "GBA transpiler test runner", long_about = None)]
struct Args {
    /// Path to TOML configuration file
    #[arg(long)]
    config: PathBuf,

    /// Filter by test name pattern (substring match)
    #[arg(long)]
    filter: Option<String>,

    /// Filter by test type: Smoke, ScreenshotGolden, ScreenshotMgba, EwramDump, PassFailScreen, AssertionText
    #[arg(long)]
    test_type: Option<String>,

    /// Output format: console, json, junit (default: all)
    #[arg(long, default_value = "all")]
    format: String,

    /// Output directory for reports (default: test-reports)
    #[arg(long, default_value = "test-reports")]
    output_dir: PathBuf,

    /// Dry run: load config but don't execute tests
    #[arg(long)]
    dry_run: bool,
}

fn load_config(path: &Path) -> Result<TestConfig, Box<dyn std::error::Error>> {
    let content = std::fs::read_to_string(path)?;
    let config: TestConfig = toml::from_str(&content)?;
    Ok(config)
}

fn _load_entries(config: &TestConfig) -> Result<Vec<TestEntry>, Box<dyn std::error::Error>> {
    let test_entries: Vec<TestEntry> = toml::from_str(&toml::to_string_pretty(config).unwrap())?;
    Ok(test_entries)
}

fn main() {
    let args = Args::parse();

    let config = match load_config(&args.config) {
        Ok(cfg) => cfg,
        Err(e) => {
            eprintln!("Error loading config: {}", e);
            std::process::exit(1);
        }
    };

    if args.dry_run {
        println!("=== Dry Run: Configuration Loaded ===");
        println!("ROMs directory: {:?}", config.roms_dir);
        println!("Output directory: {:?}", config.output_dir);
        println!("Parallel workers: {}", config.parallel);
        return;
    }

    let runner = TestRunner::from_config(config.clone());

    // Get test entries from config
    let entries = config.tests.clone();

    // Apply filters. Use filter if provided, test_type filter if provided, otherwise all entries
    let filtered_entries: Vec<TestEntry> = if let Some(ref filter) = args.filter {
        entries.iter().filter(|e| e.name.contains(filter)).cloned().collect()
    } else {
        entries.clone()
    };

    let test_type_filter = if let Some(ref ttype) = args.test_type {
        match ttype.as_str() {
            "Smoke" => Some(TestType::Smoke),
            "ScreenshotGolden" => Some(TestType::ScreenshotGolden),
            "ScreenshotMgba" => Some(TestType::ScreenshotMgba),
            "EwramDump" => Some(TestType::EwramDump),
            "PassFailScreen" => Some(TestType::PassFailScreen),
            "AssertionText" => Some(TestType::AssertionText),
            _ => None,
        }
    } else {
        None
    };

    // Run tests
    println!("=== Running GBAtoPy Tests ===");
    println!("Total entries: {}", filtered_entries.len());
    if let Some(tt) = test_type_filter {
        println!("Filter: {:?}", tt);
    }

    let results = if let Some(tt) = test_type_filter {
        runner.run_by_type(&filtered_entries, &tt)
    } else {
        runner.run_all(&filtered_entries)
    };

    // Create output directory
    std::fs::create_dir_all(&args.output_dir).ok();

    // Generate reports based on format
    let results_vec = results.tests.clone();
    Reporter::console_report(&results_vec);

    if args.format == "json" || args.format == "all" {
        let json_path = args.output_dir.join("results.json");
        Reporter::json_report(&results_vec, &json_path);
        println!("\nJSON report: {:?}", json_path);
    }

    if args.format == "junit" || args.format == "all" {
        let junit_path = args.output_dir.join("results-junit.xml");
        Reporter::junit_report(&results_vec, &junit_path);
        println!("JUnit report: {:?}", junit_path);
    }

    // Exit with error code if any failures/errors
    let failed = results_vec.iter().filter(|r| r.status == TestStatus::Fail).count();
    let errors = results_vec.iter().filter(|r| r.status == TestStatus::Error).count();

    if failed > 0 || errors > 0 {
        std::process::exit(1);
    }
}
