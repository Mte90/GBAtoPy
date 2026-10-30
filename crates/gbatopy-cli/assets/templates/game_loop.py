
import os
import time
import array

def calibrate_gba_timing(measure_cycles=100000):
    """Calibrate Python execution speed to match GBA 16.79 MHz."""
    loop_start = time.perf_counter()
    cal_cycles = 0
    cal_x = 0
    while cal_cycles < measure_cycles:
        cal_x = cal_x + 1
        cal_cycles += 1
    loop_end = time.perf_counter()
    elapsed = loop_end - loop_start
    cycles_per_second = cal_cycles / elapsed if elapsed > 0 else measure_cycles
    gba_hz = 16789800  # GBA clock speed (16.79 MHz)
    speed_ratio = cycles_per_second / gba_hz
    target_cycles_per_frame = gba_hz / 60.0
    calibrated_delay = 1.0 / cycles_per_second * target_cycles_per_frame
    return speed_ratio, calibrated_delay, cycles_per_second, gba_hz

def _save_file_path():
    return os.path.splitext(__file__)[0] + '.sav'

def _load_sram():
    try:
        with open(_save_file_path(), 'rb') as f:
            data = f.read()
        if data and len(data) <= len(memory.sram):
            memory.sram[:len(data)] = array.array('B', data)
    except (FileNotFoundError, OSError):
        pass

def _save_sram():
    if not any(memory.sram):
        return
    try:
        with open(_save_file_path(), 'wb') as f:
            f.write(memory.sram.tobytes())
    except OSError as e:
        print(f"Warning: Failed to save SRAM: {e}", file=sys.stderr)

_interp_cpu = None
_halt_reason = None  # None, "any" (Halt), or "vblank" (VBlankIntrWait)
_swi_lr = None  # Save LR_svc when SWI halts CPU
_swi_caller_pc = None  # Save PC (caller's return address) when SWI halts
_sound_work_area = None  # Sound driver work area pointer (SWI 0x19)
_sound_mode = 0  # Sound driver mode (SWI 0x1A)
_sound_vsync_enabled = True  # VSync sound processing enabled (SWI 0x1F)


