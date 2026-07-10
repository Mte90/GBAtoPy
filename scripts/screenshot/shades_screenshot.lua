local name = "test_roms/roms/shades_mgba"
local target_frame = 60

callbacks:add("frame", function()
    local current = emu:currentFrame()
    
    if current >= target_frame then
        emu:screenshot(name .. ".png")
        print("Screenshot captured at frame " .. current)
        os.exit(0)
    end
end)

print("Starting mGBA, will capture frame " .. target_frame)
