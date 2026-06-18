"""
Hook Manager for GBAtoPy - Python-native debugging and tracing system.

Provides zero-overhead hooks for:
- Instruction execution tracing
- Memory read/write monitoring
- Frame callbacks
- Breakpoints
"""

from typing import Callable, Dict, List, Set, Optional


class HookManager:
    """
    Manages debugging hooks and callbacks for the GBA emulator.
    
    All hook types support zero-overhead operation when no hooks are registered.
    """
    
    def __init__(self):
        self._instruction_hooks: Dict[int, Callable[[int], None]] = {}
        self._write_hooks: Dict[int, Callable[[int, int], None]] = {}
        self._read_hooks: Dict[int, Callable[[int], int]] = {}
        self._frame_hooks: List[Callable[[int], None]] = []
        self._breakpoints: Set[int] = set()
        self._step_mode: bool = False
        
        # Fast-path flag - updated when hooks are added/removed
        self._has_any_hooks: bool = False
    
    def on_instruction(self, addr: int, callback: Callable[[int], None]) -> None:
        """
        Register a callback for instruction execution at a specific address.
        
        Args:
            addr: Instruction address (PC value) to hook
            callback: Function called with the PC address when instruction executes
        """
        self._instruction_hooks[addr] = callback
        self._has_any_hooks = True
    
    def on_write(self, addr: int, callback: Callable[[int, int], None]) -> None:
        """
        Register a callback for memory writes to a specific address.
        
        Args:
            addr: Memory address to watch for writes
            callback: Function called with (address, value) on write
        """
        self._write_hooks[addr] = callback
        self._has_any_hooks = True
    
    def on_read(self, addr: int, callback: Callable[[int], int]) -> None:
        """
        Register a callback for memory reads from a specific address.
        
        Args:
            addr: Memory address to watch for reads
            callback: Function called with address, returns value to use
        """
        self._read_hooks[addr] = callback
        self._has_any_hooks = True
    
    def on_frame(self, callback: Callable[[int], None]) -> None:
        """
        Register a callback for each rendered frame.
        
        Args:
            callback: Function called with frame number after each render
        """
        self._frame_hooks.append(callback)
        self._has_any_hooks = True
    
    def add_breakpoint(self, addr: int) -> None:
        """
        Add a breakpoint at the specified address.
        
        When execution reaches this address, the emulator will pause.
        
        Args:
            addr: Address where execution should pause
        """
        self._breakpoints.add(addr)
        self._has_any_hooks = True
    
    def remove_breakpoint(self, addr: int) -> None:
        """
        Remove a breakpoint from the specified address.
        
        Args:
            addr: Address to remove breakpoint from
        """
        self._breakpoints.discard(addr)
        # Check if any hooks remain
        self._has_any_hooks = bool(
            self._instruction_hooks or
            self._write_hooks or
            self._read_hooks or
            self._frame_hooks or
            self._breakpoints or
            self._step_mode
        )
    
    def enable_step_mode(self, enabled: bool = True) -> None:
        """
        Enable or disable single-step execution mode.
        
        When enabled, execution pauses after every instruction.
        
        Args:
            enabled: True to enable step mode, False to disable
        """
        self._step_mode = enabled
        self._has_any_hooks = enabled or bool(
            self._instruction_hooks or
            self._write_hooks or
            self._read_hooks or
            self._frame_hooks or
            self._breakpoints
        )
    
    def check_hooks(self, pc: int, event_type: str) -> Optional[bool]:
        """
        Check and execute hooks for the current execution state.
        
        Args:
            pc: Current program counter value
            event_type: Type of event ('instruction', 'write', 'read', 'frame')
            
        Returns:
            True if execution should pause (breakpoint hit), None otherwise
        """
        # Check for breakpoint
        if pc in self._breakpoints:
            print(f"\n[BREAKPOINT] PC=0x{pc:08X}")
            return True
        
        # Check instruction hooks
        if event_type == 'instruction' and pc in self._instruction_hooks:
            self._instruction_hooks[pc](pc)
        
        # Step mode - pause after every instruction
        if self._step_mode:
            print(f"[STEP] PC=0x{pc:08X}")
            return True
        
        return None
    
    def check_write_hook(self, addr: int, value: int) -> None:
        """
        Check and execute write hooks for a memory write.
        
        Args:
            addr: Memory address being written
            value: Value being written
        """
        if addr in self._write_hooks:
            self._write_hooks[addr](addr, value)
    
    def check_read_hook(self, addr: int) -> Optional[int]:
        """
        Check and execute read hooks for a memory read.
        
        Args:
            addr: Memory address being read
            
        Returns:
            Value from hook if registered, None otherwise
        """
        if addr in self._read_hooks:
            return self._read_hooks[addr](addr)
        return None
    
    def notify_frame(self, frame_num: int) -> None:
        """
        Notify all frame hooks of a new frame.
        
        Args:
            frame_num: Current frame number
        """
        for callback in self._frame_hooks:
            callback(frame_num)
    
    def has_hooks(self) -> bool:
        """
        Fast check if any hooks are registered.
        
        Returns:
            True if any hooks exist, False otherwise (zero-overhead path)
        """
        return self._has_any_hooks
    
    def clear_all(self) -> None:
        """Remove all registered hooks and breakpoints."""
        self._instruction_hooks.clear()
        self._write_hooks.clear()
        self._read_hooks.clear()
        self._frame_hooks.clear()
        self._breakpoints.clear()
        self._step_mode = False
        self._has_any_hooks = False
    
    def list_breakpoints(self) -> List[int]:
        """
        Get list of all breakpoint addresses.
        
        Returns:
            Sorted list of breakpoint addresses
        """
        return sorted(self._breakpoints)
    
    def __repr__(self) -> str:
        return (
            f"HookManager(instructions={len(self._instruction_hooks)}, "
            f"writes={len(self._write_hooks)}, reads={len(self._read_hooks)}, "
            f"frames={len(self._frame_hooks)}, breakpoints={len(self._breakpoints)}, "
            f"step_mode={self._step_mode})"
        )
