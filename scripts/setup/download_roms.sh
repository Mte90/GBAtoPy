#!/usr/bin/env bash
# combined-download.sh - Unified test ROM downloader & organizer for GBAtoPy
# Run from project root: bash scripts/setup/combined-download.sh
#
# Combines:
# - download_test_roms.sh (download logic)
# - organize_test_roms.sh (organize logic)
# - download_and_organize_roms.sh (legacy, superseded)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
TEST_ROMS_DIR="$PROJECT_ROOT/test_roms"
SOURCES_DIR="$TEST_ROMS_DIR/sources"
ROMS_DIR="$TEST_ROMS_DIR/roms"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== GBAtoPy Test ROM Downloader & Organizer ===${NC}"
echo "Downloading test ROMs to: $TEST_ROMS_DIR"
echo ""

# Create directories
mkdir -p "$TEST_ROMS_DIR" "$SOURCES_DIR" "$ROMS_DIR"
cd "$TEST_ROMS_DIR"

# Function to download and extract ZIP
download_zip() {
    local name=$1
    local url=$2
    local extract_dir=$3
    
    echo -e "${YELLOW}Downloading $name...${NC}"
    
    if [ -d "$extract_dir" ] && [ "$(ls -A "$extract_dir" 2>/dev/null)" ]; then
        echo -e "  ${GREEN}Already exists, skipping${NC}"
        return 0
    fi
    
    rm -rf "$extract_dir" *.zip 2>/dev/null || true
    
    if curl -L -o "${name}.zip" "$url" 2>&1 | tail -1; then
        if unzip -q "${name}.zip" 2>/dev/null; then
            echo -e "  ${GREEN}Extracted${NC}"
            # Copy ROMs to ROMS_DIR
            find "$extract_dir" -type f \( -name "*.gba" -o -name "*.gb" \) -exec cp {} "$ROMS_DIR/" \; 2>/dev/null || true
        else
            echo -e "  ${RED}Extraction failed${NC}"
            return 1
        fi
    else
        echo -e "  ${RED}Download failed${NC}"
        return 1
    fi
    
    rm -f "${name}.zip"
    return 0
}

# Function to clone git repos
clone_repo() {
    local name=$1
    local url=$2
    local extract_dir=$3
    
    echo -e "${YELLOW}Cloning $name...${NC}"
    
    if [ -d "$extract_dir" ] && [ "$(ls -A "$extract_dir" 2>/dev/null)" ]; then
        echo -e "  ${GREEN}Already exists, skipping${NC}"
        return 0
    fi
    
    rm -rf "$extract_dir" 2>/dev/null || true
    
    if git clone --depth 1 "$url" 2>&1 | tail -1; then
        echo -e "  ${GREEN}Cloned${NC}"
        # Copy ROMs to ROMS_DIR
        find "$extract_dir" -type f \( -name "*.gba" -o -name "*.gb" \) -exec cp {} "$ROMS_DIR/" \; 2>/dev/null || true
    else
        echo -e "  ${RED}Clone failed${NC}"
        return 1
    fi
}

# Custom ROMs (GBAtoPy team)
CUSTOM_ROMS=(
    "test_dma"
    "test_timer"
    "test_irq"
    "test_audio"
    "test_display"
    "test_bios_swi"
    "test_sprites"
)

echo -e "\n${YELLOW}=== Source Repositories ===${NC}"

# 1. jsmolka/gba-tests (Official test suite)
echo -e "\n${GREEN}[1/16] jsmolka/gba-tests${NC}"
download_zip "jsmolka-gba-tests" \
    "https://github.com/jsmolka/gba-tests/archive/refs/heads/master.zip" \
    "jsmolka-gba-tests" || echo -e "${RED}  Failed, continuing...${NC}"

# 2. FalseDiagonalTest (Keypad input)
echo -e "\n${GREEN}[2/16] FalseDiagonalTest${NC}"
download_zip "FalseDiagonalTest" \
    "https://github.com/whatobiplays/FalseDiagonalTest/archive/refs/heads/main.zip" \
    "FalseDiagonalTest" || echo -e "${RED}  Failed, continuing...${NC}"

# 3. gba-playground (RTC + Audio demos)
echo -e "\n${GREEN}[3/16] gba-playground${NC}"
download_zip "gba-playground" \
    "https://github.com/michelhe/gba-playground/archive/refs/heads/master.zip" \
    "gba-playground" || echo -e "${RED}  Failed, continuing...${NC}"

