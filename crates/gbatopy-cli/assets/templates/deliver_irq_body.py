
    def _deliver_irq():
        nonlocal _irq_return_pc, _pending_irq_bits, _irq_saved_r0, _irq_saved_r1, _irq_saved_r2, _irq_saved_r3, _irq_saved_r12
        global _cpu_halted, _halt_reason, _swi_lr, _swi_caller_pc
        _irq = getattr(memory, '_interrupts', None)
        if _irq is None:
            return
        # Use cached IF/IE registers (avoids misinterpreting raw STRH writes to IF)
        if_live = _irq.if_reg
        ie_live = _irq.ie_reg
        if _cpu_halted:
            if _halt_reason == "vblank":
                ime_live = (memory.io[0x208] | (memory.io[0x209] << 8)) & 0x0001
                if (_irq.if_reg & (1 << 0)) and (_irq.ie_reg & (1 << 0)) and ime_live:
                    _cpu_halted = False
                    _halt_reason = None
            elif _halt_reason == "any":
                _any_pending = _irq.if_reg & _irq.ie_reg
                if _any_pending:
                    _cpu_halted = False
                    _halt_reason = None
        # Do NOT return early if CPU was just woken up - continue to deliver the IRQ
        if _irq_return_pc is not None:
            _bx_lr_return = (registers[15] == ((_irq_return_pc + 4) & 0xFFFFFFFF) or registers[15] == ((_irq_return_pc + 4) & 0xFFFFFFFC))
            if registers[15] != _irq_return_pc and not _bx_lr_return:
                return
            _resume_pc = _irq_return_pc
            _irq_return_pc = None
            _saved = cpsr.get('spsr_irq', 0)
            _saved_mode = _saved & 0x1F
            if _saved_mode != cpsr.get('mode', 0x1F):
                _switch_mode(_saved_mode)
            cpsr['mode'] = _saved_mode
            cpsr['i'] = (_saved >> 7) & 1
            cpsr['f'] = (_saved >> 6) & 1
            cpsr['t'] = (_saved >> 5) & 1
            cpsr['n'] = (_saved >> 31) & 1
            cpsr['z'] = (_saved >> 30) & 1
            cpsr['c'] = (_saved >> 29) & 1
            cpsr['v'] = (_saved >> 28) & 1
            # Clear pending bits
            _irq.if_reg &= ~_pending_irq_bits
            _pending_irq_bits = 0
            registers[0] = _irq_saved_r0
            registers[1] = _irq_saved_r1
            registers[2] = _irq_saved_r2
            registers[3] = _irq_saved_r3
            registers[12] = _irq_saved_r12
            if _swi_lr is not None:
                registers[14] = _swi_lr
                _swi_lr = None
            if _swi_caller_pc is not None:
                registers[15] = _swi_caller_pc
                _swi_caller_pc = None
            elif _bx_lr_return:
                registers[15] = _resume_pc
            return
        _pending = _irq.if_reg & _irq.ie_reg
        if not _pending:
            return
        ime_live = (memory.io[0x208] | (memory.io[0x209] << 8)) & 0x0001
        if not ime_live:
            return
        _handler = memory.read_u32(0x03007FFC)
        if not ((0x02000000 <= _handler < 0x04000000) or (0x08000000 <= _handler < 0x0A000000)):
            return
        _irq_return_pc = registers[15]
        _pending_irq_bits = _pending
        _cpsr_int = _cpsr_to_int(cpsr)
        cpsr['spsr_irq'] = _cpsr_int
        _irq_saved_r0 = registers[0]
        _irq_saved_r1 = registers[1]
        _irq_saved_r2 = registers[2]
        _irq_saved_r3 = registers[3]
        _irq_saved_r12 = registers[12]
        _switch_mode(0x12)
        cpsr['i'] = 1
        registers[14] = (registers[15] + 4) & 0xFFFFFFFF
        registers[15] = _handler & 0xFFFFFFFE
        cpsr['t'] = 1 if (_handler & 1) else 0
        _interp_cpu.thumb_mode = bool(cpsr['t'])
