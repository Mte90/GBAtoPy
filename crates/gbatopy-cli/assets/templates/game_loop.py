def run_transpiled(headless=False, frame_limit=None, screenshot_path=None, scale=1):
    """Execute transpiled GBA code using func_map dispatch"""
    
    def ror(value, amount):
        """Rotate right: (value >> amount) | (value << (32 - amount)) & 0xFFFFFFFF"""
        amount = amount & 31  # Mask to 0-31
        return ((value >> amount) | (value << (32 - amount))) & 0xFFFFFFFF
    
    frame_count = 0
    max_instructions = 1000000  # Safety limit
    instruction_count = 0
    
    print(f"Starting transpiled execution at PC=0x{r15:08X}")
    
    # Main execution loop
    while instruction_count < max_instructions:
        pc = r15
        
        # Look up function by address
        if pc not in func_map:
            print(f"Unknown PC: 0x{pc:08X} - execution halted")
            break
        
        # Get the function and call it
        func = func_map[pc]
        func()  # This updates r15 (PC) for next instruction
        
        instruction_count += 1
        
        # If PC didn't change, we're in an infinite loop
        if r15 == pc:
            print(f"PC unchanged at 0x{pc:08X} - infinite loop detected")
            break
        
        # Progress reporting every 10000 instructions
        if instruction_count % 10000 == 0:
            print(f"Executed {instruction_count} instructions, PC=0x{r15:08X}")
        
        # Frame-based execution (if headless mode with frame limit)
        if headless and frame_limit is not None:
            # Each frame = ~1000000 instructions (60fps at ~16.7M cycles/sec)
            frame_instructions = 1000000
            if instruction_count % frame_instructions == 0:
                frame_count += 1
                if frame_count > frame_limit:
                    print(f"Frame limit reached ({frame_limit} frames)")
                    break
    
    print(f"Execution complete. Total instructions: {instruction_count}")
    if screenshot_path:
        import pygame
        pygame.image.save(screen, screenshot_path)
        print(f"Screenshot saved to {screenshot_path}")
