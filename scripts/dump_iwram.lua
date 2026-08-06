-- Dump IWRAM at frame 8 (when fill is happening)
local frame = 0

callbacks:add("frame", function()
    frame = frame + 1
    if frame == 8 then
        print("=== IWRAM dump at frame 8 ===")
        -- Dump 0x03000300-0x03000320 (the BL area)
        for addr = 0x03000300, 0x03000320, 2 do
            local val = emu:read16(addr)
            print(string.format("0x%08X: 0x%04X", addr, val))
        end
        -- Also dump 0x03000020-0x03000040 (the fill code area)
        print("=== Fill code area ===")
        for addr = 0x03000020, 0x03000040, 2 do
            local val = emu:read16(addr)
            print(string.format("0x%08X: 0x%04X", addr, val))
        end
        emu:stop()
    end
end)

print("Frame callback registered, running...")
