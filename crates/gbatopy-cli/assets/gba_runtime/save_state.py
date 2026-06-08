"""Save State Support for GBAtoPy Transpiler

Provides serialization/deserialization of complete emulator state for save states.
Uses JSON format for human readability and version field for future compatibility.
"""

import json
import sys
from typing import Any, Dict, Optional

# Version for future compatibility
VERSION = 1


class SaveState:
    """Save State class for complete emulator state serialization.
    
    Provides save(filepath) and load(filepath) methods to serialize and deserialize
    the complete emulator state including CPU, Memory, PPU, APU, DMA, Timers,
    Interrupts, and Input state.
    """
    
    def __init__(self, cpu=None, memory=None, ppu=None, apu=None, 
                 dma=None, timers=None, interrupts=None, input_state=None):
        """Initialize SaveState with emulator component references.
        
        Args:
            cpu: ARM7TDMI CPU instance
            memory: Memory instance
            ppu: PPU instance
            apu: APU instance
            dma: DMA instance
            timers: Timers instance
            interrupts: InterruptController instance
            input_state: Input instance
        """
        self.cpu = cpu
        self.memory = memory
        self.ppu = ppu
        self.apu = apu
        self.dma = dma
        self.timers = timers
        self.interrupts = interrupts
        self.input_state = input_state
    
    def save(self, filepath: str) -> bool:
        """Save complete emulator state to JSON file.
        
        Args:
            filepath: Path to save file
            
        Returns:
            True on success, False on error
        """
        try:
            state = {
                "version": VERSION,
                "cpu": self._save_cpu(),
                "memory": self._save_memory(),
                "ppu": self._save_ppu(),
                "apu": self._save_apu(),
                "dma": self._save_dma(),
                "timers": self._save_timers(),
                "interrupts": self._save_interrupts(),
                "input": self._save_input()
            }
            
            with open(filepath, 'w') as f:
                json.dump(state, f, indent=2)
            
            return True
        except Exception as e:
            print(f"Error saving state: {e}", file=sys.stderr)
            return False
    
    def load(self, filepath: str) -> bool:
        """Load complete emulator state from JSON file.
        
        Args:
            filepath: Path to save file
            
        Returns:
            True on success, False on error
        """
        try:
            with open(filepath, 'r') as f:
                state = json.load(f)
            
            # Check version compatibility
            if state.get("version", 0) > VERSION:
                print(f"Warning: Save state version {state['version']} is newer than "
                      f"supported version {VERSION}", file=sys.stderr)
                return False
            
            # Restore all components
            if not self._load_cpu(state.get("cpu", {})):
                return False
            if not self._load_memory(state.get("memory", {})):
                return False
            if not self._load_ppu(state.get("ppu", {})):
                return False
            if not self._load_apu(state.get("apu", {})):
                return False
            if not self._load_dma(state.get("dma", {})):
                return False
            if not self._load_timers(state.get("timers", {})):
                return False
            if not self._load_interrupts(state.get("interrupts", {})):
                return False
            if not self._load_input(state.get("input", {})):
                return False
            
            return True
        except Exception as e:
            print(f"Error loading state: {e}", file=sys.stderr)
            return False
    
    # =========================================================================
    # CPU State
    # =========================================================================
    
    def _save_cpu(self) -> Dict[str, Any]:
        """Save CPU state."""
        if not self.cpu:
            return {}
        
        return {
            "registers": list(self.cpu.registers),  # r0-r15
            "cpsr": self.cpu.cpsr,
            "spsr": list(self.cpu.spsr),  # Saved PSR for each mode
            "mode": self.cpu.mode,
            "thumb_mode": self.cpu.thumb_mode,
            "running": self.cpu.running,
            "cycles": self.cpu.cycles
        }
    
    def _load_cpu(self, state: Dict[str, Any]) -> bool:
        """Load CPU state."""
        if not self.cpu or not state:
            return True
        
        try:
            self.cpu.registers = list(state.get("registers", [0] * 16))
            self.cpu.cpsr = state.get("cpsr", 0)
            self.cpu.spsr = list(state.get("spsr", [0] * 6))
            self.cpu.mode = state.get("mode", 0x1F)
            self.cpu.thumb_mode = state.get("thumb_mode", False)
            self.cpu.running = state.get("running", True)
            self.cpu.cycles = state.get("cycles", 0)
            return True
        except Exception as e:
            print(f"Error loading CPU state: {e}", file=sys.stderr)
            return False
    
    # =========================================================================
    # Memory State
    # =========================================================================
    
    def _save_memory(self) -> Dict[str, Any]:
        """Save Memory state."""
        if not self.memory:
            return {}
        
        return {
            "ewram": list(self.memory.ewram),
            "iwram": list(self.memory.iwram),
            "io": list(self.memory.io),
            "palette": list(self.memory.palette),
            "vram": list(self.memory.vram),
            "oam": list(self.memory.oam),
            "sram": list(self.memory.sram)
        }
    
    def _load_memory(self, state: Dict[str, Any]) -> bool:
        """Load Memory state."""
        if not self.memory or not state:
            return True
        
        try:
            # Convert lists back to bytearray for memory arrays
            ewram = state.get("ewram", [])
            if ewram:
                self.memory.ewram = list(ewram)
            
            iwram = state.get("iwram", [])
            if iwram:
                self.memory.iwram = list(iwram)
            
            io = state.get("io", [])
            if io:
                self.memory.io = list(io)
            
            palette = state.get("palette", [])
            if palette:
                self.memory.palette = list(palette)
            
            vram = state.get("vram", [])
            if vram:
                self.memory.vram = list(vram)
            
            oam = state.get("oam", [])
            if oam:
                self.memory.oam = list(oam)
            
            sram = state.get("sram", [])
            if sram:
                self.memory.sram = list(sram)
            
            return True
        except Exception as e:
            print(f"Error loading memory state: {e}", file=sys.stderr)
            return False
    
    # =========================================================================
    # PPU State
    # =========================================================================
    
    def _save_ppu(self) -> Dict[str, Any]:
        """Save PPU state."""
        if not self.ppu:
            return {}
        
        state = {}
        
        # Save PPU registers
        if hasattr(self.ppu, 'disp_cnt'):
            state["disp_cnt"] = self.ppu.disp_cnt
        if hasattr(self.ppu, 'disp_stat'):
            state["disp_stat"] = self.ppu.disp_stat
        if hasattr(self.ppu, 'v_count'):
            state["v_count"] = self.ppu.v_count
        
        # Save BG registers
        for i in range(4):
            bg_prefix = f"bg{i}"
            if hasattr(self.ppu, f'{bg_prefix}_cnt'):
                state[f'bg{i}_cnt'] = getattr(self.ppu, f'{bg_prefix}_cnt')
            if hasattr(self.ppu, f'{bg_prefix}_x'):
                state[f'bg{i}_x'] = getattr(self.ppu, f'{bg_prefix}_x')
            if hasattr(self.ppu, f'{bg_prefix}_y'):
                state[f'bg{i}_y'] = getattr(self.ppu, f'{bg_prefix}_y')
        
        # Save affine matrix parameters
        for i in range(2):
            for param in ['pa', 'pb', 'pc', 'pd', 'x', 'y']:
                attr_name = f'bg{i}_{param}'
                if hasattr(self.ppu, attr_name):
                    state[attr_name] = getattr(self.ppu, attr_name)
        
        # Save window registers
        for i in range(2):
            for attr in ['win0_h', 'win1_h', 'win0_v', 'win1_v', 'win_in', 'win_out']:
                attr_name = f'{attr}{i}' if i > 0 and attr.endswith(str(i-1)) else attr
                if hasattr(self.ppu, attr_name):
                    state[attr_name] = getattr(self.ppu, attr_name)
        
        # Save special effects
        for attr in ['blend_cnt', 'blend_alpha', 'blend_bright']:
            if hasattr(self.ppu, attr):
                state[attr] = getattr(self.ppu, attr)
        
        # Save mosaic
        if hasattr(self.ppu, 'mosaic_size'):
            state["mosaic_size"] = self.ppu.mosaic_size
        
        # Save framebuffer if available
        if hasattr(self.ppu, 'framebuffer'):
            fb = self.ppu.framebuffer
            if fb:
                state["framebuffer"] = list(fb)
        
        return state
    
    def _load_ppu(self, state: Dict[str, Any]) -> bool:
        """Load PPU state."""
        if not self.ppu or not state:
            return True
        
        try:
            # Load PPU registers
            if "disp_cnt" in state and hasattr(self.ppu, 'disp_cnt'):
                self.ppu.disp_cnt = state["disp_cnt"]
            if "disp_stat" in state and hasattr(self.ppu, 'disp_stat'):
                self.ppu.disp_stat = state["disp_stat"]
            if "v_count" in state and hasattr(self.ppu, 'v_count'):
                self.ppu.v_count = state["v_count"]
            
            # Load BG registers
            for i in range(4):
                bg_prefix = f"bg{i}"
                if f'bg{i}_cnt' in state and hasattr(self.ppu, f'{bg_prefix}_cnt'):
                    setattr(self.ppu, f'{bg_prefix}_cnt', state[f'bg{i}_cnt'])
                if f'bg{i}_x' in state and hasattr(self.ppu, f'{bg_prefix}_x'):
                    setattr(self.ppu, f'{bg_prefix}_x', state[f'bg{i}_x'])
                if f'bg{i}_y' in state and hasattr(self.ppu, f'{bg_prefix}_y'):
                    setattr(self.ppu, f'{bg_prefix}_y', state[f'bg{i}_y'])
            
            # Load affine matrix parameters
            for i in range(2):
                for param in ['pa', 'pb', 'pc', 'pd', 'x', 'y']:
                    attr_name = f'bg{i}_{param}'
                    if attr_name in state and hasattr(self.ppu, attr_name):
                        setattr(self.ppu, attr_name, state[attr_name])
            
            # Load window registers
            for attr in ['win0_h', 'win1_h', 'win0_v', 'win1_v', 'win_in', 'win_out']:
                if attr in state and hasattr(self.ppu, attr):
                    setattr(self.ppu, attr, state[attr])
            
            # Load special effects
            for attr in ['blend_cnt', 'blend_alpha', 'blend_bright']:
                if attr in state and hasattr(self.ppu, attr):
                    setattr(self.ppu, attr, state[attr])
            
            # Load mosaic
            if "mosaic_size" in state and hasattr(self.ppu, 'mosaic_size'):
                self.ppu.mosaic_size = state["mosaic_size"]
            
            # Load framebuffer
            if "framebuffer" in state and hasattr(self.ppu, 'framebuffer'):
                fb_data = state["framebuffer"]
                if fb_data and self.ppu.framebuffer:
                    self.ppu.framebuffer = list(fb_data)
            
            return True
        except Exception as e:
            print(f"Error loading PPU state: {e}", file=sys.stderr)
            return False
    
    # =========================================================================
    # APU State
    # =========================================================================
    
    def _save_apu(self) -> Dict[str, Any]:
        """Save APU state."""
        if not self.apu:
            return {}
        
        state = {}
        
        # Save master control
        if hasattr(self.apu, 'sound_on'):
            state["sound_on"] = self.apu.sound_on
        
        # Save all 4 channels
        for i in range(4):
            ch_prefix = f"ch{i + 1}"
            if hasattr(self.apu, f'{ch_prefix}_volume'):
                state[f'ch{i+1}_volume'] = getattr(self.apu, f'{ch_prefix}_volume')
            if hasattr(self.apu, f'{ch_prefix}_frequency'):
                state[f'ch{i+1}_frequency'] = getattr(self.apu, f'{ch_prefix}_frequency')
            if hasattr(self.apu, f'{ch_prefix}_duty_cycle'):
                state[f'ch{i+1}_duty_cycle'] = getattr(self.apu, f'{ch_prefix}_duty_cycle')
            if hasattr(self.apu, f'{ch_prefix}_envelope_volume'):
                state[f'ch{i+1}_envelope_volume'] = getattr(self.apu, f'{ch_prefix}_envelope_volume')
            if hasattr(self.apu, f'{ch_prefix}_envelope_direction'):
                state[f'ch{i+1}_envelope_direction'] = getattr(self.apu, f'{ch_prefix}_envelope_direction')
            if hasattr(self.apu, f'{ch_prefix}_envelope_steps'):
                state[f'ch{i+1}_envelope_steps'] = getattr(self.apu, f'{ch_prefix}_envelope_steps')
            if hasattr(self.apu, f'{ch_prefix}_enabled'):
                state[f'ch{i+1}_enabled'] = getattr(self.apu, f'{ch_prefix}_enabled')
            if hasattr(self.apu, f'{ch_prefix}_wave'):
                state[f'ch{i+1}_wave'] = list(getattr(self.apu, f'{ch_prefix}_wave', []))
        
        # Save FIFO buffers
        for fifo in ['a', 'b']:
            if hasattr(self.apu, f'fifo_{fifo}'):
                state[f'fifo_{fifo}'] = list(getattr(self.apu, f'fifo_{fifo}', []))
        
        # Save wave RAM
        if hasattr(self.apu, 'wave_ram'):
            state["wave_ram"] = list(self.apu.wave_ram)
        
        # Save master volume
        if hasattr(self.apu, 'master_volume'):
            state["master_volume"] = self.apu.master_volume
        
        return state
    
    def _load_apu(self, state: Dict[str, Any]) -> bool:
        """Load APU state."""
        if not self.apu or not state:
            return True
        
        try:
            # Load master control
            if "sound_on" in state and hasattr(self.apu, 'sound_on'):
                self.apu.sound_on = state["sound_on"]
            
            # Load all 4 channels
            for i in range(4):
                ch_prefix = f"ch{i + 1}"
                if f'ch{i+1}_volume' in state and hasattr(self.apu, f'{ch_prefix}_volume'):
                    setattr(self.apu, f'{ch_prefix}_volume', state[f'ch{i+1}_volume'])
                if f'ch{i+1}_frequency' in state and hasattr(self.apu, f'{ch_prefix}_frequency'):
                    setattr(self.apu, f'{ch_prefix}_frequency', state[f'ch{i+1}_frequency'])
                if f'ch{i+1}_duty_cycle' in state and hasattr(self.apu, f'{ch_prefix}_duty_cycle'):
                    setattr(self.apu, f'{ch_prefix}_duty_cycle', state[f'ch{i+1}_duty_cycle'])
                if f'ch{i+1}_envelope_volume' in state and hasattr(self.apu, f'{ch_prefix}_envelope_volume'):
                    setattr(self.apu, f'{ch_prefix}_envelope_volume', state[f'ch{i+1}_envelope_volume'])
                if f'ch{i+1}_envelope_direction' in state and hasattr(self.apu, f'{ch_prefix}_envelope_direction'):
                    setattr(self.apu, f'{ch_prefix}_envelope_direction', state[f'ch{i+1}_envelope_direction'])
                if f'ch{i+1}_envelope_steps' in state and hasattr(self.apu, f'{ch_prefix}_envelope_steps'):
                    setattr(self.apu, f'{ch_prefix}_envelope_steps', state[f'ch{i+1}_envelope_steps'])
                if f'ch{i+1}_enabled' in state and hasattr(self.apu, f'{ch_prefix}_enabled'):
                    setattr(self.apu, f'{ch_prefix}_enabled', state[f'ch{i+1}_enabled'])
                if f'ch{i+1}_wave' in state and hasattr(self.apu, f'{ch_prefix}_wave'):
                    setattr(self.apu, f'{ch_prefix}_wave', list(state[f'ch{i+1}_wave']))
            
            # Load FIFO buffers
            for fifo in ['a', 'b']:
                if f'fifo_{fifo}' in state and hasattr(self.apu, f'fifo_{fifo}'):
                    setattr(self.apu, f'fifo_{fifo}', list(state[f'fifo_{fifo}']))
            
            # Load wave RAM
            if "wave_ram" in state and hasattr(self.apu, 'wave_ram'):
                self.apu.wave_ram = list(state["wave_ram"])
            
            # Load master volume
            if "master_volume" in state and hasattr(self.apu, 'master_volume'):
                self.apu.master_volume = state["master_volume"]
            
            return True
        except Exception as e:
            print(f"Error loading APU state: {e}", file=sys.stderr)
            return False
    
    # =========================================================================
    # DMA State
    # =========================================================================
    
    def _save_dma(self) -> Dict[str, Any]:
        """Save DMA state."""
        if not self.dma:
            return {}
        
        state = {}
        
        # Save all 4 DMA channels
        for i in range(4):
            ch = f"ch{i}"
            if hasattr(self.dma, ch):
                channel = getattr(self.dma, ch)
                if channel:
                    state[f'channel{i}'] = {
                        "src_addr": channel.src_addr if hasattr(channel, 'src_addr') else 0,
                        "dst_addr": channel.dst_addr if hasattr(channel, 'dst_addr') else 0,
                        "control": channel.control if hasattr(channel, 'control') else 0,
                        "enabled": channel.enabled if hasattr(channel, 'enabled') else False,
                    }
        
        return state
    
    def _load_dma(self, state: Dict[str, Any]) -> bool:
        """Load DMA state."""
        if not self.dma or not state:
            return True
        
        try:
            # Load all 4 DMA channels
            for i in range(4):
                ch = f"ch{i}"
                if hasattr(self.dma, ch):
                    channel = getattr(self.dma, ch)
                    if channel and f'channel{i}' in state:
                        ch_state = state[f'channel{i}']
                        if hasattr(channel, 'src_addr'):
                            channel.src_addr = ch_state.get("src_addr", 0)
                        if hasattr(channel, 'dst_addr'):
                            channel.dst_addr = ch_state.get("dst_addr", 0)
                        if hasattr(channel, 'control'):
                            channel.control = ch_state.get("control", 0)
                        if hasattr(channel, 'enabled'):
                            channel.enabled = ch_state.get("enabled", False)
            
            return True
        except Exception as e:
            print(f"Error loading DMA state: {e}", file=sys.stderr)
            return False
    
    # =========================================================================
    # Timer State
    # =========================================================================
    
    def _save_timers(self) -> Dict[str, Any]:
        """Save Timer state."""
        if not self.timers:
            return {}
        
        state = {}
        
        # Save all 4 timers
        for i in range(4):
            ch = f"timer{i}"
            if hasattr(self.timers, ch):
                timer = getattr(self.timers, ch)
                if timer:
                    state[f'timer{i}'] = {
                        "count": timer.count if hasattr(timer, 'count') else 0,
                        "control": timer.control if hasattr(timer, 'control') else 0,
                        "reload": timer.reload if hasattr(timer, 'reload') else 0,
                    }
        
        return state
    
    def _load_timers(self, state: Dict[str, Any]) -> bool:
        """Load Timer state."""
        if not self.timers or not state:
            return True
        
        try:
            # Load all 4 timers
            for i in range(4):
                ch = f"timer{i}"
                if hasattr(self.timers, ch):
                    timer = getattr(self.timers, ch)
                    if timer and f'timer{i}' in state:
                        timer_state = state[f'timer{i}']
                        if hasattr(timer, 'count'):
                            timer.count = timer_state.get("count", 0)
                        if hasattr(timer, 'control'):
                            timer.control = timer_state.get("control", 0)
                        if hasattr(timer, 'reload'):
                            timer.reload = timer_state.get("reload", 0)
            
            return True
        except Exception as e:
            print(f"Error loading timer state: {e}", file=sys.stderr)
            return False
    
    # =========================================================================
    # Interrupt State
    # =========================================================================
    
    def _save_interrupts(self) -> Dict[str, Any]:
        """Save Interrupt state."""
        if not self.interrupts:
            return {}
        
        state = {}
        
        # Save interrupt registers
        if hasattr(self.interrupts, 'ie'):
            state["ie"] = self.interrupts.ie
        if hasattr(self.interrupts, 'if_reg'):
            state["if"] = self.interrupts.if_reg
        if hasattr(self.interrupts, 'ime'):
            state["ime"] = self.interrupts.ime
        
        # Save pending flags
        if hasattr(self.interrupts, 'pending'):
            state["pending"] = self.interrupts.pending
        
        return state
    
    def _load_interrupts(self, state: Dict[str, Any]) -> bool:
        """Load Interrupt state."""
        if not self.interrupts or not state:
            return True
        
        try:
            # Load interrupt registers
            if "ie" in state and hasattr(self.interrupts, 'ie'):
                self.interrupts.ie = state["ie"]
            if "if" in state:
                if hasattr(self.interrupts, 'if_reg'):
                    self.interrupts.if_reg = state["if"]
            if "ime" in state and hasattr(self.interrupts, 'ime'):
                self.interrupts.ime = state["ime"]
            
            # Load pending flags
            if "pending" in state and hasattr(self.interrupts, 'pending'):
                self.interrupts.pending = state["pending"]
            
            return True
        except Exception as e:
            print(f"Error loading interrupt state: {e}", file=sys.stderr)
            return False
    
    # =========================================================================
    # Input State
    # =========================================================================
    
    def _save_input(self) -> Dict[str, Any]:
        """Save Input state."""
        if not self.input_state:
            return {}
        
        state = {}
        
        # Save key input
        if hasattr(self.input_state, 'key_input'):
            state["key_input"] = self.input_state.key_input
        elif hasattr(self.input_state, 'keys'):
            state["key_input"] = self.input_state.keys
        
        # Save key control
        if hasattr(self.input_state, 'key_cnt'):
            state["key_cnt"] = self.input_state.key_cnt
        
        return state
    
    def _load_input(self, state: Dict[str, Any]) -> bool:
        """Load Input state."""
        if not self.input_state or not state:
            return True
        
        try:
            # Load key input
            if "key_input" in state:
                if hasattr(self.input_state, 'key_input'):
                    self.input_state.key_input = state["key_input"]
                elif hasattr(self.input_state, 'keys'):
                    self.input_state.keys = state["key_input"]
            
            # Load key control
            if "key_cnt" in state and hasattr(self.input_state, 'key_cnt'):
                self.input_state.key_cnt = state["key_cnt"]
            
            return True
        except Exception as e:
            print(f"Error loading input state: {e}", file=sys.stderr)
            return False


def create_save_state(cpu=None, memory=None, ppu=None, apu=None,
                     dma=None, timers=None, interrupts=None, input_state=None) -> SaveState:
    """Create a SaveState instance with emulator component references.
    
    Convenience function to create a SaveState instance.
    
    Args:
        cpu: ARM7TDMI CPU instance
        memory: Memory instance
        ppu: PPU instance
        apu: APU instance
        dma: DMA instance
        timers: Timers instance
        interrupts: InterruptController instance
        input_state: Input instance
    
    Returns:
        SaveState instance
    """
    return SaveState(cpu, memory, ppu, apu, dma, timers, interrupts, input_state)