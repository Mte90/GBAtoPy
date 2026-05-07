local config = {
    screenshot_frame = 10,
    output_path = "/tmp/mgba_screenshot.png",
}

emu.registerframe(function()
    if emu.frameCount == config.screenshot_frame then
        local success, err = pcall(function()
            emu:screenshot(config.output_path)
        end)

        if success then
            console:log("Screenshot captured at frame 10: " .. config.output_path)
        else
            console:warn("Failed to capture screenshot: " .. tostring(err))
        end

        emu.exit()
    end
end)
console:log("Screenshot script started, waiting for frame " .. config.screenshot_frame)