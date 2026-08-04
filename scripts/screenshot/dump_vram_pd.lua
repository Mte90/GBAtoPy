-- Dump VRAM content (pixel at column 120 for each of 160 rows) and BG2 affine regs at frame 60
callbacks:add("frame", function()
    local current = emu:currentFrame()
    if current >= 60 then
        local pa = emu:read16(0x04000020)
        local pb = emu:read16(0x04000022)
        local pc = emu:read16(0x04000024)
        local pd = emu:read16(0x04000026)
        local bg2x = emu:read32(0x04000028)
        local bg2y = emu:read32(0x0400002C)
        local dispcnt = emu:read16(0x04000000)
        print(string.format("DISPCNT=0x%04X PA=%d PB=%d PC=%d PD=%d X=%d Y=%d", dispcnt, pa, pb, pc, pd, bg2x, bg2y))

        local dma0_src = emu:read32(0x040000B0)
        local dma0_dst = emu:read32(0x040000B4)
        local dma0_count = emu:read16(0x040000B8)
        local dma0_cnt = emu:read16(0x040000BA)
        print(string.format("DMA0: src=0x%08X dst=0x%08X count=%d cnt=0x%04X", dma0_src, dma0_dst, dma0_count, dma0_cnt))

        print("VRAM_DUMP_START")
        for row = 0, 159 do
            local addr = 0x06000000 + row * 240 * 2 + 120 * 2
            local val = emu:read16(addr)
            local r5 = val & 0x1F
            local g5 = (val >> 5) & 0x1F
            local b5 = (val >> 10) & 0x1F
            print(string.format("%d %d %d %d", row, r5, g5, b5))
        end
        print("VRAM_DUMP_END")

        print("DMA_BUFFER_START")
        for i = 0, 159 do
            local addr = dma0_src + i * 2
            local val = emu:read16(addr)
            print(string.format("%d %d", i, val))
        end
        print("DMA_BUFFER_END")

        os.exit(0)
    end
end)
print("VRAM dump script started, waiting for frame 60")
