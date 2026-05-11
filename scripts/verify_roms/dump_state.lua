-- dump_state.lua: Dump CPU registers + MMIO state from mGBA
-- Usage: mgba -r rom.gba -s scripts/verify_roms/dump_state.lua

local FRAMES_TO_RUN = 60
local OUTPUT_FILE = "state_dump.json"

-- CPU register names (ARM7TDMI)
local CPU_REGISTERS = {
    "r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7",
    "r8", "r9", "r10", "r11", "r12", "sp", "lr", "pc",
    "cpsr", "spsr"
}

-- Key MMIO registers to dump
local MMIO_REGISTERS = {
    -- LCD Control
    { addr = 0x04000000, name = "DISPCNT", size = 16 },
    { addr = 0x04000004, name = "DISPSTAT", size = 16 },
    { addr = 0x04000006, name = "VCOUNT", size = 16 },
    -- BG Control
    { addr = 0x04000008, name = "BG0CNT", size = 16 },
    { addr = 0x0400000A, name = "BG1CNT", size = 16 },
    { addr = 0x0400000C, name = "BG2CNT", size = 16 },
    { addr = 0x0400000E, name = "BG3CNT", size = 16 },
    -- BG Offset
    { addr = 0x04000010, name = "BG0HOFS", size = 16 },
    { addr = 0x04000012, name = "BG0VOFS", size = 16 },
    { addr = 0x04000014, name = "BG1HOFS", size = 16 },
    { addr = 0x04000016, name = "BG1VOFS", size = 16 },
    { addr = 0x04000018, name = "BG2HOFS", size = 16 },
    { addr = 0x0400001A, name = "BG2VOFS", size = 16 },
    { addr = 0x0400001C, name = "BG3HOFS", size = 16 },
    { addr = 0x0400001E, name = "BG3VOFS", size = 16 },
    -- BG Rotation/Scaling
    { addr = 0x04000020, name = "BG2PA", size = 16 },
    { addr = 0x04000022, name = "BG2PB", size = 16 },
    { addr = 0x04000024, name = "BG2PC", size = 16 },
    { addr = 0x04000026, name = "BG2PD", size = 16 },
    { addr = 0x04000028, name = "BG2X", size = 32 },
    { addr = 0x0400002C, name = "BG2Y", size = 32 },
    { addr = 0x04000030, name = "BG3PA", size = 16 },
    { addr = 0x04000032, name = "BG3PB", size = 16 },
    { addr = 0x04000034, name = "BG3PC", size = 16 },
    { addr = 0x04000036, name = "BG3PD", size = 16 },
    { addr = 0x04000038, name = "BG3X", size = 32 },
    { addr = 0x0400003C, name = "BG3Y", size = 32 },
    -- Window
    { addr = 0x04000040, name = "WIN0H", size = 16 },
    { addr = 0x04000042, name = "WIN0V", size = 16 },
    { addr = 0x04000044, name = "WIN1H", size = 16 },
    { addr = 0x04000046, name = "WIN1V", size = 16 },
    { addr = 0x04000048, name = "WININ", size = 16 },
    { addr = 0x0400004A, name = "WINOUT", size = 16 },
    -- Blend
    { addr = 0x04000050, name = "BLDCNT", size = 16 },
    { addr = 0x04000052, name = "BLDALPHA", size = 16 },
    { addr = 0x04000054, name = "BLDY", size = 16 },
    -- Sound
    { addr = 0x04000060, name = "SOUND1CNT_L", size = 16 },
    { addr = 0x04000062, name = "SOUND1CNT_H", size = 16 },
    { addr = 0x04000064, name = "SOUND1CNT_X", size = 16 },
    { addr = 0x04000068, name = "SOUND2CNT_L", size = 16 },
    { addr = 0x0400006C, name = "SOUND2CNT_H", size = 16 },
    { addr = 0x04000070, name = "SOUND3CNT_L", size = 16 },
    { addr = 0x04000072, name = "SOUND3CNT_H", size = 16 },
    { addr = 0x04000074, name = "SOUND3CNT_X", size = 16 },
    { addr = 0x04000078, name = "SOUND4CNT_L", size = 16 },
    { addr = 0x0400007C, name = "SOUND4CNT_H", size = 16 },
    { addr = 0x04000080, name = "SOUNDCNT_L", size = 16 },
    { addr = 0x04000082, name = "SOUNDCNT_H", size = 16 },
    { addr = 0x04000084, name = "SOUNDCNT_X", size = 16 },
    -- DMA
    { addr = 0x040000B0, name = "DMA0CNT", size = 16 },
    { addr = 0x040000B4, name = "DMA1CNT", size = 16 },
    { addr = 0x040000B8, name = "DMA2CNT", size = 16 },
    { addr = 0x040000BC, name = "DMA3CNT", size = 16 },
    -- Timers
    { addr = 0x04000100, name = "TM0CNT", size = 16 },
    { addr = 0x04000104, name = "TM1CNT", size = 16 },
    { addr = 0x04000108, name = "TM2CNT", size = 16 },
    { addr = 0x0400010C, name = "TM3CNT", size = 16 },
    -- Keypad
    { addr = 0x04000130, name = "KEYINPUT", size = 16 },
    { addr = 0x04000132, name = "KEYCNT", size = 16 },
    -- Interrupt
    { addr = 0x04000200, name = "IE", size = 16 },
    { addr = 0x04000202, name = "IF", size = 16 },
    { addr = 0x04000204, name = "WAITCNT", size = 16 },
    { addr = 0x04000208, name = "IME", size = 16 },
    -- PostBoot flag
    { addr = 0x04000204, name = "POSTBOOT", size = 8 },
}

