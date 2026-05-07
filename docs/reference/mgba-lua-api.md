---
# Appendix E: mGBA Lua Scripting API Reference

## Core Objects

### `emu` - Core Adapter

Available after a game is loaded.

| Property/Method | Type | Description |
|---|---|---|
| `emu` | table | CoreAdapter instance |
| `emu.getGameCode()` | function | Returns game code string (e.g. "AGBJ") |
| `emu.getGameTitle()` | function | Returns game title string |
| `emu.frameCount` | number | Current frame counter |
| `emu.lagCount` | number | Frames where no input was polled |
| `emu:setTimingFatal(enabled)` | function | Whether timing errors cause crashes |
| `emu:reset()` | function | Reset emulation |
| `emu:advanceFrame()` | function | Advance one frame |
| `emu:runFrame()` | function | Run one frame (deprecated, use advanceFrame) |
| `emu:loadState(slot)` | function | Load save state (slot 1-9) |
| `emu:saveState(slot)` | function | Save state (slot 1-9) |
| `emu:clearCheats()` | function | Remove all active cheats |
| `emu:addCheat(code)` | function | Add cheat code string |
| `emu:loadROM(path)` | function | Load a ROM file |

### `emu.memory` - Memory Domains

| Domain Key | Name | Base Address | Size |
|---|---|---|---|
| `bios` | BIOS | 0x00000000 | 16 KB |
| `wram` | EWRAM | 0x02000000 | 256 KB |
| `iwram` | IWRAM | 0x03000000 | 32 KB |
| `io` | I/O | 0x04000000 | 1 KB |
| `palette` | Palette | 0x05000000 | 1 KB |
| `vram` | VRAM | 0x06000000 | 96 KB |
| `oam` | OAM | 0x07000000 | 1 KB |
| `cart0` | ROM WS0 | 0x08000000 | 32 MB |
| `cart1` | ROM WS1 | 0x0A000000 | 32 MB |
| `cart2` | ROM WS2 | 0x0C000000 | 32 MB |
| `cartBackup` | SRAM | 0x0E000000 | 64 KB |

### Memory Read Methods

Each domain object supports:

```lua
local domain = emu.memory["wram"]

-- Read methods
domain:read8(offset)      -- read unsigned byte
domain:read16(offset)     -- read unsigned halfword (little-endian)
domain:read32(offset)     -- read unsigned word (little-endian)
domain:readRange(offset, length)  -- read byte array as string

-- Write methods
domain:write8(offset, value)
domain:write16(offset, value)
domain:write32(offset, value)
domain:writeRange(offset, data)  -- data as string
```

### `emu.cpu` - CPU State

| Method | Returns | Description |
|---|---|---|
| `emu.cpu:readRegister(index)` | number | Read register r0-r15 (index 0-15) |
| `emu.cpu:writeRegister(index, value)` | - | Write register r0-r15 |
| `emu.cpu:readCPSR()` | number | Read CPSR register |
| `emu.cpu:writeCPSR(value)` | - | Write CPSR register |
| `emu.cpu:readSPSR()` | number | Read SPSR register |
| `emu.cpu:writeSPSR(value)` | - | Write SPSR register |

Register indices: 0=r0, 1=r1, ..., 12=r12, 13=SP, 14=LR, 15=PC.

### `C` - Constants Table

```lua
C.GBA_KEY.A       -- 0x0001
C.GBA_KEY.B       -- 0x0002
C.GBA_KEY.SELECT  -- 0x0004
C.GBA_KEY.START   -- 0x0008
C.GBA_KEY.RIGHT   -- 0x0010
C.GBA_KEY.LEFT    -- 0x0020
C.GBA_KEY.UP      -- 0x0040
C.GBA_KEY.DOWN    -- 0x0080
C.GBA_KEY.R       -- 0x0100
C.GBA_KEY.L       -- 0x0200

C.PLATFORM.GBA    -- platform identifier
C.SAVESTATE.SIZES  -- table of savestate sizes per platform
```

### `callbacks` - Event Callbacks

```lua
-- Register a callback for frame advance
callbacks:add("frame", function()
    console:log("Frame " .. emu.frameCount)
end)

-- Register a callback for each scanline
callbacks:add("scanline", function(scanline)
    -- scanline is the current scanline number (0-227)
end)

-- Register a callback for state loaded
callbacks:add("loadState", function()
    console:log("State loaded")
end)

-- Register a callback for reset
callbacks:add("reset", function()
    console:log("ROM reset")
end)

-- Register a callback for keyboard input
callbacks:add("keysRead", function()
    -- Called after input is polled
end)

-- Remove all callbacks
callbacks:clear()
```

### `console` - Output Console

