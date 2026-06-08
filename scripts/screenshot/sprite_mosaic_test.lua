# Capture screenshot at frame 30 for sprite-hmosaic test
callbacks:add("frame", function()
    local current = emu:currentFrame()
    if current >= 30 then
        emu:screenshot("/tmp/sprite_hmosaic_golden.png")
        print("Captured sprite_hmosaic screenshot at frame 30")
        os.exit(0)
    end
end)
print("Script started")
