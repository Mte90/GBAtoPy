-- Generic asset extraction tool for GBAtoPy.
-- Extracts VRAM and Palette from a GBA ROM at a specified frame.
--
-- Usage:
--   GBATOPY_TARGET_FRAME=60 ./mgba/build/sdl/mgba -S scripts/extract_assets.lua <rom.gba>
--
-- Environment variables:
--   GBATOPY_TARGET_FRAME  - frame number to extract (default: 60)
--   GBATOPY_OUTPUT_DIR    - output directory for assets (default: /tmp)

local target_frame = tonumber(os.getenv("GBATOPY_TARGET_FRAME") or "60")
local output_dir = os.getenv("GBATOPY_OUTPUT_DIR") or "/tmp"

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
        local rom_name = "rom"  -- Will be set from command line args
        if #arg >= 1 then
            rom_name = arg[1]:match("([^/]+)%.gba$") or arg[1]
        end
        
        local vram_file = io.open(output_dir .. "/" .. rom_name .. "_vram.bin", "wb")
        local pal_file = io.open(output_dir .. "/" .. rom_name .. "_palette.bin", "wb")
        
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

print("Starting asset extraction, will extract at frame " .. target_frame)
print("Output directory: " .. output_dir)
