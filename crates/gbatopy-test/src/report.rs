use crate::types::{TestResult, TestStatus};
use chrono::Utc;
use std::fs;
use std::path::Path;

pub struct Reporter;

impl Reporter {
    pub fn console_report(results: &[TestResult]) {
        let passed = results.iter().filter(|r| r.status == TestStatus::Pass).count();
        let failed = results.iter().filter(|r| r.status == TestStatus::Fail).count();
        let errors = results.iter().filter(|r| r.status == TestStatus::Error).count();
        let skipped = results.iter().filter(|r| r.status == TestStatus::Skipped).count();
        
        println!("=== Test Results ===");
        println!("Passed:  {}", passed);
        println!("Failed:  {}", failed);
        println!("Errors:  {}", errors);
        println!("Skipped: {}", skipped);
        println!("Total:   {}", results.len());
        
        if results.is_empty() {
            println!("No tests were executed.");
            return;
        }
        
        let total = results.len() as f64;
        let pass_rate = if total > 0.0 { (passed as f64 / total) * 100.0 } else { 0.0 };
        println!("Pass rate: {:.1}%", pass_rate);
    }
    
    pub fn json_report(results: &[TestResult], path: &Path) {
        let json = serde_json::to_string_pretty(results).unwrap();
        fs::write(path, json).unwrap();
    }
    
    pub fn junit_report(results: &[TestResult], path: &Path) {
        let _passed = results.iter().filter(|r| r.status == TestStatus::Pass).count();
        let failures = results.iter().filter(|r| r.status == TestStatus::Fail).count();
        let errors = results.iter().filter(|r| r.status == TestStatus::Error).count();
        let skipped = results.iter().filter(|r| r.status == TestStatus::Skipped).count();
        
        let mut xml = String::from("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<testsuites");
        xml.push_str(&format!(" timestamp=\"{}\" name=\"gbatopy-test\">", Utc::now().to_rfc3339()));
        xml.push('\n');
        
        xml.push_str(&format!("  <testsuite name=\"gbatopy-test\" tests=\"{}\" failures=\"{}\" errors=\"{}\" skipped=\"{}\" time=\"{}\">\n",
            results.len(), failures, errors, skipped,
            (results.iter().map(|r| r.duration.as_secs_f64()).sum::<f64>()).to_string().replace('.', "")
        ));
        
        for result in results {
            let time_str = result.duration.as_secs_f64().to_string().replace('.', "");
            xml.push_str(&format!("    <testcase name=\"{}\" classname=\"{}\" time=\"{}\">\n",
                result.name,
                result.test_type,
                time_str
            ));
            if result.status == TestStatus::Fail {
                xml.push_str(&format!("      <failure message=\"{}\">{}</failure>\n", result.message, result.message));
            } else if result.status == TestStatus::Error {
                xml.push_str(&format!("      <error message=\"{}\">{}</error>\n", result.message, result.message));
            } else if result.status == TestStatus::Skipped {
                xml.push_str("      <skipped/>\n");
            }
            xml.push_str("    </testcase>\n");
        }
        
        xml.push_str("  </testsuite>\n</testsuites>\n");
        fs::write(path, xml).unwrap();
    }
}
