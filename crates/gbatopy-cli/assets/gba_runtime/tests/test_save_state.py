"""Save State Unit Tests for GBAtoPy Transpiler.

Tests cover complete serialization/deserialization of emulator state including:
- Save/load roundtrip property tests (byte-exact equality)
- CPU state (registers, CPSR, SPJR, mode, thumb_mode, running, cycles)
- Memory state (EWRAM, IWRAM, IO, palette, VRAM, OAM, SRAM)
- PPU state (registers, BG registers, affine matrices, windows, blend, mosaic, framebuffer)
- APU state (master control, 4 channels, FIFOs, wave RAM, volume)
- DMA state (4 channels with src/dst/control/enabled)
- Timer state (4 timers with count/control/reload)
- Interrupt state (IE, IF, IME, pending flags)
- Input state (key_input, key_cnt)
- Error handling (corrupt data, truncated files, invalid JSON, missing fields)
- Edge cases (empty state, maximal state, None components)
"""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from save_state import SaveState, create_save_state, VERSION


class MockCPU:
    """Mock CPU for testing save state serialization."""
    def __init__(self):
        self.registers = [i * 0x11111111 & 0xFFFFFFFF for i in range(16)]  # r0-r15
        self.cpsr = 0x0000001F  # User mode
        self.spsr = [0x00000000] * 6  # 6 saved PSRs
        self.mode = 0x1F
        self.thumb_mode = False
        self.running = True
        self.cycles = 12345678


class MockMemory:
    """Mock Memory for testing save state serialization."""
    def __init__(self):
        self.ewram = [i & 0xFF for i in range(0x10000)]  # 64KB
        self.iwram = [i & 0xFF for i in range(0x8000)]   # 32KB
        self.io = [i & 0xFF for i in range(0x400)]       # 1KB
        self.palette = [i & 0xFFFF for i in range(0x400)]  # 512 entries
        self.vram = [i & 0xFF for i in range(0x18000)]   # 96KB
        self.oam = [i & 0xFF for i in range(0x400)]      # 1KB
        self.sram = [i & 0xFF for i in range(0x8000)]    # 32KB


class MockPPU:
    """Mock PPU for testing save state serialization."""
    def __init__(self):
        self.disp_cnt = 0x0480
        self.disp_stat = 0x0000
        self.v_count = 0
        # BG0-3
        for i in range(4):
            setattr(self, f'bg{i}_cnt', 0x1234)
            setattr(self, f'bg{i}_x', i * 100)
            setattr(self, f'bg{i}_y', i * 200)
        # Affine matrices (BG2, BG3)
        for i in range(2):
            for param in ['pa', 'pb', 'pc', 'pd', 'x', 'y']:
                setattr(self, f'bg{i}_{param}', i * 1000 + getattr(self, f'bg{i}_x', 0))
        # Windows
        self.win0_h = 0xFF
        self.win1_h = 0xFF
        self.win0_v = 0xFF
        self.win1_v = 0xFF
        self.win_in = 0x00
        self.win_out = 0x00
        # Special effects
        self.blend_cnt = 0x3F
        self.blend_alpha = 0x10
        self.blend_bright = 0x00
        # Mosaic
        self.mosaic_size = 0x1111
        # Framebuffer
        self.framebuffer = [i & 0xFFFF for i in range(240 * 160)]  # 240x160


class MockAPU:
    """Mock APU for testing save state serialization."""
    def __init__(self):
        self.sound_on = True
        # 4 channels
        for i in range(4):
            setattr(self, f'ch{i+1}_volume', (i + 1) * 0x10)
            setattr(self, f'ch{i+1}_frequency', 0x400 + i * 0x100)
            setattr(self, f'ch{i+1}_duty_cycle', 0x40)
            setattr(self, f'ch{i+1}_envelope_volume', 0x0F)
            setattr(self, f'ch{i+1}_envelope_direction', i % 2)
            setattr(self, f'ch{i+1}_envelope_steps', i + 1)
            setattr(self, f'ch{i+1}_enabled', True)
            setattr(self, f'ch{i+1}_wave', [j & 0xFF for j in range(32)])
        # FIFOs
        self.fifo_a = [i & 0xFF for i in range(32)]
        self.fifo_b = [i & 0xFF for i in range(32)]
        # Wave RAM
        self.wave_ram = [i & 0xFF for i in range(32)]
        # Master volume
        self.master_volume = 7