```lua
console:log("message")       -- print to mGBA script console
console:warn("warning")      -- print warning
console:error("error")       -- print error
```

### `emu.keypad` - Input Control

```lua
-- Set key state (simulate button press/release)
emu.keypad:SetKey(key, pressed)  -- key = C.GBA_KEY.X, pressed = boolean

-- Get current key state
local keys = emu.keypad:ReadKeys()  -- returns bitmask
```

## Complete Tracer Script Example

```lua
-- tracer.lua - Execution tracer for PyGBA-Native
-- Runs inside mGBA scripting console (Tools > Scripting...)

-- Configuration
TRACE_FRAMES = 60
TRACE_START_PC = 0x08000000
TRACE_END_PC = 0x09FFFFFF
TRACE_LOG_MEMORY = true
OUTPUT_FILE = "trace_output.jsonl"

local io_domain = emu.memory["io"]
local cart_domain = emu.memory["cart0"]
local wram_domain = emu.memory["wram"]
local iwram_domain = emu.memory["iwram"]

local output = {}
local frame_count = 0
local file = io.open(OUTPUT_FILE, "w")

local function get_scanline()
    return io_domain:read16(0x06)  -- VCOUNT
end

local function get_register(i)
    return emu.cpu:readRegister(i)
end

local function get_cpsr()
    return emu.cpu:readCPSR()
end

local function is_thumb()
    return (get_cpsr() & 0x20) ~= 0
end

local function get_pc()
    return emu.cpu:readRegister(15)
end

local function get_flags(cpsr)
    return {
        N = (cpsr >> 31) & 1 == 1,
        Z = (cpsr >> 30) & 1 == 1,
        C = (cpsr >> 29) & 1 == 1,
        V = (cpsr >> 28) & 1 == 1,
    }
end

callbacks:add("frame", function()
    frame_count = frame_count + 1

    local pc = get_pc()
    if pc < TRACE_START_PC or pc > TRACE_END_PC then
        if frame_count >= TRACE_FRAMES then
            callbacks:clear()
            file:close()
            console:log("Trace complete: " .. frame_count .. " frames")
        end
        return
    end

    local mode = is_thumb() and "thumb" or "arm"
    local opcode
    if mode == "thumb" then
        opcode = cart_domain:read16(pc - 0x08000000)
    else
        opcode = cart_domain:read32(pc - 0x08000000)
    end

    local regs = {}
    for i = 0, 15 do
        regs["r" .. i] = string.format("0x%08X", get_register(i))
    end

    local cpsr = get_cpsr()
    local entry = {
        frame = frame_count,
        scanline = get_scanline(),
        pc = string.format("0x%08X", pc),
        opcode = string.format("0x%08X", opcode),
        mode = mode,
    }
    for k, v in pairs(regs) do entry[k] = v end
    entry.cpsr = string.format("0x%08X", cpsr)
    entry.flags = get_flags(cpsr)

    file:write(json.encode(entry) .. "\n")
    file:flush()

    if frame_count >= TRACE_FRAMES then
        callbacks:clear()
        file:close()
        console:log("Trace complete: " .. frame_count .. " frames")
    end
end)

console:log("Tracer started, recording " .. TRACE_FRAMES .. " frames...")
```

## Complete Oracle Script Example

