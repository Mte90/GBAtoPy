# Capture screenshot at frame 30 for window_midframe test
callbacks:add("frame", function()
    local current = emu:currentFrame()
    if current >= 30 then
        emu:screenshot("/tmp/window_midframe_golden.png")
        print("Captured window_midframe screenshot at frame 30")
        os.exit(0)
    end
end)
print("Script started")
