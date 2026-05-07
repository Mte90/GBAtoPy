-- Oracle trace Lua script for mGBA
-- Collects execution traces including registers, memory access, and branches

local config = {
    max_instructions = 10000,
    timeout = 30,
    trace_memory = true,
    trace_branches = true,
}

local trace = {
    entries = {},
    metadata = {
        timestamp = os.date("!%Y-%m-%dT%H:%M:%SZ"),
        mgba_version = nil,
        mode = "Runtime",
        instruction_count = 0,
        duration_ms = 0,
    }
}

local start_time = os.time()

-- Callback before each instruction
emu.registerbefore(function()
    if trace.metadata.instruction_count >= config.max_instructions then
        emu.exit()
        return
    end
    
    local elapsed = os.time() - start_time
    if elapsed >= config.timeout then
        trace.metadata.duration_ms = elapsed * 1000
        emu.exit()
        return
    end
    
    trace.metadata.instruction_count = trace.metadata.instruction_count + 1
    
    local entry = {
        address = emu.getregister(15),
        registers = {},
        cpsr = 0,
        mode = "Arm",
        memory_accesses = {},
        branch_taken = nil,
        frame_number = 0,
        cycle_count = trace.metadata.instruction_count,
    }
    
    for i = 0, 15 do
        entry.registers[i] = emu.getregister(i)
    end
    
    table.insert(trace.entries, entry)
end)

-- Output trace as JSON at exit
emu.registerexit(function()
    local json = require("cjson")
    print(json.encode(trace))
end)