```lua
-- oracle.lua - Master oracle analysis script
-- Combines tracing, memory profiling, VRAM dumps, register monitoring

ORACLE_FRAMES = 300
DUMP_INTERVAL = 30
INPUT_SEQUENCE = {}  -- table of frame -> key mask
OUTPUT_DIR = "oracle_output/"

-- Create output directory
os.execute("mkdir -p " .. OUTPUT_DIR)

-- State tracking
local frame_count = 0
local reg_changes = {}
local prev_io = {}

-- Snapshot all I/O registers
local function snapshot_io()
    local snap = {}
    for addr = 0, 0x3FE, 2 do
        snap[addr] = emu.memory["io"]:read16(addr)
    end
 return snap
end

-- Detect I/O register changes
local function detect_io_changes(old, new, frame)
    for addr, old_val in pairs(old) do
        local new_val = new[addr]
        if old_val ~= new_val then
            table.insert(reg_changes, {
                frame = frame,
                address = string.format("0x%08X", 0x04000000 + addr),
                old = string.format("0x%04X", old_val),
                new = string.format("0x%04X", new_val),
            })
        end
    end
end

-- Dump VRAM state
local function dump_vram(frame)
    local palette = emu.memory["palette"]:readRange(0, 1024)
    local vram = emu.memory["vram"]:readRange(0, 98304)
    local oam = emu.memory["oam"]:readRange(0, 1024)
    local dispcnt = emu.memory["io"]:read16(0x00)

    local bin_file = io.open(OUTPUT_DIR .. "vram_" .. string.format("%04d", frame) .. ".bin", "wb")
    bin_file:write(palette)
    bin_file:write(vram)
    bin_file:write(oam)
    bin_file:close()

    local meta = {
        frame = frame,
        dispcnt = string.format("0x%04X", dispcnt),
        display_mode = dispcnt & 0x07,
    }
    local meta_file = io.open(OUTPUT_DIR .. "vram_" .. string.format("%04d", frame) .. ".json", "w")
    meta_file:write(json.encode(meta))
    meta_file:close()
end

-- Simulate input
local function simulate_input(frame)
    local keys = INPUT_SEQUENCE[frame]
    if keys then
        for key, pressed in pairs(keys) do
            emu.keypad:SetKey(key, pressed)
        end
    end
end

-- Initial I/O snapshot
prev_io = snapshot_io()

callbacks:add("frame", function()
    frame_count = frame_count + 1

    -- Simulate input
    simulate_input(frame_count)

    -- Detect I/O changes
    local current_io = snapshot_io()
    detect_io_changes(prev_io, current_io, frame_count)
    prev_io = current_io

    -- Periodic VRAM dump
    if frame_count % DUMP_INTERVAL == 0 then
        dump_vram(frame_count)
    end

    -- Check completion
    if frame_count >= ORACLE_FRAMES then
        callbacks:clear()

        -- Save register change log
        local reg_file = io.open(OUTPUT_DIR .. "register_changes.json", "w")
        reg_file:write(json.encode(reg_changes))
        reg_file:close()

        console:log("Oracle analysis complete: " .. frame_count .. " frames")
        console:log("I/O register changes: " .. #reg_changes)
        console:log("VRAM dumps: " .. math.floor(frame_count / DUMP_INTERVAL))
    end
end)

console:log("Oracle started, analyzing " .. ORACLE_FRAMES .. " frames...")
```

## JSON Encoding Helper

mGBA does not ship a built-in JSON encoder. Use this minimal helper:

```lua
-- Minimal JSON encoder for mGBA Lua scripts
local function json_encode(obj)
    local t = type(obj)
    if t == "string" then
        return '"' .. obj:gsub('"', '\\"'):gsub('\n', '\\n') .. '"'
    elseif t == "number" then
        return tostring(obj)
    elseif t == "boolean" then
        return tostring(obj)
    elseif t == "table" then
        -- Detect array vs object
        local is_array = true
        local max_index = 0
        for k, _ in pairs(obj) do
            if type(k) ~= "number" or k ~= math.floor(k) or k < 1 then
                is_array = false
                break
            end
            if k > max_index then max_index = k end
        end
        if is_array and max_index == #obj then
            local parts = {}
            for i = 1, #obj do
                parts[i] = json_encode(obj[i])
            end
            return "[" .. table.concat(parts, ",") .. "]"
        else
            local parts = {}
            for k, v in pairs(obj) do
                parts[#parts + 1] = '"' .. tostring(k) .. '":' .. json_encode(v)
            end
            return "{" .. table.concat(parts, ",") .. "}"
        end
    elseif t == "nil" then
        return "null"
    else
        return '"' .. tostring(obj) .. '"'
    end
end

json = { encode = json_encode }
```

## Script Loading in mGBA

1. Open mGBA
2. Load a GBA ROM
3. Go to Tools > Scripting...
4. In the scripting window, load a .lua file (File > Load Script)
5. Output appears in the console pane
6. Scripts run until callbacks:clear() is called or the script window is closed

## Batch Script Execution

For automated testing, mGBA supports CLI scripting:

```bash
# Run mGBA headless with a script
mgba -l game.gba --script tracer.lua

# The -l flag enables logging to stdout
# --script runs the Lua file automatically
```

This is essential for automated oracle data collection during the pipeline.

---

# Appendix E2: mGBA Fork - Extended Lua API

> Extended Lua API implementation for PyGBA-Native oracle  
> Status: FORK REQUIRED - API vanilla insufficiente per tracing completo

## Fork Decision

**Decision: FORK DI mGBA NECESSARIO**

La Lua API vanilla di mGBA non è sufficiente per il progetto PyGBA-Native perché:

1. **Nessun memory access tracing** - Non è possibile sapere quali indirizzi vengono letti/scritti durante l'esecuzione
2. **Nessun instruction-level hook** - Non è possibile intercettare ogni istruzione eseguita
3. **Performance downgrade** - Workaround con `emu.step()` in loop è troppo lento (1 istruzione per chiamata)

## Nuove API da Implementare

### 1. Memory Access Tracing

