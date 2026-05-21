local name = "/tmp/mode3_golden.png"

callbacks:add("frame", function()
    local current = emu:currentFrame()
    
    if current >= 30 then
        emu:screenshot(name)
        print("Captured screenshot at frame " .. current)
        os.exit(0)
    end
    
    if current >= 60 then
        os.exit(0)
    end
end)

print("Script started")
