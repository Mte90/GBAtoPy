# === Optimized APU with Array Buffers ===

import array

class OptimizedAPU:
    """APU with array-based buffers for better performance."""
    
    def __init__(self):
        # Use array.array instead of list for better memory efficiency
        self.channel1_buffer = array.array('h', [0] * 4096)
        self.channel2_buffer = array.array('h', [0] * 4096)
        self.channel3_buffer = array.array('h', [0] * 4096)
        self.channel4_buffer = array.array('h', [0] * 4096)
        self.mix_buffer = array.array('h', [0] * 4096)
        
        self.buffer_pos = 0
        self.sample_rate = 44100
    
    def generate_sample(self):
        """Generate a single audio sample."""
        sample = (
            self.channel1_buffer[self.buffer_pos] +
            self.channel2_buffer[self.buffer_pos] +
            self.channel3_buffer[self.buffer_pos] +
            self.channel4_buffer[self.buffer_pos]
        ) // 4
        
        self.buffer_pos = (self.buffer_pos + 1) % 4096
        return sample


# === Optimized Interrupt System ===

class OptimizedInterrupts:
    """Interrupt system with bitfield flags."""
    
    def __init__(self):
        # Single integer as bitfield instead of dict
        self.irq_flags = 0
        
        # Bit positions
        self.VBLANK_IRQ = 1 << 0
        self.HBLANK_IRQ = 1 << 1
        self.VCOUNT_IRQ = 1 << 2
        self.TIMER0_IRQ = 1 << 3
        self.TIMER1_IRQ = 1 << 4
        self.TIMER2_IRQ = 1 << 5
        self.TIMER3_IRQ = 1 << 6
        self.DMA0_IRQ = 1 << 7
        self.DMA1_IRQ = 1 << 8
        self.DMA2_IRQ = 1 << 9
        self.DMA3_IRQ = 1 << 10
        self.SIO_IRQ = 1 << 11
        self.KEYPAD_IRQ = 1 << 12
    
    def set_flag(self, flag):
        """Set an interrupt flag."""
        self.irq_flags |= flag
    
    def clear_flag(self, flag):
        """Clear an interrupt flag."""
        self.irq_flags &= ~flag
    
    def check_flag(self, flag):
        """Check if an interrupt flag is set."""
        return bool(self.irq_flags & flag)
    
    def has_pending(self):
        """Check if any interrupt is pending."""
        return self.irq_flags != 0


# === Optimized DMA with Slice Assignment ===

class OptimizedDMA:
    """DMA with array slice assignment for bulk transfers."""
    
    def transfer_fast(self, src, dst, count):
        """Fast bulk transfer using slice assignment."""
        dst[:count] = src[:count]
    
    def transfer_fifo(self, src, dst, fifo_size):
        """FIFO transfer with wraparound."""
        dst[self.pos:self.pos + fifo_size] = src[:fifo_size]
        self.pos = (self.pos + fifo_size) % len(dst)


# === Optimized Timer System ===

class OptimizedTimer:
    """Timer with integer arithmetic."""
    
    def __init__(self):
        self.count = 0
        self.overflow = 0
        self.prescaler = 0  # 0=1, 1=64, 2=256, 3=1024
        self.shift = [0, 6, 8, 10][self.prescaler]  # Pre-calculated
    
    def increment(self, cycles):
        """Increment timer with integer math."""
        self.count += (cycles >> self.shift)
        if self.count >= 65536:
            self.count -= 65536
            self.overflow += 1
            return True
        return False


# === Consolidated GBA State ===

class GBAState:
    """Single class for all GBA state."""
    
    def __init__(self):
        self.cpu = CPU()
        self.ppu = PPU()
        self.apu = OptimizedAPU()
        self.interrupts = OptimizedInterrupts()
        self.dma = [OptimizedDMA() for _ in range(4)]
        self.timers = [OptimizedTimer() for _ in range(4)]
        self.memory = Memory()
        self.keypad = 0
        self.sram = bytearray(0x8000)
        
        # Execution state
        self.pc = 0
        self.cycles = 0
        self.irq_pending = False
        self.halted = False
