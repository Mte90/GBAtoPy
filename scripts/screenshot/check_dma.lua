-- Check DMA0 and BG2 affine state at specific frames in bgpd
local frame_count = 0
local check_frames = {1, 5, 10, 30, 60, 100, 200}
local check_set = {}
for _, f in ipairs(check_frames) do check_set[f] = true end

callbacks:add("frame", function()
    frame_count = frame_count + 1
    if check_set[frame_count] then
        local dma0_ctrl = emu:read16(0x040000BA)
        local dma0_cnt = emu:read16(0x040000B8)
        local dma0_src = emu:read32(0x040000B0)
        local dma0_dst = emu:read32(0x040000B4)
        local bg2pa = emu:read16(0x04000020)
        local bg2pb = emu:read16(0x04000022)
        local bg2pc = emu:read16(0x04000024)
        local bg2pd = emu:read16(0x04000026)
        local bg2x = emu:read32(0x04000028)
        local bg2y = emu:read32(0x0400002C)
        local dispcnt = emu:read16(0x04000000)
        local dispcnt_raw = emu:read16(0x04000004)

        print(string.format("=== Frame %d ===", frame_count))
        print(string.format("  DISPCNT:  0x%04X (mode=%d, bg2=%d, force_blank=%d)", dispcnt, dispcnt & 0x7, (dispcnt >> 10) & 1, (dispcnt >> 7) & 1))
        print(string.format("  DMA0:     ctrl=0x%04X enabled=%d cnt=%d src=0x%08X dst=0x%08X",
            dma0_ctrl, (dma0_ctrl >> 15) & 1, dma0_cnt, dma0_src, dma0_dst))
        print(string.format("  BG2 affine: PA=0x%04X PB=0x%04X PC=0x%04X PD=0x%04X", bg2pa, bg2pb, bg2pc, bg2pd))
        print(string.format("  BG2 ref:    X=0x%08X Y=0x%08X", bg2x, bg2y))
    end
    if frame_count >= 200 then
        emu:quit()
    end
end)

print("DMA check script loaded")
