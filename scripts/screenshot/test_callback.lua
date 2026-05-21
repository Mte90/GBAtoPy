callbacks:add("frame", function()
    local current = emu:currentFrame()
    console.log("Frame " .. current)
    if current >= 10 then
        emu:screenshot("/tmp/frame_" .. current .. ".png")
    end
end)
print("Script ready")