def swi_handler(swi_field):
    """Handle BIOS SWI calls using the global registers/memory.
    ARM codegen extracts bits 23:16 of the 24-bit comment field (GBA BIOS
    convention, mGBA: immediate >> 16). Thumb codegen extracts bits 7:0.
    Handler receives the 8-bit SWI number directly."""
    global _cpu_halted, _halt_reason, _swi_lr, _swi_caller_pc
    swi_num = swi_field & 0xFF
    if swi_num == 0x00:  # SoftReset
        registers[0] = 0
        registers[13] = 0x03007F00
        registers[14] = 0x00000000
        registers[15] = 0x08000000
    elif swi_num == 0x01:  # RegisterRamReset
        flags = registers[0] & 0xFF
        memory.write_u16(0x04000000, 0x0080)
        if flags & 0x01:
            for addr in range(0x02000000, 0x02040000, 4):
                memory.write_u32(addr, 0)
        if flags & 0x02:
            for addr in range(0x03000000, 0x03008000 - 0x200, 4):
                memory.write_u32(addr, 0)
        if flags & 0x04:
            for addr in range(0x05000000, 0x05000400, 2):
                memory.write_u16(addr, 0)
        if flags & 0x08:
            for addr in range(0x06000000, 0x06018000, 2):
                memory.write_u16(addr, 0)
        if flags & 0x10:
            for addr in range(0x07000000, 0x07000400, 2):
                memory.write_u16(addr, 0)
        if flags & 0x20:
            memory.write_u16(0x04000128, 0)
            memory.write_u16(0x04000134, 0x8000)
            memory.write_u16(0x0400012A, 0)
            memory.write_u16(0x04000140, 0)
            memory.write_u32(0x04000150, 0)
            memory.write_u32(0x04000154, 0)
        if flags & 0x40:
            memory.write_u16(0x04000060, 0)
            memory.write_u16(0x04000062, 0)
            memory.write_u16(0x04000064, 0)
            memory.write_u16(0x04000068, 0)
            memory.write_u16(0x0400006C, 0)
            memory.write_u16(0x04000070, 0)
            memory.write_u16(0x04000072, 0)
            memory.write_u16(0x04000074, 0)
            memory.write_u16(0x04000078, 0)
            memory.write_u16(0x0400007C, 0)
            memory.write_u16(0x04000080, 0)
            memory.write_u16(0x04000082, 0)
            memory.write_u16(0x04000084, 0)
            memory.write_u16(0x04000088, 0x0200)
        if flags & 0x80:
            memory.write_u16(0x04000004, 0)
            memory.write_u16(0x04000006, 0)
            memory.write_u16(0x04000008, 0)
            memory.write_u16(0x0400000A, 0)
            memory.write_u16(0x0400000C, 0)
            memory.write_u16(0x0400000E, 0)
            memory.write_u16(0x04000010, 0)
            memory.write_u16(0x04000012, 0)
            memory.write_u16(0x04000014, 0)
            memory.write_u16(0x04000016, 0)
            memory.write_u16(0x04000018, 0)
            memory.write_u16(0x0400001A, 0)
            memory.write_u16(0x0400001C, 0)
            memory.write_u16(0x0400001E, 0)
            memory.write_u16(0x04000020, 0x0100)
            memory.write_u16(0x04000022, 0)
            memory.write_u16(0x04000024, 0)
            memory.write_u16(0x04000026, 0x0100)
            memory.write_u32(0x04000028, 0)
            memory.write_u32(0x0400002C, 0)
            memory.write_u16(0x04000030, 0x0100)
            memory.write_u16(0x04000032, 0)
            memory.write_u16(0x04000034, 0)
            memory.write_u16(0x04000036, 0x0100)
            memory.write_u32(0x04000038, 0)
            memory.write_u32(0x0400003C, 0)
            memory.write_u16(0x04000040, 0)
            memory.write_u16(0x04000042, 0)
            memory.write_u16(0x04000044, 0)
            memory.write_u16(0x04000046, 0)
            memory.write_u16(0x04000048, 0)
            memory.write_u16(0x0400004A, 0)
            memory.write_u16(0x0400004C, 0)
            memory.write_u16(0x04000050, 0)
            memory.write_u16(0x04000052, 0)
            memory.write_u16(0x04000054, 0)
            for base in [0x040000B0, 0x040000BC, 0x040000C8, 0x040000D4]:
                memory.write_u16(base + 0, 0)
                memory.write_u16(base + 2, 0)
                memory.write_u16(base + 4, 0)
                memory.write_u16(base + 6, 0)
                memory.write_u16(base + 8, 0)
                memory.write_u16(base + 10, 0)
            for base in [0x04000100, 0x04000104, 0x04000108, 0x0400010C]:
                memory.write_u16(base, 0)
                memory.write_u16(base + 2, 0)
            memory.write_u16(0x04000208, 0)
            memory.write_u16(0x04000202, 0xFFFF)
            memory.write_u16(0x04000204, 0)
            memory.write_u16(0x04000200, 0)
    elif swi_num == 0x02:  # Halt — wakes on ANY enabled IRQ
        _swi_lr = registers[14]
        _swi_caller_pc = (registers[15] + (2 if cpsr.get('t', 0) else 4)) & 0xFFFFFFFF
        _cpu_halted = True
        _halt_reason = "any"
        return
    elif swi_num == 0x03:  # Stop — low-power mode, treat as Halt
        _swi_lr = registers[14]
        _swi_caller_pc = (registers[15] + (2 if cpsr.get('t', 0) else 4)) & 0xFFFFFFFF
        _cpu_halted = True
        _halt_reason = "any"
        return
    elif swi_num == 0x04:  # IntrWait — check IF first, then halt
        _wait_flag = registers[0] & 0xFF
        _irq_obj = getattr(memory, '_interrupts', None)
        if _wait_flag & 0x01 and _irq_obj is not None:
            _flag_mask = registers[1] & 0xFFFF
            _pending = _irq_obj.if_reg & _flag_mask
            if _pending:
                _irq_obj.if_reg &= ~_pending
                registers[0] = 1
                cpsr['z'] = 1
                return
        _swi_lr = registers[14]
        _swi_caller_pc = (registers[15] + (2 if cpsr.get('t', 0) else 4)) & 0xFFFFFFFF
        _cpu_halted = True
        _halt_reason = "any"
        return
    elif swi_num == 0x05:  # VBlankIntrWait — wakes on VBlank IRQ ONLY
        _swi_lr = registers[14]  # Save LR_svc (SWI return address)
        _swi_caller_pc = (registers[15] + (2 if cpsr.get('t', 0) else 4)) & 0xFFFFFFFF
        # Per GBATEK: set IE.0 (VBlank enable), clear IF.0 (acknowledge pending VBlank)
        _irq_obj = getattr(memory, '_interrupts', None)
        if _irq_obj is not None:
            _irq_obj.ie_reg |= 0x0001
            _irq_obj.if_reg &= ~0x0001
        # Set DISPSTAT.3 (VBlank IRQ enable) so step_scanline fires vblank_irq()
        _dispstat = memory.read_u16(0x04000004)
        memory.write_u16(0x04000004, _dispstat | 0x0008)
        # Enable IME so the VBlank IRQ can actually wake the CPU
        memory.write_u16(0x04000208, 0x0001)
        _cpu_halted = True
        _halt_reason = "vblank"
        return
    elif swi_num == 0x06:  # Div (signed)
        dividend = registers[0]
        divisor = registers[1]
        if divisor != 0:
            # Interpret as signed 32-bit
            sd = dividend - 0x100000000 if dividend & 0x80000000 else dividend
            sv = divisor - 0x100000000 if divisor & 0x80000000 else divisor
            q = int(sd / sv) if sv != 0 else 0
            r = sd - q * sv
            registers[0] = q & 0xFFFFFFFF
            registers[1] = r & 0xFFFFFFFF
            registers[3] = abs(sd) & 0xFFFFFFFF
    elif swi_num == 0x07:  # DivArm (unsigned)
        dividend = registers[0] & 0xFFFFFFFF
        divisor = registers[1] & 0xFFFFFFFF
        if divisor != 0:
            registers[0] = (dividend // divisor) & 0xFFFFFFFF
            registers[1] = (dividend % divisor) & 0xFFFFFFFF
            registers[3] = dividend & 0xFFFFFFFF
    elif swi_num == 0x08:  # Sqrt
        val = registers[0] & 0xFFFFFFFF
        registers[0] = int(val ** 0.5) & 0xFFFFFFFF
    elif swi_num == 0x0B:  # CpuSet
        arm7tdmi_instance.bios.swi_cpuset(registers[0], registers[1], registers[2], registers[2])
    elif swi_num == 0x0C:  # CpuFastSet
        arm7tdmi_instance.bios.swi_cpufastset(registers[0], registers[1], registers[2], registers[2])
    elif swi_num == 0x09:  # ArcTan
        registers[0] = arm7tdmi_instance.bios.swi_arctan(registers[0]) & 0xFFFF
    elif swi_num == 0x0A:  # ArcTan2
        registers[0] = arm7tdmi_instance.bios.swi_arctan2(registers[0], registers[1]) & 0xFFFF
    elif swi_num == 0x0E:  # BgAffineSet
        arm7tdmi_instance.bios.swi_bg_affine_set(registers[0], registers[1], registers[2], registers[3])
    elif swi_num == 0x0F:  # ObjAffineSet
        _data = registers[0]
        _param_table = registers[1]
        _num_objects = registers[2]
        _increment = registers[3]
        for i in range(_num_objects):
            _offset = i * _increment
            arm7tdmi_instance.bios.swi_obj_affine_set(
                _param_table + _offset,
                memory.read_u16(_data + _offset * 2),
                memory.read_u16(_data + _offset * 2 + 2),
                memory.read_u16(_data + _offset * 2 + 4)
            )
    elif swi_num == 0x10:  # BitUnPack
        arm7tdmi_instance.bios.swi_bit_unpack(registers[0], registers[1], registers[2])
    elif swi_num == 0x11:  # LZ77UnCompWram
        arm7tdmi_instance.bios.swi_lz77_uncomp(registers[0], registers[1])
    elif swi_num == 0x12:  # LZ77UnCompVram
        arm7tdmi_instance.bios.swi_lz77_uncomp(registers[0], registers[1])
    elif swi_num == 0x13:  # HuffmanUnComp
        arm7tdmi_instance.bios.swi_huff_uncomp(registers[0], registers[1])
    elif swi_num == 0x14:  # RLUnCompWram
        arm7tdmi_instance.bios.swi_rl_uncomp(registers[0], registers[1])
    elif swi_num == 0x15:  # RLUnCompVram
        arm7tdmi_instance.bios.swi_rl_uncomp(registers[0], registers[1])
    elif swi_num == 0x16:  # Diff8bitUnFilterWram
        arm7tdmi_instance.bios.swi_diff_unfilter(registers[0], registers[1], is_16bit=False)
    elif swi_num == 0x17:  # Diff8bitUnFilterVram
        arm7tdmi_instance.bios.swi_diff_unfilter(registers[0], registers[1], is_16bit=False)
    elif swi_num == 0x18:  # Diff16bitUnFilter
        arm7tdmi_instance.bios.swi_diff_unfilter(registers[0], registers[1], is_16bit=True)
    elif swi_num == 0x19:  # SoundDriverInit
        # Store sound driver work area pointer for later use
        global _sound_work_area
        _sound_work_area = registers[0]
    elif swi_num == 0x1A:  # SoundDriverMode
        # Store sound driver mode
        global _sound_mode
        _sound_mode = registers[0]
    elif swi_num == 0x1B:  # SoundDriverMain
        # Main sound driver processing - minimal (pygame handles audio)
        pass
    elif swi_num == 0x1C:  # SoundDriverVSync
        # VBlank sound processing - minimal
        pass
    elif swi_num == 0x1D:  # SoundChannelClear
        # Clear sound channels - no-op (pygame handles channels)
        pass
    elif swi_num == 0x1E:  # MidiKey2Freq
        # Convert MIDI key to frequency
        # r1 = MIDI key number (fixed-point with 8-bit fractional part)
        # Formula: freq = 440 * 2^((key - 69) / 12)
        key_fixed = registers[1]
        key = key_fixed / 256.0
        freq = 440.0 * (2.0 ** ((key - 69.0) / 12.0))
        registers[0] = int(freq * 256) & 0xFFFFFFFF
    elif swi_num == 0x1F:  # SoundDriverVSyncOff
        # Disable VSync sound processing
        global _sound_vsync_enabled
        _sound_vsync_enabled = False
def _sync_state_to_cpu(registers, cpsr):
    global _interp_cpu
    if _interp_cpu is None:
        _interp_cpu = ARM7TDMI(memory)
        memory.cpu = _interp_cpu
    for i in range(16):
        _interp_cpu.registers[i] = registers[i]
    _interp_cpu.cpsr = _cpsr_to_int(cpsr)
    _interp_cpu.mode = cpsr.get('mode', 0x1F) & 0x1F
    _interp_cpu.spsr[_MODE_TO_SPSR_IDX.get(0x12, 6)] = cpsr.get('spsr_irq', 0) & 0xFFFFFFFF
    _interp_cpu.spsr[_MODE_TO_SPSR_IDX.get(0x13, 2)] = cpsr.get('spsr_svc', 0) & 0xFFFFFFFF
    _interp_cpu.spsr[_MODE_TO_SPSR_IDX.get(0x17, 3)] = cpsr.get('spsr_abt', 0) & 0xFFFFFFFF
    _interp_cpu.spsr[_MODE_TO_SPSR_IDX.get(0x1B, 4)] = cpsr.get('spsr_und', 0) & 0xFFFFFFFF
    _interp_cpu.spsr[_MODE_TO_SPSR_IDX.get(0x1F, 1)] = cpsr.get('spsr_sys', 0) & 0xFFFFFFFF
    _interp_cpu.thumb_mode = bool(cpsr.get('t', 0))
    for _m, _b in banked_sp_lr.items():
        if _m in _interp_cpu.banked_sp_lr:
            _ib = _interp_cpu.banked_sp_lr[_m]
            _ib['sp'] = _b['sp']; _ib['lr'] = _b['lr']
            if _m == 0x11:
                _ib['r8'] = _b.get('r8', 0); _ib['r9'] = _b.get('r9', 0)
                _ib['r10'] = _b.get('r10', 0); _ib['r11'] = _b.get('r11', 0)
                _ib['r12'] = _b.get('r12', 0)

def _sync_state_from_cpu(registers, cpsr):
    for i in range(16):
        registers[i] = _interp_cpu.registers[i]
    _cpsr_from_int(cpsr, _interp_cpu.cpsr)
    cpsr['mode'] = _interp_cpu.mode & 0x1F
    cpsr['spsr_irq'] = _interp_cpu.spsr[_MODE_TO_SPSR_IDX.get(0x12, 6)] & 0xFFFFFFFF
    cpsr['spsr_svc'] = _interp_cpu.spsr[_MODE_TO_SPSR_IDX.get(0x13, 2)] & 0xFFFFFFFF
    cpsr['spsr_abt'] = _interp_cpu.spsr[_MODE_TO_SPSR_IDX.get(0x17, 3)] & 0xFFFFFFFF
    cpsr['spsr_und'] = _interp_cpu.spsr[_MODE_TO_SPSR_IDX.get(0x1B, 4)] & 0xFFFFFFFF
    cpsr['spsr_sys'] = _interp_cpu.spsr[_MODE_TO_SPSR_IDX.get(0x1F, 1)] & 0xFFFFFFFF
    for _m, _ib in _interp_cpu.banked_sp_lr.items():
        if _m in banked_sp_lr:
            _b = banked_sp_lr[_m]
            _b['sp'] = _ib['sp']; _b['lr'] = _ib['lr']
            if _m == 0x11:
                _b['r8'] = _ib.get('r8', 0); _b['r9'] = _ib.get('r9', 0)
                _b['r10'] = _ib.get('r10', 0); _b['r11'] = _ib.get('r11', 0)
                _b['r12'] = _ib.get('r12', 0)

def _interp_fallback(registers, cpsr, max_steps=2000, irq_return_pc=None):
    global _interp_cpu
    global _cpu_halted, _halt_reason, _swi_lr, _swi_caller_pc
    _sync_state_to_cpu(registers, cpsr)
    _step_count = 0
    while _step_count < max_steps:
        _pc = _interp_cpu.registers[15]
        if not (0x02000000 <= _pc < 0x02040000
                or 0x03000000 <= _pc < 0x03008000
                or 0x04000000 <= _pc < 0x04000400
                or 0x05000000 <= _pc < 0x05000400
                or 0x06000000 <= _pc < 0x06020000
                or 0x07000000 <= _pc < 0x07000400
                or 0x08000000 <= _pc < 0x0A000000):
            _cpu_halted = True
            _halt_reason = 'unmapped_pc'
            break
        if irq_return_pc is not None and (_pc == irq_return_pc or _pc == ((irq_return_pc + 4) & 0xFFFFFFFF) or _pc == ((irq_return_pc + 4) & 0xFFFFFFFC) or _pc == ((irq_return_pc + 2) & 0xFFFFFFFF)):
            break
        # Check for ROM dispatch table lookup
        if 0x08000000 <= _pc < 0x0A000000:
            _idx = (_pc - 0x08000000) >> (1 if _interp_cpu.thumb_mode else 2)
            if _interp_cpu.thumb_mode:
                if dispatch_table_thumb.get(_idx) is not None:
                    break
            else:
                if dispatch_table_arm.get(_idx) is not None:
                    break
        # If PC is NOT in ROM range (e.g., IWRAM, EWRAM, BIOS), execute one step and return
        # This allows the main loop to advance the PPU
        # NOTE: This break was removed to allow batch execution of non-ROM code
        # if not (0x08000000 <= _pc < 0x0A000000):
        #     break
        _old_pc = _pc
        _interp_cpu.step()
        _step_count += 1
        # Dynamic dispatch table expansion for indirect calls
        # When BX Rm or BLX Rm executes, the new PC may not be in the dispatch table
        _new_pc = _interp_cpu.registers[15]
        if 0x08000000 <= _new_pc < 0x0A000000 and _new_pc != _old_pc:
            # PC changed to a new ROM address - add to dispatch table
            _new_idx = (_new_pc - 0x08000000) >> (1 if _interp_cpu.thumb_mode else 2)
            if _interp_cpu.thumb_mode:
                if _new_idx not in dispatch_table_thumb:
                    dispatch_table_thumb[_new_idx] = None  # Add entry only if not already present
            else:
                if _new_idx not in dispatch_table_arm:
                    dispatch_table_arm[_new_idx] = None  # Add entry only if not already present
        
        if getattr(_interp_cpu, '_halted', False):
            _interp_cpu._halted = False
            _cpu_halted = True
            _halt_reason = getattr(_interp_cpu, '_halt_reason', 'any')
            _swi_lr = getattr(_interp_cpu, '_swi_lr', None)
            _swi_caller_pc = getattr(_interp_cpu, '_swi_caller_pc', None)
            break
    _sync_state_from_cpu(registers, cpsr)
    return _step_count

def run_transpiled(headless=False, frame_limit=None, screenshot_path=None, scale=1, max_instrs=10000000, pc_trace=None, trace_n=0, audio_capture=None, watch_reg=None, dump_at=None):
    global _cpu_halted
    speed_ratio, calibrated_delay, cycles_per_second, gba_hz = calibrate_gba_timing()
    def ror(v, a):
        a = a & 31
        return ((v >> a) | (v << (32 - a))) & 0xFFFFFFFF
    fc = 0; mi = max_instrs; ic = 0
    _irq_return_pc = None
    _pending_irq_bits = 0
    _irq_saved_r0 = 0
    _irq_saved_r1 = 0
    _irq_saved_r2 = 0
    _irq_saved_r3 = 0
    _irq_saved_r12 = 0
    _trace_file = open(pc_trace, "w") if pc_trace else None
    _trace_count = 0
    _watch_reg_idx = None
    _watch_reg_prev = None
    if watch_reg:
        _reg_map = {'r0': 0, 'r1': 1, 'r2': 2, 'r3': 3, 'r4': 4, 'r5': 5, 'r6': 6, 'r7': 7, 'r8': 8, 'r9': 9, 'r10': 10, 'r11': 11, 'r12': 12, 'sp': 13, 'lr': 14, 'pc': 15}
        _watch_reg_idx = _reg_map.get(watch_reg.lower())
        if _watch_reg_idx is None:
            print(f"Unknown register: {watch_reg}", file=sys.stderr)
    _dump_target_pc = None
    _dump_region_name = None
    _dump_done = False
    if dump_at:
        _parts = dump_at.split(':')
        _dump_target_pc = int(_parts[0], 0)
        _dump_region_name = _parts[1] if len(_parts) > 1 else 'iwram'
    _audio_buf = bytearray() if audio_capture else None
    _audio_synth_per_frame = 735
    instr_per_scanline = max(50, int(gba_hz / 60.0) // 228)
    _instr_per_frame = instr_per_scanline * 228
    _max_inner_stalls = max(50, instr_per_scanline // 2)
    __DELIVER_IRQ_BODY__
    _load_sram()
    _dt_arm = dispatch_table_arm
    _dt_thumb = dispatch_table_thumb
    _has_timers = timers_instance is not None
    while ic < mi:
        if frame_limit and fc >= frame_limit: break
        for _scanline in range(228):
            if ic >= mi:
                break
            _inner_stalls = 0
            _inner_ic_start = ic
            while (ic - _inner_ic_start) < instr_per_scanline:
                if _cpu_halted or ic >= mi:
                    break
                pc = registers[15]
                if _trace_file:
                    _cur_w = registers[_watch_reg_idx] if _watch_reg_idx is not None else None
                    if (trace_n == 0 or _trace_count < trace_n) and (_watch_reg_idx is None or _cur_w != _watch_reg_prev):
                        _trace_file.write(f"PC=0x{pc:08X} R0={registers[0]:08X} R1={registers[1]:08X} R2={registers[2]:08X} R3={registers[3]:08X} R8={registers[8]:08X} R9={registers[9]:08X} R10={registers[10]:08X} R12={registers[12]:08X} LR={registers[14]:08X} SP={registers[13]:08X} mode={cpsr.get('mode', 0):#x} i={cpsr.get('i', 0)} t={cpsr.get('t', 0)}\n")
                        _trace_count += 1
                        _watch_reg_prev = _cur_w
                if dump_at and not _dump_done and pc == _dump_target_pc:
                    _regions = {'ewram': memory.ewram, 'iwram': memory.iwram, 'vram': memory.vram, 'palette': memory.palette, 'oam': memory.oam}
                    _rd = _regions.get(_dump_region_name, memory.iwram)
                    with open(f'/tmp/dump_{_dump_region_name}_at_{pc:08X}.bin', 'wb') as _df:
                        _df.write(bytes(_rd))
                    print(f"Dumped {_dump_region_name} ({len(_rd)} bytes) at PC=0x{pc:08X}", flush=True)
                    _dump_done = True
                _t = cpsr.get('t', 0)
                idx = (pc - 0x08000000) >> (1 if _t else 2)
                _dt = _dt_thumb if _t else _dt_arm
                func = _dt.get(idx)
                if func is None:
                    # PC not in dispatch table - could be IWRAM/EWRAM code or unknown ROM address
                    # If PC is NOT in ROM range, execute one CPU step directly and continue
                    # This prevents infinite fallback loops for IWRAM code
                    if not (0x08000000 <= pc < 0x0A000000):
                        # Non-ROM address: batch execute via fallback interpreter
                        _budget = instr_per_scanline - (ic - _inner_ic_start)
                        if _budget <= 0:
                            _budget = 1
                        _steps = _interp_fallback(registers, cpsr, max_steps=_budget, irq_return_pc=_irq_return_pc)
                        _steps = max(1, _steps)
                        ic += _steps
                        if _has_timers:
                            timers_instance.step(4 * _steps)
                    else:
                        # ROM address not in dispatch table - use fallback interpreter
                        _budget = instr_per_scanline - (ic - _inner_ic_start)
                        if _budget <= 0:
                            _budget = 1
                        _steps = _interp_fallback(registers, cpsr, max_steps=_budget, irq_return_pc=_irq_return_pc)
                        _steps = max(1, _steps)
                        ic += _steps
                        if _has_timers:
                            timers_instance.step(4 * _steps)
                        if _irq_return_pc is not None and (registers[15] == _irq_return_pc or registers[15] == ((_irq_return_pc + 4) & 0xFFFFFFFF) or registers[15] == ((_irq_return_pc + 4) & 0xFFFFFFFC)):
                            break
                else:
                    func(registers, cpsr); ic += 1
                    if _has_timers:
                        timers_instance.step(4)
                    if registers[15] == pc:
                        _inner_stalls += 1
                        if _inner_stalls > _max_inner_stalls:
                            break
                    else:
                        _inner_stalls = 0
            _deliver_irq()
            ppu_instance.step_scanline()
            _deliver_irq()
            ppu_instance.recapture_window_snapshot()
            if _has_timers:
                timers_instance.step(960)
            if serial_instance is not None:
                serial_instance.step()
            ppu_instance.fire_hblank_irq()
            _deliver_irq()
        ppu_instance.render_frame()
        if _audio_buf is not None:
            _audio_buf.extend(apu_instance._generate_samples(_audio_synth_per_frame))
        fc += 1
    if screenshot_path:
        import pygame
        surf = ppu_instance.get_surface()
        pygame.image.save(surf, screenshot_path)
    if _audio_buf is not None:
        import wave, array
        _s16 = array.array('h', [((b - 128) << 8) for b in _audio_buf])
        with wave.open(audio_capture, 'wb') as _wav:
            _wav.setnchannels(2)
            _wav.setsampwidth(2)
            _wav.setframerate(44100)
            _wav.writeframes(_s16.tobytes())
    _save_sram()
    return fc

def run_with_pygame(headless=False, frame_limit=None, screenshot_path=None, scale=1, dump_memory=None, dump_region=None, load_state=None, save_state=None, hook_file=None, pc_trace=None, trace_n=0, max_instrs=10000000, watch_reg=None, dump_at=None):
    global _cpu_halted
    # Initialize HookManager if hook file provided
    hook_manager = HookManager() if hook_file else None
    trace_file = None
    if pc_trace:
        trace_file = open(pc_trace, "w")
    trace_count = 0
    _watch_reg_idx = None
    _watch_reg_prev = None
    if watch_reg:
        _reg_map = {'r0': 0, 'r1': 1, 'r2': 2, 'r3': 3, 'r4': 4, 'r5': 5, 'r6': 6, 'r7': 7, 'r8': 8, 'r9': 9, 'r10': 10, 'r11': 11, 'r12': 12, 'sp': 13, 'lr': 14, 'pc': 15}
        _watch_reg_idx = _reg_map.get(watch_reg.lower())
        if _watch_reg_idx is None:
            print(f"Unknown register: {watch_reg}", file=sys.stderr)
    _dump_target_pc = None
    _dump_region_name = None
    _dump_done = False
    if dump_at:
        _parts = dump_at.split(':')
        _dump_target_pc = int(_parts[0], 0)
        _dump_region_name = _parts[1] if len(_parts) > 1 else 'iwram'
    if hook_file:
        # Load and execute hook script
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("hook_script", hook_file)
            hook_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(hook_module)
            # Call setup_hooks if it exists
            if hasattr(hook_module, 'setup_hooks'):
                hook_module.setup_hooks(hook_manager)
                print(f"Hooks loaded from: {hook_file}")
        except Exception as e:
            print(f"Warning: Failed to load hooks from {hook_file}: {e}", file=sys.stderr)
    _irq_return_pc = None
    _pending_irq_bits = 0
    _irq_saved_r0 = 0
    _irq_saved_r1 = 0
    _irq_saved_r2 = 0
    _irq_saved_r3 = 0
    _irq_saved_r12 = 0
    __DELIVER_IRQ_BODY__
    _load_sram()
    running = True
    fc = 0; mi = max_instrs; ic = 0
    while running and ic < mi and fc < (frame_limit or 10000):
        for e in pygame.event.get():
            if e.type == pygame.QUIT: running = False
            # Handle save state hotkeys: F5=save, F8=load
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_F5 and save_state_mgr:
                    # Save state to default file or provided path
                    save_path = save_state if save_state else "save_state.json"
                    print(f"Saving state to: {save_path}")
                    if save_state_mgr.save(save_path):
                        print(f"State saved successfully")
                    else:
                        print(f"Warning: Failed to save state to {save_path}", file=sys.stderr)
                elif e.key == pygame.K_F8 and save_state_mgr:
                    # Load state from default file or provided path
                    load_path = load_state if load_state else "save_state.json"
                    print(f"Loading state from: {load_path}")
                    if save_state_mgr.load(load_path):
                        print(f"State loaded successfully")
                    else:
                        print(f"Warning: Failed to load state from {load_path}", file=sys.stderr)
        # Execute instructions for this frame, stepping PPU scanlines
        # Each scanline: run a batch of instructions, then advance VCount + fire HBlank DMA
        target_cycles_per_frame = int(gba_hz / 60.0)
        instr_per_scanline = max(50, target_cycles_per_frame // 228)
        max_inner_stalls = max(50, instr_per_scanline // 2)
        _dt_arm = dispatch_table_arm
        _dt_thumb = dispatch_table_thumb
        _has_timers = timers_instance is not None
        for _scanline in range(228):
            if ic >= mi:
                break
            inner_loop_stalls = 0
            _inner_ic_start = ic
            while (ic - _inner_ic_start) < instr_per_scanline:
                if _cpu_halted or ic >= mi:
                    break
                pc = registers[15]
                _t = cpsr.get('t', 0)
                idx = (pc - 0x08000000) >> (1 if _t else 2)
                _dt = _dt_thumb if _t else _dt_arm
                func = _dt.get(idx)
                if func is None:
                    # PC not in dispatch table - could be IWRAM/EWRAM code or unknown ROM address
                    # If PC is NOT in ROM range, execute one CPU step directly and continue
                    # This prevents infinite fallback loops for IWRAM code
                    if not (0x08000000 <= pc < 0x0A000000):
                        # Non-ROM address: batch execute via fallback interpreter
                        _budget = instr_per_scanline - (ic - _inner_ic_start)
                        if _budget <= 0:
                            _budget = 1
                        _steps = _interp_fallback(registers, cpsr, max_steps=_budget, irq_return_pc=_irq_return_pc)
                        _steps = max(1, _steps)
                        ic += _steps
                        if _has_timers:
                            timers_instance.step(4 * _steps)
                    else:
                        # ROM address not in dispatch table - use fallback interpreter
                        _budget = instr_per_scanline - (ic - _inner_ic_start)
                        if _budget <= 0:
                            _budget = 1
                        _steps = _interp_fallback(registers, cpsr, max_steps=_budget, irq_return_pc=_irq_return_pc)
                        _steps = max(1, _steps)
                        ic += _steps
                        if _has_timers:
                            timers_instance.step(4 * _steps)
                        if _irq_return_pc is not None and (registers[15] == _irq_return_pc or registers[15] == ((_irq_return_pc + 4) & 0xFFFFFFFF) or registers[15] == ((_irq_return_pc + 4) & 0xFFFFFFFC)):
                            break
                    continue
                func(registers, cpsr); ic += 1
                if _has_timers:
                    timers_instance.step(4)
                _cur_w = registers[_watch_reg_idx] if _watch_reg_idx is not None else None
                if pc_trace and trace_file and (_watch_reg_idx is None or _cur_w != _watch_reg_prev):
                    trace_file.write(f"{ic:08d} PC=0x{registers[15]:08X} R0={registers[0]:08X} R1={registers[1]:08X} R2={registers[2]:08X} R3={registers[3]:08X} R14={registers[14]:08X}\n")
                    _watch_reg_prev = _cur_w
                if dump_at and not _dump_done and pc == _dump_target_pc:
                    _regions = {'ewram': memory.ewram, 'iwram': memory.iwram, 'vram': memory.vram, 'palette': memory.palette, 'oam': memory.oam}
                    _rd = _regions.get(_dump_region_name, memory.iwram)
                    with open(f'/tmp/dump_{_dump_region_name}_at_{pc:08X}.bin', 'wb') as _df:
                        _df.write(bytes(_rd))
                    print(f"Dumped {_dump_region_name} ({len(_rd)} bytes) at PC=0x{pc:08X}", flush=True)
                    _dump_done = True
                if trace_n > 0 and trace_count < trace_n:
                    print(f"{ic:08d} PC=0x{registers[15]:08X} R0={registers[0]:08X} R1={registers[1]:08X} R2={registers[2]:08X} R3={registers[3]:08X}")
                    trace_count += 1
                if registers[15] == pc:
                    inner_loop_stalls += 1
                    if inner_loop_stalls > max_inner_stalls:
                        break
                else:
                    inner_loop_stalls = 0
                if hook_manager and hook_manager.has_hooks():
                    if hook_manager.check_hooks(registers[15], 'instruction'):
                        print("Execution paused at breakpoint")
                        break
            _deliver_irq()
            ppu_instance.step_scanline()
            _deliver_irq()
            ppu_instance.recapture_window_snapshot()
            if _has_timers:
                timers_instance.step(960)
            if serial_instance is not None:
                serial_instance.step()
            ppu_instance.fire_hblank_irq()
            _deliver_irq()
        # Render the completed frame
        ppu_instance.render_frame()
        # Update APU audio
        if apu_instance: apu_instance.update()
        surf = ppu_instance.get_surface()
        screen.blit(pygame.transform.scale(surf, (240 * scale, 160 * scale)), (0, 0))
        if not headless: pygame.display.flip()
        clock.tick(60); fc += 1
        # Notify frame hooks
        if hook_manager and hook_manager.has_hooks():
            hook_manager.notify_frame(fc)
        if frame_limit and fc >= frame_limit: break
    if screenshot_path:
        pygame.image.save(screen, screenshot_path)
        print(f"Screenshot: {screenshot_path}")
    
    # Save state if requested
    if save_state and save_state_mgr:
        print(f"Saving state to: {save_state}")
        if save_state_mgr.save(save_state):
            print(f"State saved successfully")
        else:
            print(f"Warning: Failed to save state to {save_state}", file=sys.stderr)
    
    pygame.mixer.quit()
    pygame.quit()
    
    # Dump memory if requested
    if dump_memory:
        with open(dump_memory, 'wb') as f:
            if dump_region:
                # Map region name to memory array
                regions = {
                    'ewram': memory.ewram,
                    'iwram': memory.iwram,
                    'vram': memory.vram,
                    'palette': memory.palette,
                    'oam': memory.oam
                }
                region_data = regions.get(dump_region, memory.ewram)
                f.write(bytes(region_data))
            else:
                # Default: dump full EWRAM (256KB)
                f.write(bytes(memory.ewram))
        print(f"Memory dump written to: {dump_memory}")
    
    if trace_file:
        trace_file.close()
        print(f"PC trace written to: {pc_trace} ({ic} instructions)")
    
    _save_sram()
    return fc

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--frame", type=int)
    parser.add_argument("--screenshot", type=str)
    parser.add_argument("--scale", type=int, default=1)
    parser.add_argument("--dump-memory", type=str, help="Dump memory to binary file")
    parser.add_argument("--dump-region", type=str, help="Specific region to dump (ewram/iwram/vram/palette/oam)")
    parser.add_argument("--save-state", type=str, help="Save state to JSON file after execution")
    parser.add_argument("--load-state", type=str, help="Load state from JSON file before execution")
    parser.add_argument("--hook-file", type=str, help="Python script with debugging hooks (breakpoints, tracing, etc.)")
    parser.add_argument("--pc-trace", type=str, help="Log PC + registers each step to a file")
    parser.add_argument("--trace-n", type=int, default=0, help="Print first N PCs to stdout then stop tracing")
    parser.add_argument("--max-instrs", type=int, default=10000000, help="Maximum instructions before aborting (default 10M)")
    parser.add_argument("--watch-reg", type=str, help="Filter PC trace to only lines where this register changes (e.g. SP, R0, LR)")
    parser.add_argument("--dump-at", type=str, help="Dump memory region when PC first hits target. Format: 0xPC[:region] (e.g. 0x080182CC:iwram)")
    parser.add_argument("--audio-capture", type=str, help="Capture audio to WAV file (stereo, 16-bit signed, 44100 Hz)")
    parser.add_argument("--profile", type=str, help="Dump cProfile stats to file")
    parser.add_argument("--debug-ppu", action="store_true", help="Re-raise PPU rendering exceptions with context for debugging")
    args = parser.parse_args()
    if args.debug_ppu:
        os.environ['GBATOPY_DEBUG_PPU'] = '1'
    if args.profile:
        import cProfile
        pr = cProfile.Profile()
        pr.enable()
    if args.headless:
        _unsupported = []
        if args.dump_memory:
            _unsupported.append("--dump-memory")
        if args.dump_region:
            _unsupported.append("--dump-region")
        if args.hook_file:
            _unsupported.append("--hook-file")
        if args.load_state:
            _unsupported.append("--load-state")
        if args.save_state:
            _unsupported.append("--save-state")
        if _unsupported:
            print(f"Error: --headless does not support: {', '.join(_unsupported)}", file=sys.stderr)
            sys.exit(1)
        frames = run_transpiled(
            headless=True,
            frame_limit=args.frame,
            screenshot_path=args.screenshot,
            scale=args.scale,
            max_instrs=args.max_instrs,
            pc_trace=args.pc_trace,
            trace_n=args.trace_n,
            audio_capture=args.audio_capture,
            watch_reg=args.watch_reg,
            dump_at=args.dump_at,
        )
    else:
        frames = run_with_pygame(
            headless=args.headless, 
            frame_limit=args.frame, 
            screenshot_path=args.screenshot, 
            scale=args.scale,
            dump_memory=args.dump_memory,
            dump_region=args.dump_region,
            load_state=args.load_state,
            save_state=args.save_state,
            hook_file=args.hook_file,
            pc_trace=args.pc_trace,
            trace_n=args.trace_n,
            max_instrs=args.max_instrs,
            watch_reg=args.watch_reg,
            dump_at=args.dump_at,
        )
    if args.profile:
        pr.disable()
        pr.dump_stats(args.profile)
        print(f"Profile stats written to: {args.profile}", flush=True)
    print(f"{frames} frames")
    # Report swallowed PPU exceptions if any
    try:
        from gba_runtime import ppu as _ppu_module
        if hasattr(_ppu_module, '_SWALLOWED_COUNT') and _ppu_module._SWALLOWED_COUNT > 0:
            print(f"PPU: {_ppu_module._SWALLOWED_COUNT} exceptions swallowed during rendering", flush=True)
    except ImportError:
        pass
    import os; os._exit(0)
