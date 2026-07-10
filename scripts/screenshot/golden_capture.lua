-- Generic mGBA screenshot capture script.
-- Reads configuration from environment variables:
--   GBATOPY_SCREENSHOT_PATH  - output PNG path (without extension)
--   GBATOPY_TARGET_FRAME     - frame number to capture (default: 60)

local name = os.getenv("GBATOPY_SCREENSHOT_PATH") or "/tmp/golden"
local target_frame_str = os.getenv("GBATOPY_TARGET_FRAME") or "60"
local target_frame = tonumber(target_frame_str)

callbacks:add("frame", function()
    local current = emu:currentFrame()

    if current >= target_frame then
        emu:screenshot(name .. ".png")
        print("Screenshot captured at frame " .. current .. " -> " .. name .. ".png")
        os.exit(0)
    end
end)

print("Starting mGBA screenshot capture, target frame " .. target_frame)