# 4. ARMWrestler GBA (Destoe)
echo -e "\n${GREEN}[4/16] ARMWrestler GBA${NC}"
download_zip "armwrestler-gba" \
    "https://github.com/destoer/armwrestler-gba-fixed/archive/refs/heads/master.zip" \
    "armwrestler-gba" || echo -e "${RED}  Failed, continuing...${NC}"

# 5. FuzzARM (Randomized tests)
echo -e "\n${GREEN}[5/16] FuzzARM${NC}"
download_zip "FuzzARM" \
    "https://github.com/DenSinH/FuzzARM/archive/refs/heads/master.zip" \
    "FuzzARM" || echo -e "${RED}  Failed, continuing...${NC}"

# 7. GBA-Test-Collection (LadyStarBreeze)
echo -e "\n${GREEN}[7/16] GBA-Test-Collection${NC}"
download_zip "GBA-Test-Collection" \
    "https://github.com/ladystarbreeze/GBA-Test-Collection/archive/refs/heads/main.zip" \
    "GBA-Test-Collection" || echo -e "${RED}  Failed, continuing...${NC}"

# 8. destoer/gba_tests (NEW - cond, DMA priority, ISR, timing)
echo -e "\n${GREEN}[8/16] destoer/gba_tests${NC}"
download_zip "destoer-gba_tests" \
    "https://github.com/destoer/gba_tests/archive/refs/heads/master.zip" \
    "destoer-gba_tests" || echo -e "${RED}  Failed, continuing...${NC}"

# 9. nataliethenerd/enhancedcontrolcheckerGBA (NEW - Input/Keypad)
echo -e "\n${GREEN}[9/16] enhancedcontrolcheckerGBA${NC}"
download_zip "enhancedcontrolcheckerGBA" \
    "https://github.com/nataliethenerd/enhancedcontrolcheckerGBA/archive/refs/heads/main.zip" \
    "enhancedcontrolcheckerGBA" || echo -e "${RED}  Failed, continuing...${NC}"

# 11. nba-emu/hw-test (CRITICAL - DMA, Timers, IRQ, PPU)
echo -e "\n${GREEN}[11/16] nba-emu/hw-test${NC}"
if [ -d "hw-test" ] && [ "$(ls -A hw-test 2>/dev/null)" ]; then
    echo -e "  ${GREEN}Already exists, skipping${NC}"
else
    rm -rf hw-test 2>/dev/null || true
    if git clone --depth 1 https://github.com/nba-emu/hw-test.git 2>&1 | tail -1; then
        echo -e "  ${GREEN}Cloned successfully${NC}"
        find "hw-test" -type f \( -name "*.gba" -o -name "*.gb" \) -exec cp {} "$ROMS_DIR/" \; 2>/dev/null || true
    else
        echo -e "  ${RED}Clone failed${NC}"
    fi
fi

# 13. gbadev-org/tonc (Sound demo source code)
echo -e "\n${GREEN}[13/16] gbadev-org/tonc (sound demo source)${NC}"
if [ -d "tonc" ] && [ "$(ls -A tonc 2>/dev/null)" ]; then
    echo -e "  ${GREEN}Already exists, skipping${NC}"
else
    rm -rf tonc 2>/dev/null || true
    if git clone --depth 1 https://github.com/gbadev-org/tonc.git 2>&1 | tail -1; then
        echo -e "  ${GREEN}Cloned successfully${NC}"
        echo -e "  ${YELLOW}Note: Sound demos require devkitARM to compile${NC}"
    else
        echo -e "  ${RED}Clone failed${NC}"
    fi
fi

# 14. mgba-emu/mgba (Reference - GB/GBC tests)
echo -e "\n${GREEN}[14/16] mgba-emu/mgba (GB/GBC reference)${NC}"
if [ -d "mgba" ] && [ "$(ls -A mgba 2>/dev/null)" ]; then
    echo -e "  ${GREEN}Already exists, skipping${NC}"
else
    rm -rf mgba 2>/dev/null || true
    if git clone --depth 1 https://github.com/mgba-emu/mgba.git 2>&1 | tail -1; then
        echo -e "  ${GREEN}Cloned successfully${NC}"
    else
        echo -e "  ${RED}Clone failed${NC}"
    fi
