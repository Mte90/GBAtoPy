-- Find where tilemap fill happens in mGBA
local write_count = 0

emu:registerMemoryWrite(0x06002000, function(addr, value)
    local pc = emu:readRegister("r15")
    write_count = write_count + 1
    if write_count <= 5 then
        print(string.format("WRITE 0x%08X val=0x%04X PC=0x%08X count=%d", addr, value, pc, write_count))
    end
    if write_count == 1 or write_count == 2 or write_count == 100 or write_count == 1000 then
        local r0 = emu:readRegister("r0")
        local r1 = emu:readRegister("r1")
        local r2 = emu:readRegister("r2")
        local r3 = emu:readRegister("r3")
        local lr = emu:readRegister("r14")
        print(string.format("  R0=0x%08X R1=0x%08X R2=0x%08X R3=0x%08X LR=0x%08X", r0, r1, r2, r3, lr))
    end
    if write_count >= 1100 then
        print("Stopping - got 1100 writes")
        emu:stop()
    end
end)

print("Breakpoint set on 0x06002000, running...")
