"""GBA Runtime - Python implementation of GBA hardware.

This package marker exists for development/test discovery. The runtime
modules are designed to be inlined into transpiled output by the codegen,
not imported as a package. Internal modules use absolute imports
(e.g. ``from bios import BIOS``) which work when inlined but not when
imported as a subpackage.
"""
