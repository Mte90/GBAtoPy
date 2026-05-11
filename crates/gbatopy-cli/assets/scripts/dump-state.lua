-- mGBA Lua script for dumping CPU state to JSON
-- Used for verification comparison with GBAtoPy output

local dump_dir = arg[1] or "."
local frame = arg[2] or 0

-- Helper function to write JSON
local function write_json(key, value)
    io.stdout(string.format('"%s": %s,', key, json.encode(value)))
end

-- Dump CPU registers
print("{")
print('  "timestamp": ' .. tostring(frame) .. ",")

-- R0-R15 registers
for i = 0, 15 do
    write_json(string.format("R%d", i), cpu.registers[i])
end

-- CPSR flags
write_json("cpsr", cpu.cpsr)

-- SPSR (saved program status register)
write_json("spsr", cpu.spsr)

print("}")
print("]")
