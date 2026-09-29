# Ghidra script: list all discovered functions
# @category GBAtoPy
# @runtime PyGhidra

from ghidra.program.model.listing import FunctionIterator

fns = currentProgram.getListing().getFunctions(True)
for f in fns:
    print("FUNC %s 0x%08X" % (f.getName(), f.getEntryPoint().getOffset()))