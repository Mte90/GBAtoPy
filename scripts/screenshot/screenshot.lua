-- Generic mGBA screenshot capture script.
-- Usage:
--   GBATOPY_SCREENSHOT_PATH=/tmp/out GBATOPY_TARGET_FRAME=60 \
--     ./mgba/build/sdl/mgba -S scripts/screenshot/screenshot.lua <rom.gba>
--
-- Environment variables:
--   GBATOPY_SCREENSHOT_PATH  - output PNG path without extension (default: /tmp/golden)
--   GBATOPY_TARGET_FRAME     - frame number to capture (default: 60)

local name = os.getenv("GBATOPY_SCREENSHOT_PATH") or "/tmp/golden"
local target_frame = tonumber(os.getenv("GBATOPY_TARGET_FRAME") or "60")

callbacks:add("frame", function()
    local current = emu:currentFrame()
    if current >= target_frame then
        emu:screenshot(name .. ".png")
        print("Screenshot captured at frame " .. current .. " -> " .. name .. ".png")
        os.exit(0)
    end
end)

print("Starting mGBA screenshot capture, target frame " .. target_frame)