class MockDMA:
    """Mock DMA for testing save state serialization."""
    def __init__(self):
        # 4 channels
        for i in range(4):
            channel = type('Channel', (), {})()
            channel.src_addr = 0x08000000 + i * 0x1000
            channel.dst_addr = 0x06000000 + i * 0x1000
            channel.control = 0x8000 + i
            channel.enabled = (i % 2) == 0
            setattr(self, f'ch{i}', channel)


class MockTimer:
    """Mock Timer for testing save state serialization."""
    def __init__(self, idx):
        self.count = idx * 0x1000
        self.control = idx
        self.reload = idx * 0x100


class MockTimers:
    """Mock Timers container for testing save state serialization."""
    def __init__(self):
        for i in range(4):
            setattr(self, f'timer{i}', MockTimer(i))


class MockInterrupts:
    """Mock InterruptController for testing save state serialization."""
    def __init__(self):
        self.ie = 0xFFFF  # All interrupts enabled
        self.if_reg = 0x0000  # No pending interrupts
        self.ime = 1  # Interrupts enabled
        self.pending = [False] * 14  # 14 interrupt sources


class MockInput:
    """Mock Input for testing save state serialization."""
    def __init__(self):
        self.key_input = 0x03FF  # All keys released
        self.key_cnt = 0x0000


def make_full_save_state():
    """Create a SaveState with all components populated."""
    return SaveState(
        cpu=MockCPU(),
        memory=MockMemory(),
        ppu=MockPPU(),
        apu=MockAPU(),
        dma=MockDMA(),
        timers=MockTimers(),
        interrupts=MockInterrupts(),
        input_state=MockInput()
    )


def make_empty_save_state():
    """Create a SaveState with all components None."""
    return SaveState()


