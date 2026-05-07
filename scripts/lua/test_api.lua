-- Test script to verify mGBA extended Lua API availability
-- Run: mgba --lua scripts/lua/test_api.lua test_roms/.../arm.gba

local tests_passed = 0
local tests_failed = 0

function test(name, fn)
    local ok, err = pcall(fn)
    if ok then
        print("PASS: " .. name)
        tests_passed = tests_passed + 1
    else
        print("FAIL: " .. name .. " - " .. tostring(err))
        tests_failed = tests_failed + 1
    end
end

print("=== mGBA Extended Lua API Test ===")

-- Test emu.getregister
test("emu.getregister exists", function()
    assert(emu.getregister ~= nil)
    local r0 = emu.getregister(0)
    print("  r0 = " .. string.format("0x%08X", r0))
end)

-- Test emu.setregister
test("emu.setregister exists", function()
    assert(emu.setregister ~= nil)
    emu.setregister(0, 42)
end)

-- Test memory.read
test("memory.read exists", function()
    assert(memory.read ~= nil)
end)

-- Test memory.register
test("memory.register exists", function()
    assert(memory.register ~= nil)
end)

-- Test emu.registerbefore
test("emu.registerbefore exists", function()
    assert(emu.registerbefore ~= nil)
end)

-- Test emu.registerafter
test("emu.registerafter exists", function()
    assert(emu.registerafter ~= nil)
end)

-- Test emu.registerexit
test("emu.registerexit exists", function()
    assert(emu.registerexit ~= nil)
end)

print("")
print("=== Results ===")
print("Passed: " .. tests_passed)
print("Failed: " .. tests_failed)

if tests_failed > 0 then
    os.exit(1)
end