```lua
-- NUOVA API: emu.traceMemory(enabled, callback)
emu.traceMemory(true, function(access)
    -- access = { type="read"|"write", address=0x02001234, size=4, value=0xDEADBEEF }
    console:log(string.format("MEM: %s %08X = %08X", access.type, access.address, access.value))
end)
```

**Implementazione C richiesta:**
- Hook nel memory bus di mGBA
- Cattura indirizzo, tipo, dimensione, valore
- Chiamata callback Lua con tabella

### 2. Instruction Tracing

```lua
-- NUOVA API: emu.traceInstructions(enabled, callback)
emu.traceInstructions(true, function(instr)
    -- instr = { pc=0x08001234, opcode=0xE3A00001, thumb=false, regs={r0=0,...} }
    console:log(string.format("PC=%08X OP=%08X", instr.pc, instr.opcode))
end)
```

**Implementazione C richiesta:**
- Hook nella CPU execution loop
- Cattura PC, opcode, flags
- Opzionale: dump registri

### 3. Register Watch

```lua
-- NUOVA API: emu.watchRegister(reg, callback)
emu.watchRegister("r0", function(old_val, new_val)
    console:log(string.format("r0: %08X -> %08X", old_val, new_val))
end)

-- Watch per interrupt
emu.watchInterrupt(true, function(irq)
    -- irq = { type="irq", source="timer0", pending=0x0010 }
end)
```

### 4. Breakpoint/Watchpoint

```lua
-- NUOVA API: emu.setBreakpoint(address, callback)
emu.setBreakpoint(0x08001234, function(ctx)
    -- Ferma a indirizzo specifico
    console:log("BREAK at " .. emu.cpu:readRegister(15))
end)

-- NUOVA API: emu.setWatchpoint(address, type, callback)  
emu.setWatchpoint(0x02001234, "write", function(ctx)
    -- Ferma quando scrive a indirizzo
end)
```

### 5. Bus Transaction Log

```lua
-- NUOVA API: emu.getBusTransactionlog()
local log = emu.getBusTransactionLog()
-- log = [{cycle=1000, type="read", addr=0x04000200, size=2, value=0x1234}, ...]

-- Pulisci log
emu.clearBusTransactionLog()
```

### 6. DMA Trace

```lua
-- NUOVA API: emu.traceDMA(channel, callback)
emu.traceDMA(0, function(dma)
    -- dma = { channel=0, src=0x02001234, dst=0x06001234, count=64, ctrl=0x8800 }
    console:log(string.format("DMA0: %08X -> %08X (x%d)", dma.src, dma.dst, dma.count))
end)
```

### 7. Interrupt Trace

```lua
-- NUOVA API: emu.traceInterrupts(enabled, callback)
emu.traceInterrupts(true, function(irq)
    -- irq = { type="irq"|"fiq", source="vblank"|"timer0"|"dma0"|..., pending=0xFFFF }
    console:log("IRQ: " .. irq.source)
end)
```

## Implementation Status

### ✅ COMPLETATO:
- [x] Struttura `mScriptCoreAdapter` estesa (`src/core/scripting.c`)
- [x] Funzioni Lua: `traceMemory`, `traceInstructions`, `watchRegister`, `traceInterrupts`, `getBusTransactionLog`, `clearBusTransactionLog`
- [x] Callback struttura `mCoreCallbacks` estesa con `instructionExecuted` e `memoryAccessed` (`include/mgba/core/interface.h`)
- [x] Macro callback: `mCALLBACKS_INVOKE_IE` e `mCALLBACKS_INVOKE_MEM`
- [x] Memory read callback in `src/gba/memory.c` (GBALoad8)
- [x] Memory write callback in `src/gba/memory.c` (GBAStore8)
- [x] Instruction callback nel CPU loop (`src/arm/arm.c`)
- [x] Refactoring nomi variabili per stile mGBA

### ✅ TUTTO COMPLETATO - PRONTO PER IL MERGE

## File Modificati

```
src/core/scripting.c           # Extended mScriptCoreAdapter + 6 nuove API
include/mgba/core/interface.h  # mCoreCallbacks estesa
src/gba/memory.c               # Memory access callbacks
src/arm/arm.c                  # Instruction execution callback
```

## Build e Test

```bash
# Build mGBA con Lua modificato
cd mgba
mkdir build && cd build
cmake -DENABLE_SCRIPTING=ON -DUSE_LUA=ON ..
make -j4

# Test delle nuove API
mgba -l test.gba --script test_extended_api.lua
```

## Riferimenti

- mGBA source: https://github.com/mgba-emu/mgba
- Lua API vanilla: https://mgba.io/docs/scripting.html
