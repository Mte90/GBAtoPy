local name = "/tmp/stripes_golden"
local target_frame = 60

callbacks:add("frame", function()
    local current = emu:currentFrame()
    
    if current >= target_frame then
        emu:screenshot(name .. ".png")
        print("Golden screenshot captured at frame " .. current)
        os.exit(0)
    end
end)

print("Starting mGBA, will capture frame " .. target_frame)
