#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import shutil
import tempfile
from pathlib import Path

from PIL import Image

FRAMES = [1, 10, 20, 30]
THRESHOLD = 95.0
TOLERANCE = 10

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_MGBA = PROJECT_ROOT / "mgba" / "build" / "sdl" / "mgba"
LUA_SCRIPT = SCRIPT_DIR / "screenshot.lua"


def check_mgba():
    mgba = Path(os.environ.get("MGBA", DEFAULT_MGBA))
    if not mgba.exists():
        print(f"Warning: mGBA not found at {mgba}")
        print("Set MGBA env var or build mGBA first (see README)")
        return None
    return mgba


def capture_mgba_golden(rom_path: Path, output_dir: Path, mgba: Path):
    lua_content = f'''local targetFrames = {{{", ".join(str(f) for f in FRAMES)}}}
local name = "{output_dir}/golden_frame"
local frameIdx = 1

local function onFrame()
    local current = emu:currentFrame()
    if frameIdx > #targetFrames then
        os.exit(0)
    end
    if current >= targetFrames[frameIdx] then
        emu:screenshot(name .. "_" .. targetFrames[frameIdx] .. ".png")
        print("Frame " .. targetFrames[frameIdx])
        frameIdx = frameIdx + 1
        if frameIdx > #targetFrames then
            os.exit(0)
        end
    end
end

callbacks:add("frame", onFrame)
'''

    lua_temp = Path(tempfile.gettempdir()) / f"golden_{rom_path.stem}.lua"
    lua_temp.write_text(lua_content)

    print(f"  Running mGBA...")
    result = subprocess.run(
        [str(mgba), "--script", str(lua_temp), str(rom_path)],
        capture_output=True, text=True, timeout=30
    )

    lua_temp.unlink(missing_ok=True)

    captured = [output_dir / f"golden_frame_{f}.png" for f in FRAMES]
    existing = [p for p in captured if p.exists()]
    return existing


