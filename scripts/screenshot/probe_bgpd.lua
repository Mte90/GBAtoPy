-- Probe BG2PD register at each scanline to detect DMA writes
-- Uses mGBA callback API

local frame_count = 0
local target_frame = 200
local logged = false

-- mGBA Lua callback for frame
emu:register(emu.EVENT_FRAME, function()
    frame_count = frame_count + 1
    if frame_count == target_frame and not logged then
        logged = true
        local f = io.open("/tmp/bgpd_pd_probe.txt", "w")
        if f then
            -- Read BG2PD (0x04000026) and DMA0 control (0x040000BA)
            local pd = emu:read16(0x04000026)
            local dma_ctrl = emu:read16(0x040000BA)
            local dma_src = emu:read32(0x040000B0)
            local dma_dst = emu:read32(0x040000B4)
            local dma_cnt = emu:read16(0x040000B8)
            f:write(string.format("Frame %d:\n", frame_count))
            f:write(string.format("BG2PD = 0x%04X (%d)\n", pd, pd))
            f:write(string.format("DMA0: src=0x%08X dst=0x%08X count=%d ctrl=0x%04X\n", dma_src, dma_dst, dma_cnt, dma_ctrl))
            
            -- Read BG2PA, PB, PC, PD, X, Y
            local pa = emu:read16(0x04000020)
            local pb = emu:read16(0x04000022)
            local pc = emu:read16(0x04000024)
            local x_lo = emu:read16(0x04000028)
            local x_hi = emu:read16(0x0400002A)
            local y_lo = emu:read16(0x0400002C)
            local y_hi = emu:read16(0x0400002E)
            f:write(string.format("BG2: PA=0x%04X PB=0x%04X PC=0x%04X PD=0x%04X\n", pa, pb, pc, pd))
            f:write(string.format("BG2: X=0x%04X%04X Y=0x%04X%04X\n", x_hi, x_lo, y_hi, y_lo))
            
            -- Read DISPCNT
            local dispcnt = emu:read16(0x04000000)
            f:write(string.format("DISPCNT = 0x%04X\n", dispcnt))
            
            -- Dump DMA source buffer (first 20 values)
            f:write("\nDMA source buffer (first 20 halfwords):\n")
            for i = 0, 19 do
                local val = emu:read16(dma_src + i * 2)
                f:write(string.format("  [%d] = 0x%04X (%d)\n", i, val, val))
            end
            
            f:close()
            print("Probe data written to /tmp/bgpd_pd_probe.txt")
        end
        -- Stop after logging
        emu:stop()
    end
end)

print("Probe script loaded, will log at frame " .. target_frame)
