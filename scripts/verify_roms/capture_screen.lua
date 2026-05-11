local FRAMES_TO_RUN = 60

local function getPalette()
    local data = {}
    for i = 0, 255 do
        local val = emu.memory.palette:read16(i * 2)
        data[i] = val
    end
    return data
end

local function getVRAM()
    local data = {}
    for i = 0, 38399 do
        data[i] = emu.memory.vram:read8(i)
    end
    return data
end

local function getOAM()
    local data = {}
    for i = 0, 255 do
        local val = emu.memory.oam:read32(i * 4)
        data[i] = val
    end
    return data
end

callbacks:add("frame", function()
    local currentFrame = emu:currentFrame()
    
    if currentFrame >= FRAMES_TO_RUN then
        local palette = getPalette()
        local vram = getVRAM()
        local oam = getOAM()
        
        local out = io.open("vram_dump.bin", "wb")
        for i = 1, #vram do
            out:write(string.char(vram[i]))
        end
        out:close()
        
        local out = io.open("palette_dump.bin", "wb")
        for i = 0, 255 do
            local val = palette[i]
            local r = (val & 0x1F) * 8
            local g = ((val >> 5) & 0x1F) * 8
            local b = ((val >> 10) & 0x1F) * 8
            out:write(string.char(r, g, b))
        end
        out:close()
        
        print("Dumped VRAM and palette")
    end
end)