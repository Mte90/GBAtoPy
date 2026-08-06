-- Check tilemap state at early frames and log PC
local frame = 0
local seen_pcs = {}

callbacks:add("frame", function()
    frame = frame + 1
    if frame <= 5 or frame == 10 or frame == 20 then
        local pc = emu:readRegister("r15")
        local sp = emu:readRegister("r13")
        print(string.format("Frame %d: PC=0x%08X SP=0x%08X", frame, pc, sp))
        -- Count non-zero tilemap entries at 0x06002000
        local nonzero = 0
        for i = 0, 1023 do
            local val = emu:read16(0x06002000 + i * 2)
            if val ~= 0 then nonzero = nonzero + 1 end
        end
        print(string.format("  Tilemap non-zero entries: %d/1024", nonzero))
    end
    if frame == 20 then
        emu:stop()
    end
end)

print("Frame callback registered, running...")
