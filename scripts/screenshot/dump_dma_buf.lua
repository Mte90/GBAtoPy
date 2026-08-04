-- Dump DMA0 source buffer and BG2PD at frame 30 (DMA should be active)
callbacks:add("frame", function()
    local current = emu:currentFrame()
    if current >= 30 then
        local dma0_src = emu:read32(0x040000B0)
        local dma0_dst = emu:read32(0x040000B4)
        local dma0_count = emu:read16(0x040000B8)
        local dma0_cnt = emu:read16(0x040000BA)
        local pd = emu:read16(0x04000026)
        local pa = emu:read16(0x04000020)
        print(string.format("Frame %d: DMA0 src=0x%08X dst=0x%08X count=%d cnt=0x%04X PA=%d PD=%d", current, dma0_src, dma0_dst, dma0_count, dma0_cnt, pa, pd))

        -- Dump first 32 entries of DMA source buffer
        if dma0_src >= 0x02000000 and dma0_src < 0x08000000 then
            print("DMA_BUFFER_START")
            for i = 0, 31 do
                local addr = dma0_src + i * 2
                local val = emu:read16(addr)
                print(string.format("%d %d", i, val))
            end
            print("DMA_BUFFER_END")
        end

        -- Also dump BG2 X/Y (32-bit)
        local bg2x = emu:read32(0x04000028)
        local bg2y = emu:read32(0x0400002C)
        print(string.format("BG2X=%d BG2Y=%d", bg2x, bg2y))

        os.exit(0)
    end
end)
print("DMA buffer probe started, waiting for frame 30")
