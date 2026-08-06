-- Check tilemap state at every frame 6-10
local frame = 0

callbacks:add("frame", function()
    frame = frame + 1
    if frame >= 6 and frame <= 12 then
        local pc = emu:readRegister("r15")
        local sp = emu:readRegister("r13")
        local lr = emu:readRegister("r14")
        local nonzero = 0
        for i = 0, 1023 do
            local val = emu:read16(0x06002000 + i * 2)
            if val ~= 0 then nonzero = nonzero + 1 end
        end
        -- Also check first few entries to see fill value
        local v0 = emu:read16(0x06002000)
        local v1 = emu:read16(0x06002002)
        local v2 = emu:read16(0x06002004)
        print(string.format("Frame %d: PC=0x%08X SP=0x%08X LR=0x%08X tilemap=%d/1024 [0]=0x%04X [1]=0x%04X [2]=0x%04X", 
              frame, pc, sp, lr, nonzero, v0, v1, v2))
    end
    if frame == 12 then
        emu:stop()
    end
end)

print("Frame callback registered, running...")