def transpile_rom(rom_path: Path, output_path: Path):
    result = subprocess.run(
        ["cargo", "run", "-q", "-p", "gbatopy-cli", "--",
         "pipeline", "--rom", str(rom_path), "--output", str(output_path)],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        print(f"  Transpile failed: {result.stderr}")
        return False
    if not output_path.exists():
        print(f"  Transpiled file not created")
        return False
    print(f"  Transpiled: {output_path.name}")
    return True


def capture_transpiled(output_dir: Path, transpiled_path: Path, rom_stem: str):
    captured = []
    for frame in FRAMES:
        out = output_dir / f"transpiled_frame_{frame}.png"
        env = {**os.environ, "SDL_VIDEODRIVER": "dummy"}
        result = subprocess.run(
            ["python3", str(transpiled_path), "--headless",
             f"--frame={frame}", "--screenshot", str(out)],
            env=env, capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and out.exists():
            captured.append(out)
            print(f"    Frame {frame}: {out.name}")
        else:
            print(f"    Frame {frame}: FAILED")
    return captured


def compare_images(img1: Image.Image, img2: Image.Image):
    w = min(img1.width, img2.width)
    h = min(img1.height, img2.height)
    i1 = img1.resize((w, h), Image.NEAREST)
    i2 = img2.resize((w, h), Image.NEAREST)

    p1 = list(i1.getdata())
    p2 = list(i2.getdata())

    matching = sum(1 for a, b in zip(p1, p2)
                   if all(abs(ca - cb) <= TOLERANCE
                          for ca, cb in zip(a[:3], b[:3])))

    total = len(p1)
    pct = (matching / total) * 100 if total else 0

    diff = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dp = []
    for a, b in zip(p1, p2):
        if all(abs(ca - cb) <= TOLERANCE for ca, cb in zip(a[:3], b[:3])):
            dp.append((0, 0, 0, 0))
        else:
            dp.append((255, 0, 0, 255))
    diff.putdata(dp)

    return matching, pct, diff, (i1.size, i2.size)


def compare_rom(rom_path: Path, mgba: Path | None, keep: bool):
    name = rom_path.stem
    output_dir = Path(tempfile.gettempdir()) / f"gbatopy_compare_{name}"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    print(f"\n{'='*50}")
    print(f"ROM: {name}")
    print(f"{'='*50}")

    print(f"\n[1/3] Capturing golden screenshots...")
    golden = []
    if mgba:
        golden = capture_mgba_golden(rom_path, output_dir, mgba)
    if not golden:
        print(f"  No golden screenshots captured (mGBA unavailable?)")

    print(f"\n[2/3] Transpiling ROM...")
    transpiled_path = Path(tempfile.gettempdir()) / f"transpiled_{name}.py"
    if not transpile_rom(rom_path, transpiled_path):
        print(f"SKIP: {name}")
        if not keep:
            shutil.rmtree(output_dir)
        return

    print(f"\n[3/3] Running transpiled Python...")
    transpiled = capture_transpiled(output_dir, transpiled_path, name)
    if not transpiled:
        print(f"SKIP: {name} - no transpiled screenshots")
        if not keep:
            shutil.rmtree(output_dir)
        return

    print(f"\n{'='*50}")
    print(f"RESULTS: {name}")
    print(f"{'='*50}")

    results = []
    for frame in FRAMES:
        g = output_dir / f"golden_frame_{frame}.png"
        t = output_dir / f"transpiled_frame_{frame}.png"

        if not g.exists() or not t.exists():
            reason = "no golden" if not g.exists() else "no transpiled"
            print(f"  Frame {frame:>2}: SKIP ({reason})")
            continue

        gi = Image.open(g).convert("RGB")
        ti = Image.open(t).convert("RGB")
        match, pct, diff, sizes = compare_images(gi, ti)

        diff_path = output_dir / f"diff_frame_{frame}.png"
        diff.save(diff_path)

        status = "PASS" if pct >= THRESHOLD else "FAIL"
        results.append((frame, pct, status, sizes))
        gs = f"{gi.width}x{gi.height}"
        ts = f"{ti.width}x{ti.height}"
        print(f"  Frame {frame:>2}: {pct:>6.2f}%  {status}  (golden={gs} transpiled={ts})")

    passed = sum(1 for r in results if r[2] == "PASS")
    total = len(results)
    print(f"\n  Summary: {passed}/{total} frames passed")

    report = output_dir / "report.txt"
    report.write_text(
        f"ROM: {name}\n"
        f"Frames compared: {total}\n"
        f"Passed: {passed}\n"
        f"Threshold: {THRESHOLD}%\n"
        f"Tolerance: ±{TOLERANCE}\n"
        f"Overall: {'PASS' if passed == total > 0 else 'FAIL'}\n"
    )
    print(f"  Report: {report}")
    print(f"  Screenshots: {output_dir}/")

    if not keep:
        shutil.rmtree(output_dir)
        print(f"  (temp files cleaned up; use --keep to retain)")


def main():
    parser = argparse.ArgumentParser(
        description="Compare GBAtoPy screenshots against mGBA golden reference"
    )
    parser.add_argument("rom", help="Path to GBA ROM file")
    parser.add_argument("--mgba", default=str(DEFAULT_MGBA),
                        help="Path to mGBA binary")
    parser.add_argument("--keep", action="store_true",
                        help="Keep temp screenshot files")
    args = parser.parse_args()

    rom = Path(args.rom)
    if not rom.exists():
        print(f"Error: ROM not found: {rom}")
        sys.exit(1)

    mgba = Path(args.mgba)
    if not mgba.exists():
        print(f"Warning: mGBA not found at {mgba}, golden capture disabled")
        mgba = None

    compare_rom(rom, mgba, args.keep)


if __name__ == "__main__":
    main()
