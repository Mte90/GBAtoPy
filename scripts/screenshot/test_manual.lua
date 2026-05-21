print("Script started")
print("Current frame: " .. emu:currentFrame())

callbacks:add("frame", function()
    local current = emu:currentFrame()
    print("Frame " .. current .. " - screenshotting now")
    emu:screenshot("/tmp/test.png")
    print("Screenshot saved")
end)

print("Waiting for manual stop...")
for i = 1, 1000 do
    emu:runFrame()
    if emu:currentFrame() >= 60 then
        break
    end
end
print("Done")
