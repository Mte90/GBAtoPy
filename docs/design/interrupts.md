# Interrupt-Driven Execution Architecture for GBAtoPy

## Problem Statement

Current architecture blocks on ROM execution:
```python
call_func(r15)  # Executes ROM until it returns (never for most games - infinite loops)
while frame_count < frames:
    ppu.render_frame()  # NEVER REACHED - code after call_func() is unreachable
```

**Root Cause:** GBA games run in infinite loops, never returning from main. The `call_func()` is blocking and doesn't yield control back to the rendering loop.

## Solution: VBlank Timer-Based Yielding

Implement cycle-based yielding that simulates GBA's hardware VBlank interrupt behavior:
- Execute ROM instructions in chunks bounded by cycle count
- Yield to PPU rendering every ~280,968 cycles (GBA's VBlank period)
- No ROM modifications required
- Preserves ROM behavior while enabling interleaved rendering

## Architecture Design

### Cycle Tracking Model

```
GBA Hardware: 16.78 MHz CPU → ~280,968 cycles per frame at 60 Hz
Simplified Model: 4 cycles per ARM instruction (average cost)
```

### Execution Flow

```
┌─────────────────────────────────────────────────────────┐
│ Frame Loop (controlled by Python)                       │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Instruction Chunk Loop (controlled by cycles)    │   │
│  │  ┌──────────────────────────────────────────┐   │   │
│  │  │ main_entry()                             │   │   │
│  │  │  1. Execute ONE instruction via call_func│   │   │
│  │  │  2. Increment cycle counter (+4)         │   │   │
│  │  │  3. Check if VBlank threshold reached    │   │   │
│  │  └──────────────────────────────────────────┘   │   │
│  │  Returns: True if VBlank pending, False to continue│ │
│  └──────────────────────────────────────────────────┘   │
│  ↓ When VBlank threshold reached                         │
│  1. Reset cycle counter                                  │
│  2. Call ppu.render_frame()                             │
│  3. Set VBlank interrupt flag (unblocks ROM wait loops) │
│  4. Increment frame count                               │
└─────────────────────────────────────────────────────────┘
```

### Key Components

#### 1. Cycle Tracking Globals (game_loop.py)
```python
_cycle_count = 0
_CYCLES_PER_FRAME = 280968  # GBA VBlank period
_vblank_pending = False
```

#### 2. Yield Control Functions
```python
def _increment_cycles(cycle_cost=4):
    """Track cycles and set VBlank flag when threshold reached"""
    global _cycle_count, _vblank_pending
    _cycle_count += cycle_cost
    if _cycle_count >= _CYCLES_PER_FRAME:
        _vblank_pending = True

def _check_vblank():
    """Returns True if VBlank interrupt should fire"""
    return _vblank_pending

def _reset_vblank():
    """Reset cycle counter after VBlank handling"""
    global _cycle_count, _vblank_pending
    _cycle_count = 0
    _vblank_pending = False
```

#### 3. Non-Blocking Instruction Execution
```python
def main_entry():
    """Execute ONE instruction, return True when should yield to rendering"""
    global r15, _vblank_pending
    
    # Initialize once
    if not hasattr(main_entry, "_initialized"):
        load_assets()
        main_entry._initialized = True
    
    # Execute one instruction from current PC
    current_pc = r15 & 0xFFFFFFFE
    func = func_map.get(current_pc)
    
    if func:
        func()  # Updates r15 (PC) for next instruction
    
    # Track cycles (simplified: 4 cycles per ARM instruction)
    _increment_cycles(4)
    
    # Check if we should yield to rendering
    return _check_vblank()
```

#### 4. Interrupt-Driven Execution Loop
```python
def run_game(frames=None, headless=False, scale=2, screenshot=None):
    """Execute ROM with VBlank-driven rendering"""
    global framebuffer, r15, screen, clock
    
    pygame.init()
    load_assets()
    
    # Initialize CPU state
    r15 = ROM_BASE  # Start at ROM entry point (0x08000000)
    _load_bin_files()
    
    frame_count = 0
    
    # Interrupt-driven execution loop
    while frame_count < (frames or 1000):
        # Execute instructions until VBlank cycle count reached
        while not _check_vblank():
            main_entry()  # Execute one instruction, check if should yield
        
        # VBlank interrupt triggered - render frame
        _reset_vblank()
        ppu.parse_oam()
        ppu.render_sprites()
        set_vblank_flag()  # Set Z flag for VBlank wait loops in ROM
        ppu.render_frame()
        frame_count += 1
        
        # Display if not headless
        if not headless:
            surf = ppu.get_surface()
            if surf:
                pygame.transform.scale(surf, (240 * scale, 160 * scale), screen)
                pygame.display.flip()
            clock.tick(60)
    
    # Save screenshot if requested
    if screenshot and frame_count > 0:
        surf = ppu.get_surface()
        if surf:
            pygame.image.save(surf, screenshot)
    
    return frame_count
```

#### 5. Codegen Integration (arm_ops.rs, thumb_ops.rs)

Modify instruction emission to track cycles:
```rust
// In emit_arm() for branch instructions
code.push_str(&format!(
    "    r15 = 0x{:08X}\n    call_func(r15)\n    _increment_cycles(4)\n",
    target
));
```

## Alternative Approaches Considered

### Option 1: Cooperative Yield Points in Generated Code
**Approach**: Insert explicit yield points at safe locations (function returns, loop boundaries)

**Pros:**
- More precise control over yield locations
- No cycle counting overhead

**Cons:**
- Requires analysis of generated code to find safe yield points
- May not yield frequently enough for smooth rendering
- Complex to implement correctly

**Decision**: Rejected - cycle-based approach is simpler and more predictable

### Option 2: Hardware VBlank Interrupt Simulation
**Approach**: Implement full interrupt controller with VBlank timer triggering IRQ

**Pros:**
- Most accurate to real GBA hardware
- ROM can enable/disable VBlank interrupts naturally

**Cons:**
- Requires significant infrastructure (interrupt controller, vector table handling)
- ROM must have interrupt handlers set up
- More complex than needed for basic rendering

**Decision**: Rejected - overkill for initial implementation, can add later if needed

### Option 3: Time-Based Yielding (wall clock)
**Approach**: Yield every 16.67ms (real-time 60Hz)

**Pros:**
- Matches real frame timing
- Simple to implement

**Cons:**
- Doesn't account for variable instruction execution time
- May desynchronize ROM execution from rendering
- Depends on system clock, not deterministic

**Decision**: Rejected - cycle-based is more deterministic and matches GBA model

## Why Cycle-Based VBlank Yielding?

1. **Matches GBA hardware**: Real GBA triggers VBlank every 280,968 cycles
2. **Non-invasive**: No ROM code changes required
3. **Simple cycle accounting**: Track cycles per instruction, yield when threshold reached
4. **Preserves ROM behavior**: ROM executes same instructions, just interleaved with rendering
5. **Deterministic**: Same ROM + same cycles = same behavior
6. **Handles VBlank wait loops**: Setting VBlank flag unblocks ROM code waiting for interrupts

## Implementation Checklist

- [x] Architecture design document
- [ ] Modify `game_loop.py` template with cycle tracking
- [ ] Update `run_game()` function with interrupt-driven loop
- [ ] Update `arm_ops.rs` to emit cycle tracking after instructions
- [ ] Update `thumb_ops.rs` to emit cycle tracking after instructions  
- [ ] Test with hello_world.gba
- [ ] Verify screenshot is non-black
- [ ] Test with other ROMs to ensure compatibility

## Edge Cases & Considerations

### VBlank Wait Loops
Some ROM code may wait for VBlank interrupt before proceeding:
```assembly
wait_vblank:
    ldr r0, [DISPSTAT]
    test r0, #1      ; Check VBlank bit
    beq wait_vblank  ; Loop until VBlank
```

**Solution**: `set_vblank_flag()` sets `z=1` before calling `render_frame()`, which unblocks these wait loops.

### Variable Instruction Costs
Real ARM instructions have varying cycle costs (1-6 cycles depending on type, memory access, etc.)

**Current**: Simplified to 4 cycles per instruction (average)
**Future**: Could implement more accurate cycle counting based on instruction type

### First Frame Initialization
Ensure assets load before first render cycle to avoid black frame.

**Solution**: Call `load_assets()` once in `main_entry()` initialization.

## Testing Strategy

1. **Hello World Test**: Transpile and run hello_world.gba, verify non-black screenshot
2. **Frame Count Verification**: Ensure correct number of frames rendered
3. **VBlank Flag Test**: Verify ROM code waiting on VBlank unblocks correctly
4. **Regression Test**: Ensure existing functionality (LDM/STM, screenshots) still works

## Success Criteria

- [ ] Architecture document created and reviewed
- [ ] hello_world.gba produces non-black screenshot
- [ ] Frame rendering occurs DURING ROM execution (not after)
- [ ] No changes to ROM behavior or output
- [ ] Existing functionality preserved

## Future Enhancements

1. **Accurate cycle counting**: Track actual instruction costs (1-6 cycles)
2. **Full interrupt controller**: Implement IE/IF/IME registers and interrupt vectors
3. **HBlank interrupts**: Add HBlank timing for scanline effects
4. **Timer interrupts**: Implement GBA timer hardware
5. **DMA sync**: Synchronize DMA transfers with VBlank/HBlank

## References

- GBA Hardware Manual: https://gbdev.io/gbafaq/
- VBlank timing: 280,968 cycles at ~16.78 MHz = ~60 Hz
- Cycle counting: ARM7TDMI instruction costs vary 1-6 cycles