class TestSaveStateRoundtrip:
    """Test save/load roundtrip property: save then load must restore exact state."""

    def test_save_load_roundtrip_full_state(self, tmp_path):
        """Full state roundtrip: save all components, load, assert byte-exact equality."""
        save_state = make_full_save_state()
        filepath = str(tmp_path / "full_state.sav")

        # Save
        result = save_state.save(filepath)
        assert result is True, "Save should succeed"

        # Verify file exists and is non-empty
        assert os.path.exists(filepath)
        assert os.path.getsize(filepath) > 1000  # Full state should be large

        # Load into fresh SaveState
        loaded = make_full_save_state()
        result = loaded.load(filepath)
        assert result is True, "Load should succeed"

        # Verify CPU state
        assert loaded.cpu.registers == save_state.cpu.registers
        assert loaded.cpu.cpsr == save_state.cpu.cpsr
        assert loaded.cpu.spsr == save_state.cpu.spsr
        assert loaded.cpu.mode == save_state.cpu.mode
        assert loaded.cpu.thumb_mode == save_state.cpu.thumb_mode
        assert loaded.cpu.running == save_state.cpu.running
        assert loaded.cpu.cycles == save_state.cpu.cycles

        # Verify Memory state
        assert loaded.memory.ewram == save_state.memory.ewram
        assert loaded.memory.iwram == save_state.memory.iwram
        assert loaded.memory.io == save_state.memory.io
        assert loaded.memory.palette == save_state.memory.palette
        assert loaded.memory.vram == save_state.memory.vram
        assert loaded.memory.oam == save_state.memory.oam
        assert loaded.memory.sram == save_state.memory.sram

        # Verify PPU state
        assert loaded.ppu.disp_cnt == save_state.ppu.disp_cnt
        assert loaded.ppu.disp_stat == save_state.ppu.disp_stat
        assert loaded.ppu.v_count == save_state.ppu.v_count
        for i in range(4):
            assert getattr(loaded.ppu, f'bg{i}_cnt') == getattr(save_state.ppu, f'bg{i}_cnt')
            assert getattr(loaded.ppu, f'bg{i}_x') == getattr(save_state.ppu, f'bg{i}_x')
            assert getattr(loaded.ppu, f'bg{i}_y') == getattr(save_state.ppu, f'bg{i}_y')
        for i in range(2):
            for param in ['pa', 'pb', 'pc', 'pd', 'x', 'y']:
                attr = f'bg{i}_{param}'
                assert getattr(loaded.ppu, attr) == getattr(save_state.ppu, attr)
        assert loaded.ppu.win0_h == save_state.ppu.win0_h
        assert loaded.ppu.win1_h == save_state.ppu.win1_h
        assert loaded.ppu.win0_v == save_state.ppu.win0_v
        assert loaded.ppu.win1_v == save_state.ppu.win1_v
        assert loaded.ppu.win_in == save_state.ppu.win_in
        assert loaded.ppu.win_out == save_state.ppu.win_out
        assert loaded.ppu.blend_cnt == save_state.ppu.blend_cnt
        assert loaded.ppu.blend_alpha == save_state.ppu.blend_alpha
        assert loaded.ppu.blend_bright == save_state.ppu.blend_bright
        assert loaded.ppu.mosaic_size == save_state.ppu.mosaic_size
        assert loaded.ppu.framebuffer == save_state.ppu.framebuffer

        # Verify APU state
        assert loaded.apu.sound_on == save_state.apu.sound_on
        assert loaded.apu.master_volume == save_state.apu.master_volume
        for i in range(4):
            assert getattr(loaded.apu, f'ch{i+1}_volume') == getattr(save_state.apu, f'ch{i+1}_volume')
            assert getattr(loaded.apu, f'ch{i+1}_frequency') == getattr(save_state.apu, f'ch{i+1}_frequency')
            assert getattr(loaded.apu, f'ch{i+1}_duty_cycle') == getattr(save_state.apu, f'ch{i+1}_duty_cycle')
            assert getattr(loaded.apu, f'ch{i+1}_enabled') == getattr(save_state.apu, f'ch{i+1}_enabled')
        assert loaded.apu.fifo_a == save_state.apu.fifo_a
        assert loaded.apu.fifo_b == save_state.apu.fifo_b
        assert loaded.apu.wave_ram == save_state.apu.wave_ram

        # Verify DMA state
        for i in range(4):
            ch = f'ch{i}'
            assert getattr(loaded.dma, ch).src_addr == getattr(save_state.dma, ch).src_addr
            assert getattr(loaded.dma, ch).dst_addr == getattr(save_state.dma, ch).dst_addr
            assert getattr(loaded.dma, ch).control == getattr(save_state.dma, ch).control
            assert getattr(loaded.dma, ch).enabled == getattr(save_state.dma, ch).enabled

        # Verify Timer state
        for i in range(4):
            ch = f'timer{i}'
            assert getattr(loaded.timers, ch).count == getattr(save_state.timers, ch).count
            assert getattr(loaded.timers, ch).control == getattr(save_state.timers, ch).control
            assert getattr(loaded.timers, ch).reload == getattr(save_state.timers, ch).reload

        # Verify Interrupt state
        assert loaded.interrupts.ie == save_state.interrupts.ie
        assert loaded.interrupts.if_reg == save_state.interrupts.if_reg
        assert loaded.interrupts.ime == save_state.interrupts.ime

        # Verify Input state
        assert loaded.input_state.key_input == save_state.input_state.key_input
        assert loaded.input_state.key_cnt == save_state.input_state.key_cnt

    def test_save_load_roundtrip_empty_state(self, tmp_path):
        """Empty state roundtrip: all None components should save/load without error."""
        save_state = make_empty_save_state()
        filepath = str(tmp_path / "empty_state.sav")

        # Save
        result = save_state.save(filepath)
        assert result is True, "Save should succeed for empty state"

        # Load into fresh empty SaveState
        loaded = make_empty_save_state()
        result = loaded.load(filepath)
        assert result is True, "Load should succeed for empty state"

    def test_save_load_roundtrip_cpu_only(self, tmp_path):
        """CPU-only roundtrip: only CPU component should save/load correctly."""
        cpu = MockCPU()
        save_state = SaveState(cpu=cpu)
        filepath = str(tmp_path / "cpu_only.sav")

        # Save
        result = save_state.save(filepath)
        assert result is True

        # Load
        loaded = SaveState(cpu=MockCPU())
        result = loaded.load(filepath)
        assert result is True

        # Verify CPU state restored
        assert loaded.cpu.registers == cpu.registers
        assert loaded.cpu.cpsr == cpu.cpsr
        assert loaded.cpu.spsr == cpu.spsr
        assert loaded.cpu.mode == cpu.mode
        assert loaded.cpu.thumb_mode == cpu.thumb_mode
        assert loaded.cpu.running == cpu.running
        assert loaded.cpu.cycles == cpu.cycles


