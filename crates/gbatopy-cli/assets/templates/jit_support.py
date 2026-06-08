# === Numba JIT Support (optional) ===
# Install with: pip install numba

try:
    from numba import njit, prange
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    
    # Fallback decorators when numba is not available
    def njit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    
    prange = range


def apply_jit_to_cpu(cpu_class):
    """Apply JIT compilation to CPU methods if numba is available."""
    if not NUMBA_AVAILABLE:
        return cpu_class
    
    # List of CPU methods to JIT-compile
    jit_methods = [
        'execute_instruction',
        'execute_thumb_instruction',
        'add', 'sub', 'and_', 'or_', 'eor', 'bic', 'mov', 'cmp',
        'ldr', 'str', 'ldrh', 'strh', 'ldrb', 'strb',
        'ldr_sh', 'str_sh', 'ldr_sb', 'str_sb'
    ]
    
    for method_name in jit_methods:
        if hasattr(cpu_class, method_name):
            method = getattr(cpu_class, method_name)
            decorated = njit()(method)
            setattr(cpu_class, method_name, decorated)
    
    return cpu_class
