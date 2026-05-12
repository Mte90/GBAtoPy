local targetFrames = {1, 10, 20, 30}
local name = "/tmp/stripes_golden"
local frameIdx = 1

local function onFrame()
    local current = emu:currentFrame()
    if frameIdx > #targetFrames then
        os.exit(0)
    end
    if current >= targetFrames[frameIdx] then
        emu:screenshot(name .. "_frame_" .. targetFrames[frameIdx] .. ".png")
        print("Captured frame " .. targetFrames[frameIdx])
        frameIdx = frameIdx + 1
        if frameIdx > #targetFrames then
            os.exit(0)
        end
    end
end

callbacks:add("frame", onFrame)
print("Screenshot script started")