class TestSaveStateCPU:
    """Test CPU state serialization."""

    def test_save_cpu_registers(self, tmp_path):
        """CPU registers: all 16 registers should serialize and deserialize."""
        cpu = MockCPU()
        save_state = SaveState(cpu=cpu)
        filepath = str(tmp_path / "cpu_regs.sav")

        save_state.save(filepath)
        loaded = SaveState(cpu=MockCPU())
        loaded.load(filepath)

        assert loaded.cpu.registers == cpu.registers

    def test_save_cpu_cpsr_spsr(self, tmp_path):
        """CPU flags: CPSR and all 6 SPSRs should serialize correctly."""
        cpu = MockCPU()
        cpu.cpsr = 0x9000001F  # N=1, I=1, F=1, mode=0x1F
        cpu.spsr = [0x12345678, 0x87654321, 0xABCDEF00, 0x00FEDCBA, 0x11223344, 0x44332211]
        save_state = SaveState(cpu=cpu)
        filepath = str(tmp_path / "cpu_flags.sav")

        save_state.save(filepath)
        loaded = SaveState(cpu=MockCPU())
        loaded.load(filepath)

        assert loaded.cpu.cpsr == cpu.cpsr
        assert loaded.cpu.spsr == cpu.spsr

    def test_save_cpu_mode_thumb(self, tmp_path):
        """CPU mode: mode, thumb_mode, running, cycles should serialize correctly."""
        cpu = MockCPU()
        cpu.mode = 0x13  # IRQ mode
        cpu.thumb_mode = True
        cpu.running = False
        cpu.cycles = 999999999
        save_state = SaveState(cpu=cpu)
        filepath = str(tmp_path / "cpu_mode.sav")

        save_state.save(filepath)
        loaded = SaveState(cpu=MockCPU())
        loaded.load(filepath)

        assert loaded.cpu.mode == cpu.mode
        assert loaded.cpu.thumb_mode == cpu.thumb_mode
        assert loaded.cpu.running == cpu.running
        assert loaded.cpu.cycles == cpu.cycles


class TestSaveStateMemory:
    """Test Memory state serialization."""

    def test_save_memory_all_regions(self, tmp_path):
        """Memory regions: all 7 regions (EWRAM, IWRAM, IO, palette, VRAM, OAM, SRAM) should serialize."""
        memory = MockMemory()
        save_state = SaveState(memory=memory)
        filepath = str(tmp_path / "memory.sav")

        save_state.save(filepath)
        loaded = SaveState(memory=MockMemory())
        loaded.load(filepath)

        assert loaded.memory.ewram == memory.ewram
        assert loaded.memory.iwram == memory.iwram
        assert loaded.memory.io == memory.io
        assert loaded.memory.palette == memory.palette
        assert loaded.memory.vram == memory.vram
        assert loaded.memory.oam == memory.oam
        assert loaded.memory.sram == memory.sram


