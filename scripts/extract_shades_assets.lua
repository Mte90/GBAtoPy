-- Extract VRAM and Palette from shades.gba for GBAtoPy
-- Try different mGBA memory access APIs
local target_frame = 60

-- Test which API is available
local function read8(addr)
    if memory and memory.read8 then
        return memory.read8(addr)
    elseif core and core.peek8 then
        return core:peek8(addr)
    elseif emu and emu.read8 then
        return emu:read8(addr)
    else
        return 0
    end
end

local function read16(addr)
    if memory and memory.read16 then
        return memory.read16(addr)
    elseif core and core.peek16 then
        return core:peek16(addr)
    elseif emu and emu.read16 then
        return emu:read16(addr)
    else
        return 0
    end
end

callbacks:add("frame", function()
    local current = emu:currentFrame()
    
    if current == target_frame then
        print("Extracting VRAM and Palette...")
        
        -- Open output files
        local vram_file = io.open("/home/archimede/Desktop/projects/GBAtoPy/test_roms/assets/shades_vram.bin", "wb")
        local pal_file = io.open("/home/archimede/Desktop/projects/GBAtoPy/test_roms/assets/shades_palette.bin", "wb")
        
        if not vram_file or not pal_file then
            print("Error: Could not open output files")
            return
        end
        
        -- Extract VRAM (96KB: 0x06000000 - 0x06017FFF)
        for addr = 0x06000000, 0x06017FFF do
            local val = read8(addr)
            vram_file:write(string.char(val))
        end
        vram_file:close()
        print("VRAM extracted (98304 bytes)")
        
        -- Extract Palette (first 32 bytes only for testing)
        for addr = 0x05000000, 0x0500001F do
            local val = read8(addr)
            pal_file:write(string.char(val))
        end
        pal_file:close()
        print("Palette extracted (512 bytes)")
        
        print("Asset extraction complete!")
        os.exit(0)
    end
end)

print("Starting shades.gba, will extract at frame " .. target_frame)
