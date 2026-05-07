#!/usr/bin/env python3
import os
from gba_runtime.ppu import PPU


def capture_screenshot_from_ppu(ppu, output_path="/tmp/python_screenshot.png"):
    try:
        ppu.render_frame()
        ppu.save_screenshot(output_path)
        return True
    except Exception as e:
        import sys

        print(f"Screenshot error: {e}", file=sys.stderr)
        return False


def get_capture_output_path():
    return os.environ.get("GBA_CAPTURE_SCREENSHOT")


def auto_capture_screenshot(ppu):
    output_path = get_capture_output_path()
    if output_path:
        capture_screenshot_from_ppu(ppu, output_path)