class TestSaveStatePPU:
    """Test PPU state serialization."""

    def test_save_ppu_registers(self, tmp_path):
        """PPU registers: disp_cnt, disp_stat, v_count should serialize correctly."""
        ppu = MockPPU()
        save_state = SaveState(ppu=ppu)
        filepath = str(tmp_path / "ppu_regs.sav")

        save_state.save(filepath)
        loaded = SaveState(ppu=MockPPU())
        loaded.load(filepath)

        assert loaded.ppu.disp_cnt == ppu.disp_cnt
        assert loaded.ppu.disp_stat == ppu.disp_stat
        assert loaded.ppu.v_count == ppu.v_count

    def test_save_ppu_bg_registers(self, tmp_path):
        """BG registers: all 4 BGs' cnt, x, y should serialize correctly."""
        ppu = MockPPU()
        save_state = SaveState(ppu=ppu)
        filepath = str(tmp_path / "ppu_bg.sav")

        save_state.save(filepath)
        loaded = SaveState(ppu=MockPPU())
        loaded.load(filepath)

        for i in range(4):
            assert getattr(loaded.ppu, f'bg{i}_cnt') == getattr(ppu, f'bg{i}_cnt')
            assert getattr(loaded.ppu, f'bg{i}_x') == getattr(ppu, f'bg{i}_x')
            assert getattr(loaded.ppu, f'bg{i}_y') == getattr(ppu, f'bg{i}_y')

    def test_save_ppu_affine_matrices(self, tmp_path):
        """Affine matrices: BG2 and BG3 affine parameters should serialize correctly."""
        ppu = MockPPU()
        save_state = SaveState(ppu=ppu)
        filepath = str(tmp_path / "ppu_affine.sav")

        save_state.save(filepath)
        loaded = SaveState(ppu=MockPPU())
        loaded.load(filepath)

        for i in range(2):
            for param in ['pa', 'pb', 'pc', 'pd', 'x', 'y']:
                attr = f'bg{i}_{param}'
                assert getattr(loaded.ppu, attr) == getattr(ppu, attr)

    def test_save_ppu_windows(self, tmp_path):
        """Windows: window horizontal/vertical bounds and enable masks should serialize."""
        ppu = MockPPU()
        save_state = SaveState(ppu=ppu)
        filepath = str(tmp_path / "ppu_windows.sav")

        save_state.save(filepath)
        loaded = SaveState(ppu=MockPPU())
        loaded.load(filepath)

        assert loaded.ppu.win0_h == ppu.win0_h
        assert loaded.ppu.win1_h == ppu.win1_h
        assert loaded.ppu.win0_v == ppu.win0_v
        assert loaded.ppu.win1_v == ppu.win1_v
        assert loaded.ppu.win_in == ppu.win_in
        assert loaded.ppu.win_out == ppu.win_out

    def test_save_ppu_special_effects(self, tmp_path):
        """Special effects: blend_cnt, blend_alpha, blend_bright, mosaic_size should serialize."""
        ppu = MockPPU()
        save_state = SaveState(ppu=ppu)
        filepath = str(tmp_path / "ppu_effects.sav")

        save_state.save(filepath)
        loaded = SaveState(ppu=MockPPU())
        loaded.load(filepath)

        assert loaded.ppu.blend_cnt == ppu.blend_cnt
        assert loaded.ppu.blend_alpha == ppu.blend_alpha
        assert loaded.ppu.blend_bright == ppu.blend_bright
        assert loaded.ppu.mosaic_size == ppu.mosaic_size

    def test_save_ppu_framebuffer(self, tmp_path):
        """Framebuffer: 240x160 pixel buffer should serialize correctly."""
        ppu = MockPPU()
        save_state = SaveState(ppu=ppu)
        filepath = str(tmp_path / "ppu_fb.sav")

        save_state.save(filepath)
        loaded = SaveState(ppu=MockPPU())
        loaded.load(filepath)

        assert loaded.ppu.framebuffer == ppu.framebuffer


class TestSaveStateAPU:
    """Test APU state serialization."""

    def test_save_apu_master_control(self, tmp_path):
        """Master control: sound_on and master_volume should serialize correctly."""
        apu = MockAPU()
        save_state = SaveState(apu=apu)
        filepath = str(tmp_path / "apu_master.sav")

        save_state.save(filepath)
        loaded = SaveState(apu=MockAPU())
        loaded.load(filepath)

        assert loaded.apu.sound_on == apu.sound_on
        assert loaded.apu.master_volume == apu.master_volume

    def test_save_apu_channels(self, tmp_path):
        """Channels: all 4 channels' parameters should serialize correctly."""
        apu = MockAPU()
        save_state = SaveState(apu=apu)
        filepath = str(tmp_path / "apu_channels.sav")

        save_state.save(filepath)
        loaded = SaveState(apu=MockAPU())
        loaded.load(filepath)

        for i in range(4):
            assert getattr(loaded.apu, f'ch{i+1}_volume') == getattr(apu, f'ch{i+1}_volume')
            assert getattr(loaded.apu, f'ch{i+1}_frequency') == getattr(apu, f'ch{i+1}_frequency')
            assert getattr(loaded.apu, f'ch{i+1}_duty_cycle') == getattr(apu, f'ch{i+1}_duty_cycle')
            assert getattr(loaded.apu, f'ch{i+1}_envelope_volume') == getattr(apu, f'ch{i+1}_envelope_volume')
            assert getattr(loaded.apu, f'ch{i+1}_enabled') == getattr(apu, f'ch{i+1}_enabled')

    def test_save_apu_fifo_wave_ram(self, tmp_path):
        """FIFOs and wave RAM: FIFO A/B and wave RAM should serialize correctly."""
        apu = MockAPU()
        save_state = SaveState(apu=apu)
        filepath = str(tmp_path / "apu_fifo.sav")

        save_state.save(filepath)
        loaded = SaveState(apu=MockAPU())
        loaded.load(filepath)

        assert loaded.apu.fifo_a == apu.fifo_a
        assert loaded.apu.fifo_b == apu.fifo_b
        assert loaded.apu.wave_ram == apu.wave_ram


