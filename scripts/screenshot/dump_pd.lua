callbacks:add("frame", function()
    local current = emu:currentFrame()
    if current >= 60 then
        -- Read VRAM (should have gradient 0x1084 at row 0)
        local vram0 = emu:read16(0x06000000)
        local vram8 = emu:read16(0x06000000 + 8 * 240 * 2)
        -- Read DISPCNT
        local dispcnt = emu:read16(0x04000000)
        -- Read BG2PD
        local pd = emu:read16(0x04000026)
        -- Read as 32-bit
        local pd32 = emu:read32(0x04000026)
        print(string.format("VRAM0=0x%04x VRAM8=0x%04x DISPCNT=0x%04x PD16=0x%04x PD32=0x%08x", vram0, vram8, dispcnt, pd, pd32))
        os.exit(0)
    end
end)
print("PD probe started")
