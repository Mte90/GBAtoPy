local targetFrame = 60

callbacks:add("frame", function()
    emu.frameWait()
    if core:currentFrame() >= targetFrame then
        emu.print("Frame " .. targetFrame .. " reached")
    end
end)