fi

# 15. velipso/gba-sound-demo (Audio demos - song, rates)
echo -e "\n${GREEN}[15/17] velipso/gba-sound-demo (audio demos)${NC}"
if [ -d "gba-sound-demo" ] && [ "$(ls -A gba-sound-demo 2>/dev/null)" ]; then
    echo -e "  ${GREEN}Already exists, skipping${NC}"
else
    rm -rf gba-sound-demo 2>/dev/null || true
    if git clone --depth 1 https://github.com/velipso/gba-sound-demo.git 2>&1 | tail -1; then
        echo -e "  ${GREEN}Cloned successfully${NC}"
        # Copy ROMs to ROMS_DIR
        for f in gba-sound-demo/song.gba gba-sound-demo/rates.gba; do
            if [ -f "$f" ]; then
                cp "$f" "$ROMS_DIR/"
                echo -e "  ${GREEN}Copied: $(basename $f)${NC}"
            fi
        done
        # Copy gvasm source files to SOURCES_DIR
        mkdir -p "$SOURCES_DIR/gba-sound-demo"
        for f in gba-sound-demo/*.gvasm; do
            if [ -f "$f" ]; then
                cp "$f" "$SOURCES_DIR/gba-sound-demo/"
                echo -e "  ${GREEN}Source: $(basename $f)${NC}"
            fi
        done
    else
        echo -e "  ${RED}Clone failed${NC}"
    fi
fi

# 16. nba-emu/NanoBoyAdvance (Test matrix)
echo -e "\n${GREEN}[16/17] nba-emu/NanoBoyAdvance (test matrix)${NC}"
if [ -d "nba-emu" ] && [ "$(ls -A nba-emu 2>/dev/null)" ]; then
    echo -e "  ${GREEN}Already exists, skipping${NC}"
else
    rm -rf nba-emu 2>/dev/null || true
    if git clone --depth 1 https://github.com/nba-emu/NanoBoyAdvance.git 2>&1 | tail -1; then
        echo -e "  ${GREEN}Cloned successfully${NC}"
    else
        echo -e "  ${RED}Clone failed${NC}"
    fi
fi

# 17. veikkos/gba-frame-test (Frame timing - frame drops and screen tearing)
# Tests GBA display frame timing: detects dropped frames and screen tearing.
# Useful for VBlank timing verification. License: Unlicense (public domain).
echo -e "\n${GREEN}[17/17] veikkos/gba-frame-test${NC}"
if [ -f "$ROMS_DIR/gba-frame-test.gba" ]; then
    echo -e "  ${GREEN}Already exists, skipping${NC}"
else
    if curl -L -o /tmp/gba-frame-test-v1.zip \
        "https://github.com/veikkos/gba-frame-test/releases/download/v1/gba-frame-test-v1.zip" 2>&1 | tail -1; then
        if unzip -q -o /tmp/gba-frame-test-v1.zip -d /tmp/gba-frame-test-extract 2>/dev/null; then
            find /tmp/gba-frame-test-extract -type f -name "*.gba" -exec cp {} "$ROMS_DIR/" \; 2>/dev/null || true
            echo -e "  ${GREEN}Extracted gba-frame-test.gba${NC}"
        else
            echo -e "  ${RED}Extraction failed${NC}"
        fi
        rm -rf /tmp/gba-frame-test-v1.zip /tmp/gba-frame-test-extract
    else
        echo -e "  ${RED}Download failed${NC}"
    fi
fi

# 18. emmabritton/gba_gbarcade (Arcade game collection - sprites, audio, backgrounds)
# Rust/AGB framework: Asteroids, Pipe Dream, Brick Break, Minesweeper, Space Invaders, Lights Out.
# License: MIT
echo -e "\n${GREEN}[18/26] emmabritton/gba_gbarcade${NC}"
if [ -f "$ROMS_DIR/gbarcade_gbarcade_v0.1.4.gba" ]; then
    echo -e "  ${GREEN}Already exists, skipping${NC}"
else
    if curl -L -o "$ROMS_DIR/gbarcade_gbarcade_v0.1.4.gba"         "https://github.com/emmabritton/gba_gbarcade/releases/download/v0.1.4/gbarcade_v0.1.4.gba" 2>&1 | tail -1; then
        echo -e "  ${GREEN}Downloaded gbarcade_gbarcade_v0.1.4.gba${NC}"
    else
        echo -e "  ${RED}Download failed${NC}"
    fi
fi

# 19. mick-schroeder/gba-cascade7 (Puzzle game - Drop7 clone, Butano engine)
# Tests sprites, backgrounds, audio. License: MIT
echo -e "\n${GREEN}[19/26] mick-schroeder/gba-cascade7${NC}"
if [ -f "$ROMS_DIR/cascade7.gba" ]; then
    echo -e "  ${GREEN}Already exists, skipping${NC}"
else
    if curl -L -o "$ROMS_DIR/cascade7.gba"         "https://github.com/mick-schroeder/gba-cascade7/releases/download/v1.0.0/CASCADE7.gba" 2>&1 | tail -1; then
        echo -e "  ${GREEN}Downloaded cascade7.gba${NC}"
    else
        echo -e "  ${RED}Download failed${NC}"
    fi
fi

# 20. JoeMatt/Proposal (Visual novel / dating sim demo)
# Tests sprites, text, audio. License: MIT
echo -e "\n${GREEN}[20/26] JoeMatt/Proposal${NC}"
if [ -f "$ROMS_DIR/proposal_proposal-demo.gba" ]; then
    echo -e "  ${GREEN}Already exists, skipping${NC}"
else
    if curl -L -o "$ROMS_DIR/proposal_proposal-demo.gba"         "https://github.com/JoeMatt/Proposal/releases/download/v1.0.0/proposal-demo.gba" 2>&1 | tail -1; then
        echo -e "  ${GREEN}Downloaded proposal_proposal-demo.gba${NC}"
    else
        echo -e "  ${RED}Download failed${NC}"
    fi
fi

# 21. evanbowman/blind-jump-portable (Action/adventure roguelike with link multiplayer)
# Tests sprites, procedural generation, audio, link cable. License: GPL-3.0 (GBA build)
echo -e "\n${GREEN}[21/26] evanbowman/blind-jump-portable${NC}"
if [ -f "$ROMS_DIR/blindjump_BlindJump.gba" ]; then
    echo -e "  ${GREEN}Already exists, skipping${NC}"
else
    echo -e "  ${YELLOW}Downloading latest BlindJump release...${NC}"
    LATEST_URL=$(curl -sL "https://api.github.com/repos/evanbowman/blind-jump-portable/releases/latest" | python3 -c "import sys,json; r=json.load(sys.stdin); assets=[a for a in r.get('assets',[]) if a['name'].lower().endswith('.gba')]; print(assets[0]['browser_download_url'] if assets else '')" 2>/dev/null)
    if [ -n "$LATEST_URL" ]; then
        curl -L -o "$ROMS_DIR/blindjump_BlindJump.gba" "$LATEST_URL" 2>&1 | tail -1
        echo -e "  ${GREEN}Downloaded blindjump_BlindJump.gba${NC}"
    else
        echo -e "  ${RED}Could not find .gba asset in latest release${NC}"
    fi
fi

# 22. evanbowman/skyland-beta (RTS game inspired by FTL)
# Tests sprites, backgrounds, audio, custom scripting. License: MPL-2.0
echo -e "\n${GREEN}[22/26] evanbowman/skyland-beta${NC}"
if [ -f "$ROMS_DIR/Skyland.gba" ]; then
    echo -e "  ${GREEN}Already exists, skipping${NC}"
else
    echo -e "  ${YELLOW}Downloading latest Skyland release...${NC}"
    LATEST_URL=$(curl -sL "https://api.github.com/repos/evanbowman/skyland-beta/releases/latest" | python3 -c "import sys,json; r=json.load(sys.stdin); assets=[a for a in r.get('assets',[]) if a['name'].lower().endswith('.gba')]; print(assets[0]['browser_download_url'] if assets else '')" 2>/dev/null)
    if [ -n "$LATEST_URL" ]; then
        curl -L -o "$ROMS_DIR/Skyland.gba" "$LATEST_URL" 2>&1 | tail -1
        echo -e "  ${GREEN}Downloaded Skyland.gba${NC}"
    else
        echo -e "  ${RED}Could not find .gba asset in latest release${NC}"
    fi
fi

# 23. CasualPokePlayer/gba-flash-speed-test (Flash save chip speed tests)
# Tests flash erase/program speed for various GBA cartridge save chips.
# Two variants: MB (memory bus) and ROM. License: unknown
echo -e "\n${GREEN}[23/26] CasualPokePlayer/gba-flash-speed-test${NC}"
if [ -f "$ROMS_DIR/FlashSpeedTestMB.gba" ] && [ -f "$ROMS_DIR/FlashSpeedTestROM.gba" ]; then
    echo -e "  ${GREEN}Already exists, skipping${NC}"
else
    echo -e "  ${YELLOW}Downloading latest flash-speed-test release...${NC}"
    LATEST_URLS=$(curl -sL "https://api.github.com/repos/CasualPokePlayer/gba-flash-speed-test/releases/latest" | python3 -c "import sys,json; r=json.load(sys.stdin); assets=[a for a in r.get('assets',[]) if a['name'].lower().endswith('.gba')]; [print(a['browser_download_url']) for a in assets]" 2>/dev/null)
    if [ -n "$LATEST_URLS" ]; then
        for url in $LATEST_URLS; do
            fname=$(basename "$url")
            if echo "$fname" | grep -qi "mb"; then
                curl -L -o "$ROMS_DIR/FlashSpeedTestMB.gba" "$url" 2>&1 | tail -1
            else
                curl -L -o "$ROMS_DIR/FlashSpeedTestROM.gba" "$url" 2>&1 | tail -1
            fi
        done
        echo -e "  ${GREEN}Downloaded flash speed test ROMs${NC}"
    else
        echo -e "  ${RED}Could not find .gba assets in latest release${NC}"
    fi
fi

# 24. bpcore_BPCoreEngine (Lua game framework for GBA - manually provided)
# Tests sprite engine, audio, Lua scripting on GBA. License: unknown
echo -e "\n${GREEN}[24/26] bpcore_BPCoreEngine (manual)${NC}"
if [ -f "$ROMS_DIR/bpcore_BPCoreEngine.gba" ]; then
    echo -e "  ${GREEN}Already exists${NC}"
else
    echo -e "  ${YELLOW}No public download URL - must be manually provided${NC}"
fi

# 25. fantasy-knight (GBA RPG homebrew - manually provided)
# Tests sprites, backgrounds, audio. License: unknown
echo -e "\n${GREEN}[25/26] fantasy-knight (manual)${NC}"
if [ -f "$ROMS_DIR/fantasy-knight.gba" ]; then
    echo -e "  ${GREEN}Already exists${NC}"
else
    echo -e "  ${YELLOW}No public download URL - must be manually provided${NC}"
fi

# Custom ROMs (GBAtoPy team - must be built separately)
echo -e "\n${YELLOW}=== Custom GBAtoPy Test ROMs ===${NC}"
mkdir -p custom

for rom in "${CUSTOM_ROMS[@]}"; do
    rom_file="$rom.gba"
    if [ -f "custom/$rom_file" ]; then
        cp "custom/$rom_file" "$ROMS_DIR/$rom_file"
        echo -e "  ${GREEN}✓${NC} $rom_file"
    else
        echo -e "  ${YELLOW}✗${NC} $rom_file not found (must be built)"
        echo "    See: docs/v3/appendices/f_test_roms_coverage.md"
    fi
done

echo -e "\n${GREEN}=== Moving legacy ROMs ===${NC}"
# Move existing test ROMs from project root to sources
for dir in $(find "$TEST_ROMS_DIR" -mindepth 1 -maxdepth 1 -type d ! -path "$ROMS_DIR" ! -path "$SOURCES_DIR"); do
    dname=$(basename "$dir")
    if [ "$dname" != "roms" ] && [ "$dname" != "sources" ]; then
        if [ ! -d "$SOURCES_DIR/$dname" ]; then
            mv "$dir" "$SOURCES_DIR/$dname"
            echo -e "  ${GREEN}Moved: $dname${NC}"
        fi
    fi
done

echo -e "\n${GREEN}=== Summary ===${NC}"
TOTAL_ROMS=$(find "$ROMS_DIR" -type f \( -name "*.gba" -o -name "*.gb" \) | wc -l)
echo "Total ROMs: $TOTAL_ROMS"
echo ""
echo "ROMs: $ROMS_DIR"
echo "Sources: $SOURCES_DIR"
echo ""
echo "${GREEN}Done.${NC}"
