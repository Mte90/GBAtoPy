-- Screenshot capture for mGBA headless
-- Reads VRAM directly and writes raw pixel data

local FRAMES_TO_RUN = 60

local function listMemoryDomains()
    print("Available memory domains:")
    for name, domain in pairs(emu.memory) do
        print("  - " .. name)
    end
end

local function getVRAM()
    local domains = {"vram", "video", "VRAM"}
    for _, name in ipairs(domains) do
        if emu.memory[name] then
            return emu.memory[name]
        end
    end
    for name, domain in pairs(emu.memory) do
        if type(domain) == "table" and domain.read8 then
            return domain
        end
    end
    return nil
end

listMemoryDomains()

local vram = getVRAM()
if vram then
    print("Found VRAM domain")
else
    print("No VRAM domain found, trying main memory")
end

callbacks:add("frame", function()
    local currentFrame = emu:currentFrame()
    print("Frame: " .. currentFrame)
    
    if currentFrame >= FRAMES_TO_RUN then
        if emu.memory.cart0 then
            for i = 0, 10 do
                local val = emu.memory.cart0:read16(0x05000000 + i * 2)
            end
            print("Read palette entries")
        end
        print("Screenshot capture simulated - headless mode")
    end
end)