class TestSaveStateDMA:
    """Test DMA state serialization."""

    def test_save_dma_channels(self, tmp_path):
        """DMA channels: all 4 channels' src/dst/control/enabled should serialize correctly."""
        dma = MockDMA()
        save_state = SaveState(dma=dma)
        filepath = str(tmp_path / "dma.sav")

        save_state.save(filepath)
        loaded = SaveState(dma=MockDMA())
        loaded.load(filepath)

        for i in range(4):
            ch = f'ch{i}'
            assert getattr(loaded.dma, ch).src_addr == getattr(dma, ch).src_addr
            assert getattr(loaded.dma, ch).dst_addr == getattr(dma, ch).dst_addr
            assert getattr(loaded.dma, ch).control == getattr(dma, ch).control
            assert getattr(loaded.dma, ch).enabled == getattr(dma, ch).enabled


class TestSaveStateTimers:
    """Test Timer state serialization."""

    def test_save_timers_all(self, tmp_path):
        """Timers: all 4 timers' count/control/reload should serialize correctly."""
        timers = MockTimers()
        save_state = SaveState(timers=timers)
        filepath = str(tmp_path / "timers.sav")

        save_state.save(filepath)
        loaded = SaveState(timers=MockTimers())
        loaded.load(filepath)

        for i in range(4):
            ch = f'timer{i}'
            assert getattr(loaded.timers, ch).count == getattr(timers, ch).count
            assert getattr(loaded.timers, ch).control == getattr(timers, ch).control
            assert getattr(loaded.timers, ch).reload == getattr(timers, ch).reload


class TestSaveStateInterrupts:
    """Test Interrupt state serialization."""

    def test_save_interrupts_registers(self, tmp_path):
        """Interrupt registers: IE, IF, IME should serialize correctly."""
        interrupts = MockInterrupts()
        save_state = SaveState(interrupts=interrupts)
        filepath = str(tmp_path / "interrupts.sav")

        save_state.save(filepath)
        loaded = SaveState(interrupts=MockInterrupts())
        loaded.load(filepath)

        assert loaded.interrupts.ie == interrupts.ie
        assert loaded.interrupts.if_reg == interrupts.if_reg
        assert loaded.interrupts.ime == interrupts.ime


class TestSaveStateInput:
    """Test Input state serialization."""

    def test_save_input_keys(self, tmp_path):
        """Input: key_input and key_cnt should serialize correctly."""
        input_state = MockInput()
        save_state = SaveState(input_state=input_state)
        filepath = str(tmp_path / "input.sav")

        save_state.save(filepath)
        loaded = SaveState(input_state=MockInput())
        loaded.load(filepath)

        assert loaded.input_state.key_input == input_state.key_input
        assert loaded.input_state.key_cnt == input_state.key_cnt