-- Helper: escape string for JSON
local function jsonEscape(s)
    return (s:gsub("\\", "\\\\"):gsub("\"", "\\\""):gsub("\n", "\\n"):gsub("\r", "\\r"):gsub("\t", "\\t"))
end

-- Dump CPU registers
local function dumpCPURegisters()
    local regs = {}
    for _, name in ipairs(CPU_REGISTERS) do
        local val = emu.cpu:readRegister(name)
        regs[name] = string.format("0x%08X", val)
    end
    return regs
end

-- Dump MMIO registers
local function dumpMMIO()
    local mmio = {}
    for _, reg in ipairs(MMIO_REGISTERS) do
        local val
        if reg.size == 32 then
            val = emu.memory.main:read32(reg.addr)
        elseif reg.size == 16 then
            val = emu.memory.main:read16(reg.addr)
        else
            val = emu.memory.main:read8(reg.addr)
        end
        mmio[reg.name] = string.format("0x%X", val)
    end
    return mmio
end

-- Dump palette RAM
local function dumpPalette()
    local palette = {}
    for i = 0, 255 do
        local val = emu.memory.palette:read16(i * 2)
        palette[i] = string.format("0x%04X", val)
    end
    return palette
end

-- Main callback
callbacks:add("frame", function()
    local currentFrame = emu:currentFrame()
    
    if currentFrame >= FRAMES_TO_RUN then
        print("Dumping state at frame " .. currentFrame)
        
        -- Build JSON manually (avoid external deps)
        local json = "{\n"
        
        -- Timestamp
        json = json .. '  "frame": ' .. currentFrame .. ",\n"
        json = json .. '  "timestamp": "' .. os.date("%Y-%m-%dT%H:%M:%S") .. '",\n'
        
        -- CPU Registers
        json = json .. '  "cpu_registers": {\n'
        local regs = dumpCPURegisters()
        local regList = {}
        for name, val in pairs(regs) do
            table.insert(regList, '    "' .. name .. '": ' .. val)
        end
        json = json .. table.concat(regList, ",\n") .. "\n"
        json = json .. "  },\n"
        
        -- MMIO Registers
        json = json .. '  "mmio": {\n'
        local mmio = dumpMMIO()
        local mmioList = {}
        for name, val in pairs(mmio) do
            table.insert(mmioList, '    "' .. jsonEscape(name) .. '": ' .. val)
        end
        json = json .. table.concat(mmioList, ",\n") .. "\n"
        json = json .. "  },\n"
        
        -- Palette sample (first 16 entries)
        json = json .. '  "palette_sample": {\n'
        local palette = dumpPalette()
        local palList = {}
        for i = 0, 15 do
            table.insert(palList, '    "' .. i .. '": ' .. palette[i])
        end
        json = json .. table.concat(palList, ",\n") .. "\n"
        json = json .. "  }\n"
        
        json = json .. "}\n"
        
        -- Write to file
        local out = io.open(OUTPUT_FILE, "w")
        if out then
            out:write(json)
            out:close()
            print("State dumped to " .. OUTPUT_FILE)
        else
            print("Failed to open " .. OUTPUT_FILE .. " for writing")
        end
        
        -- Also dump memory regions to separate files for detailed comparison
        -- VRAM (first 1KB sample)
        local vramSample = io.open("vram_sample.bin", "wb")
        if vramSample then
            for i = 0, 1023 do
                vramSample:write(string.char(emu.memory.vram:read8(i)))
            end
            vramSample:close()
            print("Dumped VRAM sample")
        end
        
        -- OAM (all 1KB)
        local oamDump = io.open("oam_dump.bin", "wb")
        if oamDump then
            for i = 0, 255 do
                local val = emu.memory.oam:read32(i * 4)
                oamDump:write(string.char(val & 0xFF))
                oamDump:write(string.char((val >> 8) & 0xFF))
                oamDump:write(string.char((val >> 16) & 0xFF))
                oamDump:write(string.char((val >> 24) & 0xFF))
            end
            oamDump:close()
            print("Dumped OAM")
        end
        
        -- Halt execution
        emu.pause()
    end
end)

print("dump_state.lua loaded - will dump state after " .. FRAMES_TO_RUN .. " frames")