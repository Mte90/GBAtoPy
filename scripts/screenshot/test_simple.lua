print("SCRIPT STARTED")

callbacks:add("frame", function()
    local current = emu:currentFrame()
    print("Frame: " .. current)
    if current >= 10 then
        emu:screenshot("/tmp/test.png")
        print("SCREENSHOT SAVED")
        os.exit(0)
    end
end)
