-- GBAtoPy memory reading script for custom mGBA fork
-- Waits for frame 3, then reads and prints memory contents

print("Starting GBAtoPy memory reader script")

callbacks:add("frame", function()
    local current = emu:currentFrame()
    
    if current >= 3 then
        print("Reached frame " .. current .. " - reading memory...")
        
        -- Method 1: Use memory domains for direct access (recommended)
        -- emu.memory.IWRAM and emu.memory.VRAM are MemoryDomain objects
        print("\n=== Method 1: Memory Domain Access ===")
        
        -- Read and print 32 bytes from IWRAM (0x03000000)
        print("\nIWRAM domain (Domain base: 0x03000000, IWRAM:base()=0x"..string.format("%X", emu.memory.IWRAM:base()).."):")
        local iwram_domain_data = emu.memory.IWRAM:readRange(0x0, 32)  -- Read 32 bytes from start of domain
        for i = 1, 32 do
            io.write(string.format("%02X ", string.byte(iwram_domain_data, i)))
            if i % 16 == 0 then io.write("\n") end
        end
        
        -- Read and print 32 bytes from VRAM (0x06000000)
        print("\nVRAM domain (Domain base: 0x06000000, VRAM:base()=0x"..string.format("%X", emu.memory.VRAM:base()).."):")
        local vram_domain_data = emu.memory.VRAM:readRange(0x0, 32)  -- Read 32 bytes from start of domain
        for i = 1, 32 do
            io.write(string.format("%02X ", string.byte(vram_domain_data, i)))
            if i % 16 == 0 then io.write("\n") end
        end
        
        -- Method 2: Use emu:read32/read16/read8() for bus address access
        print("\n=== Method 2: Bus Address Access ===")
        
        -- DMA0 registers (MMIO bus addresses)
        print("\nDMA0 registers (bus addresses):")
        local dma0_sad = emu:read32(0x040000B0)  -- DMA0 Source Address
        local dma0_dad = emu:read16(0x040000B4)  -- DMA0 Destination Address (16-bit for DAD? No, it's 32-bit)
        local dma0_cnt = emu:read32(0x040000B8)  -- DMA0 Control
        print(string.format("DMA0_SAD (0x040000B0): 0x%08X", dma0_sad))
        print(string.format("DMA0_DAD (0x040000B4): 0x%08X", emu:read32(0x040000B4))
        print(string.format("DMA0_CNT (0x040000B8): 0x%08X", dma0_cnt))
        
        -- Method 3: Read memory ranges via bus address
        print("\n=== Method 3: Bus Address Range Read ===")
        print("\nVRAM at 0x06000000 via bus readRange:")
        local vram_bus_data = emu:readRange(0x06000000, 32)
        for i = 1, 32 do
            io.write(string.format("%02X ", string.byte(vram_bus_data, i)))
            if i % 16 == 0 then io.write("\n") end
        end
        
        print("\nMemory read complete. Exiting.")
        os.exit(0)
    end
end)

print("Memory reader script loaded. Waiting for frame 3...")