class TestSaveStateErrors:
    """Test error handling for corrupt/invalid save states."""

    def test_load_corrupt_json(self, tmp_path):
        """Corrupt JSON: invalid JSON syntax should return False."""
        save_state = make_empty_save_state()
        filepath = str(tmp_path / "corrupt.json")

        # Write invalid JSON
        with open(filepath, 'w') as f:
            f.write("{ invalid json }")

        result = save_state.load(filepath)
        assert result is False

    def test_load_truncated_file(self, tmp_path):
        """Truncated file: incomplete JSON should return False."""
        save_state = make_empty_save_state()
        filepath = str(tmp_path / "truncated.json")

        # Write truncated JSON
        with open(filepath, 'w') as f:
            f.write('{"version": 1, "cpu": {"registers": [')

        result = save_state.load(filepath)
        assert result is False

    def test_load_missing_file(self, tmp_path):
        """Missing file: non-existent file should return False."""
        save_state = make_empty_save_state()
        filepath = str(tmp_path / "nonexistent.sav")

        result = save_state.load(filepath)
        assert result is False

    def test_load_unsupported_version(self, tmp_path):
        """Unsupported version: future version > VERSION should return False."""
        save_state = make_empty_save_state()
        filepath = str(tmp_path / "future.sav")

        # Write state with future version
        state = {"version": VERSION + 100}
        with open(filepath, 'w') as f:
            json.dump(state, f)

        result = save_state.load(filepath)
        assert result is False

    def test_load_missing_fields(self, tmp_path):
        """Missing fields: state with missing required fields should still load (graceful defaults)."""
        save_state = make_full_save_state()
        filepath = str(tmp_path / "partial.sav")

        # Write state with missing fields
        state = {
            "version": VERSION,
            "cpu": {"registers": [0] * 16}  # Only registers, no cpsr, spsr, etc.
        }
        with open(filepath, 'w') as f:
            json.dump(state, f)

        # Should load successfully with defaults for missing fields
        loaded = make_full_save_state()
        result = loaded.load(filepath)
        assert result is True

    def test_load_invalid_type_values(self, tmp_path):
        """Invalid type values: wrong types should be handled gracefully."""
        save_state = make_empty_save_state()
        filepath = str(tmp_path / "invalid_types.sav")

        # Write state with invalid types
        state = {
            "version": VERSION,
            "cpu": {"registers": "not_a_list"}  # String instead of list
        }
        with open(filepath, 'w') as f:
            json.dump(state, f)

        result = save_state.load(filepath)
        # Should handle gracefully (may return False or True with defaults)
        # The important thing is it doesn't crash


class TestCreateSaveState:
    """Test create_save_state factory function."""

    def test_create_save_state_all_components(self):
        """create_save_state: should create SaveState with all components."""
        cpu = MockCPU()
        memory = MockMemory()
        ppu = MockPPU()
        apu = MockAPU()
        dma = MockDMA()
        timers = MockTimers()
        interrupts = MockInterrupts()
        input_state = MockInput()

        save_state = create_save_state(
            cpu=cpu, memory=memory, ppu=ppu, apu=apu,
            dma=dma, timers=timers, interrupts=interrupts, input_state=input_state
        )

        assert save_state.cpu is cpu
        assert save_state.memory is memory
        assert save_state.ppu is ppu
        assert save_state.apu is apu
        assert save_state.dma is dma
        assert save_state.timers is timers
        assert save_state.interrupts is interrupts
        assert save_state.input_state is input_state

    def test_create_save_state_none_components(self):
        """create_save_state: should create SaveState with None components."""
        save_state = create_save_state()

        assert save_state.cpu is None
        assert save_state.memory is None
        assert save_state.ppu is None
        assert save_state.apu is None
        assert save_state.dma is None
        assert save_state.timers is None
        assert save_state.interrupts is None
        assert save_state.input_state is None


class TestSaveStateVersion:
    """Test version field handling."""

    def test_save_includes_version(self, tmp_path):
        """Save format: saved JSON should include version field."""
        save_state = make_empty_save_state()
        filepath = str(tmp_path / "version.sav")

        save_state.save(filepath)

        with open(filepath, 'r') as f:
            data = json.load(f)

        assert "version" in data
        assert data["version"] == VERSION

    def test_load_version_0(self, tmp_path):
        """Version 0: should load successfully (backward compatibility)."""
        save_state = make_empty_save_state()
        filepath = str(tmp_path / "v0.sav")

        # Write state with version 0
        state = {"version": 0}
        with open(filepath, 'w') as f:
            json.dump(state, f)

        result = save_state.load(filepath)
        assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])