-- PC trace script for mGBA — records program counter and CPU mode per frame
--
-- Usage:
--   GBATOPY_TRACE_PATH=/tmp/trace GBATOPY_TRACE_MAX_FRAMES=60 \
--     ./mgba/build/sdl/mgba -S scripts/trace/trace.lua <rom.gba>
--
-- Environment variables:
--   GBATOPY_TRACE_PATH       — output JSON path without extension (default: /tmp/trace)
--   GBATOPY_TRACE_MAX_FRAMES — max frames to trace before stopping (default: 1000)
--
-- Output: JSON file at <GBATOPY_TRACE_PATH>.json with structure:
--   {
--     "entries": [{ "frame": 1, "pc": "0x08000000", "mode": "ARM" }, ...],
--     "metadata": { "frame_count": 60, "sample": "per-frame" }
--   }

local output_path = os.getenv("GBATOPY_TRACE_PATH") or "/tmp/trace"
local max_frames = tonumber(os.getenv("GBATOPY_TRACE_MAX_FRAMES") or "1000")

local entries = {}
local frame_count = 0

-- Pre-compute output file path
local output_file = output_path .. ".json"

function writeTrace()
    local file = io.open(output_file, "w")
    if not file then
        print("ERROR: Cannot open " .. output_file .. " for writing")
        return
    end

    -- Write JSON manually (no json library in mGBA Lua)
    file:write("{\n")
    file:write('  "entries": [\n')

    for i, entry in ipairs(entries) do
        if i > 1 then file:write(",\n") end
        file:write("    {")
        file:write('"frame":' .. entry.frame)
        file:write(',"pc":"')
        file:write(entry.pc)
        file:write('","mode":"')
        file:write(entry.mode)
        file:write('"}')
    end

    file:write("\n  ],\n")
    file:write('  "metadata": {\n')
    file:write('    "frame_count":' .. frame_count .. ',\n')
    file:write('    "sample":"per-frame"\n')
    file:write("  }\n")
    file:write("}\n")

    file:close()
    print("Trace written to " .. output_file)
    print("Total frames traced: " .. frame_count)
end

function onFrame()
    frame_count = frame_count + 1

    if frame_count > max_frames then
        writeTrace()
        os.exit(0)
        return
    end

    -- Read PC register
    local pc = emu:readRegister("pc")
    local pc_hex = string.format("0x%08X", pc)

    -- Read CPSR and extract T-bit (bit 5) for CPU mode
    local cpsr = emu:readRegister("cpsr")
    local mode = (cpsr & 0x20) ~= 0 and "Thumb" or "ARM"

    table.insert(entries, {
        frame = frame_count,
        pc = pc_hex,
        mode = mode
    })
end

callbacks:add("frame", onFrame)

print("Trace script started")
print("Output path: " .. output_file)
print("Max frames: " .. max_frames)