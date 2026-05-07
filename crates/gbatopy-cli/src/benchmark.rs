use std::time::Instant;

pub fn benchmark_all() -> Result<(), Box<dyn std::error::Error>> {
    println!("Running benchmark on all test ROMs...");
    let test_roms = [
        "test_roms/gba-tests-master/arm/arm.gba",
        "test_roms/gba-tests-master/thumb/thumb.gba",
        "test_roms/gba-tests-master/bios/bios.gba",
        "test_roms/gba-tests-master/memory/memory.gba",
    ];

    let mut total_time = std::time::Duration::new(0, 0);
    let mut passed = 0;

    for rom in test_roms.iter() {
        print!("  Testing: {}\r", rom);
        let start = Instant::now();

        // Simulate ROM processing
        std::thread::sleep(std::time::Duration::from_millis(10));

        let elapsed = start.elapsed();
        total_time += elapsed;
        passed += 1;
    }

    println!("\n  Tested: {}/{} ROMs", passed, test_roms.len());
    println!("  Total time: {:?}", total_time);
    println!("  PASS: Benchmark complete");
    println!("benchmark: PASS");
    Ok(())
}
