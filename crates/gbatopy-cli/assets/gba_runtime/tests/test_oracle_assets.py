"""Tests for OracleAssetTracker - VRAM write classification for asset extraction."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from oracle_assets import OracleAssetTracker


def test_oracle_asset_tracker_construction():
    """OracleAssetTracker construction: initializes empty tracking structures."""
    tracker = OracleAssetTracker()
    
    assert tracker.vram_tile_writes == {}
    assert tracker.vram_palette_writes == {}
    assert tracker.oam_writes == []
    assert tracker.vram_tilemap_writes == {}
    assert tracker.tile_write_addrs == set()
    assert tracker.palette_write_addrs == set()
    assert tracker.tilemap_write_addrs == set()
    
    print("✓ test_oracle_asset_tracker_construction passed")


def test_track_vram_write_tile_region_bg():
    """track_vram_write: BG tile region (0x06000000-0x06007FFF) classified as tile."""
    tracker = OracleAssetTracker()
    
    # Write to BG tile region
    tracker.track_vram_write(0x06000000, b"\x00" * 32, 32)
    tracker.track_vram_write(0x06004000, b"\x00" * 32, 32)
    tracker.track_vram_write(0x06007FFF, b"\x00" * 32, 32)
    
    assert len(tracker.tile_write_addrs) == 3
    assert 0x06000000 in tracker.tile_write_addrs
    assert 0x06004000 in tracker.tile_write_addrs
    assert 0x06007FFF in tracker.tile_write_addrs
    assert len(tracker.vram_tile_writes) == 3
    
    print("✓ test_track_vram_write_tile_region_bg passed")


def test_track_vram_write_tilemap_region():
    """track_vram_write: Tilemap region (0x06008000-0x0600FFFF) classified as tilemap."""
    tracker = OracleAssetTracker()
    
    # Write to tilemap region
    tracker.track_vram_write(0x06008000, b"\x00" * 32, 32)
    tracker.track_vram_write(0x0600C000, b"\x00" * 32, 32)
    tracker.track_vram_write(0x0600FFFF, b"\x00" * 32, 32)
    
    assert len(tracker.tilemap_write_addrs) == 3
    assert 0x06008000 in tracker.tilemap_write_addrs
    assert 0x0600C000 in tracker.tilemap_write_addrs
    assert 0x0600FFFF in tracker.tilemap_write_addrs
    assert len(tracker.vram_tilemap_writes) == 3
    
    print("✓ test_track_vram_write_tilemap_region passed")


def test_track_vram_write_framebuffer_region():
    """track_vram_write: Framebuffer region (0x06010000+) classified as tile."""
    tracker = OracleAssetTracker()
    
    # Write to framebuffer region (bitmap modes)
    tracker.track_vram_write(0x06010000, b"\x00" * 32, 32)
    tracker.track_vram_write(0x06017FFF, b"\x00" * 32, 32)
    
    assert len(tracker.tile_write_addrs) == 2
    assert 0x06010000 in tracker.tile_write_addrs
    assert 0x06017FFF in tracker.tile_write_addrs
    assert len(tracker.vram_tile_writes) == 2
    
    print("✓ test_track_vram_write_framebuffer_region passed")


def test_track_vram_write_boundary_tile_start():
    """track_vram_write: Address exactly at tile region start (0x06000000)."""
    tracker = OracleAssetTracker()
    
    tracker.track_vram_write(0x06000000, b"\x00" * 32, 32)
    
    assert 0x06000000 in tracker.tile_write_addrs
    assert len(tracker.tile_write_addrs) == 1
    
    print("✓ test_track_vram_write_boundary_tile_start passed")


def test_track_vram_write_boundary_tile_end():
    """track_vram_write: Address exactly at tile region end (0x06007FFF)."""
    tracker = OracleAssetTracker()
    
    tracker.track_vram_write(0x06007FFF, b"\x00" * 32, 32)
    
    assert 0x06007FFF in tracker.tile_write_addrs
    assert len(tracker.tile_write_addrs) == 1
    
    print("✓ test_track_vram_write_boundary_tile_end passed")


def test_track_vram_write_boundary_tilemap_start():
    """track_vram_write: Address exactly at tilemap region start (0x06008000)."""
    tracker = OracleAssetTracker()
    
    tracker.track_vram_write(0x06008000, b"\x00" * 32, 32)
    
    assert 0x06008000 in tracker.tilemap_write_addrs
    assert len(tracker.tilemap_write_addrs) == 1
    
    print("✓ test_track_vram_write_boundary_tilemap_start passed")


def test_track_vram_write_boundary_tilemap_end():
    """track_vram_write: Address exactly at tilemap region end (0x0600FFFF)."""
    tracker = OracleAssetTracker()
    
    tracker.track_vram_write(0x0600FFFF, b"\x00" * 32, 32)
    
    assert 0x0600FFFF in tracker.tilemap_write_addrs
    assert len(tracker.tilemap_write_addrs) == 1
    
    print("✓ test_track_vram_write_boundary_tilemap_end passed")


def test_track_vram_write_boundary_framebuffer_start():
    """track_vram_write: Address exactly at framebuffer region start (0x06010000)."""
    tracker = OracleAssetTracker()
    
    tracker.track_vram_write(0x06010000, b"\x00" * 32, 32)
    
    assert 0x06010000 in tracker.tile_write_addrs
    assert len(tracker.tile_write_addrs) == 1
    
    print("✓ test_track_vram_write_boundary_framebuffer_start passed")


def test_track_vram_write_one_past_tile_end():
    """track_vram_write: Address one past tile region end (0x06008000) -> tilemap."""
    tracker = OracleAssetTracker()
    
    # 0x06007FFF is last tile, 0x06008000 is first tilemap
    tracker.track_vram_write(0x06007FFF, b"\x00" * 32, 32)
    tracker.track_vram_write(0x06008000, b"\x00" * 32, 32)
    
    assert 0x06007FFF in tracker.tile_write_addrs
    assert 0x06008000 in tracker.tilemap_write_addrs
    assert len(tracker.tile_write_addrs) == 1
    assert len(tracker.tilemap_write_addrs) == 1
    
    print("✓ test_track_vram_write_one_past_tile_end passed")


def test_track_vram_write_one_past_tilemap_end():
    """track_vram_write: Address one past tilemap region end (0x06010000) -> framebuffer."""
    tracker = OracleAssetTracker()
    
    # 0x0600FFFF is last tilemap, 0x06010000 is first framebuffer
    tracker.track_vram_write(0x0600FFFF, b"\x00" * 32, 32)
    tracker.track_vram_write(0x06010000, b"\x00" * 32, 32)
    
    assert 0x0600FFFF in tracker.tilemap_write_addrs
    assert 0x06010000 in tracker.tile_write_addrs
    assert len(tracker.tilemap_write_addrs) == 1
    assert len(tracker.tile_write_addrs) == 1
    
    print("✓ test_track_vram_write_one_past_tilemap_end passed")


def test_track_vram_write_multiple_writes():
    """track_vram_write: Multiple writes tracked correctly."""
    tracker = OracleAssetTracker()
    
    # Mix of tile, tilemap, and framebuffer writes
    tracker.track_vram_write(0x06000000, b"\x01" * 32, 32)
    tracker.track_vram_write(0x06001000, b"\x02" * 32, 32)
    tracker.track_vram_write(0x06008000, b"\x03" * 32, 32)
    tracker.track_vram_write(0x06009000, b"\x04" * 32, 32)
    tracker.track_vram_write(0x06010000, b"\x05" * 32, 32)
    tracker.track_vram_write(0x06011000, b"\x06" * 32, 32)
    
    assert len(tracker.tile_write_addrs) == 4  # 0x06000000, 0x06001000, 0x06010000, 0x06011000
    assert len(tracker.tilemap_write_addrs) == 2  # 0x06008000, 0x06009000
    assert len(tracker.vram_tile_writes) == 4
    assert len(tracker.vram_tilemap_writes) == 2
    
    # Verify data stored correctly
    assert tracker.vram_tile_writes[0x06000000] == b"\x01" * 32
    assert tracker.vram_tilemap_writes[0x06008000] == b"\x03" * 32
    assert tracker.vram_tile_writes[0x06010000] == b"\x05" * 32
    
    print("✓ test_track_vram_write_multiple_writes passed")


def test_track_vram_write_address_zero():
    """track_vram_write: Address 0 has negative offset, classified as tile (offset < 0x8000)."""
    tracker = OracleAssetTracker()
    
    tracker.track_vram_write(0, b"\x00" * 32, 32)
    
    # Address 0 has offset = -0x06000000, which is < 0x8000, so it's classified as tile
    # Note: This is a potential bug - negative offsets should be rejected
    assert 0 in tracker.tile_write_addrs
    assert len(tracker.tile_write_addrs) == 1
    
    print("✓ test_track_vram_write_address_zero passed")


def test_track_vram_write_max_address():
    """track_vram_write: Max VRAM address (0x06017FFF) classified as tile."""
    tracker = OracleAssetTracker()
    
    tracker.track_vram_write(0x06017FFF, b"\x00" * 32, 32)
    
    assert 0x06017FFF in tracker.tile_write_addrs
    assert len(tracker.tile_write_addrs) == 1
    
    print("✓ test_track_vram_write_max_address passed")


def test_track_vram_write_non_vram_address():
    """track_vram_write: Non-VRAM address (e.g., WRAM) with negative offset classified as tile."""
    tracker = OracleAssetTracker()
    
    # IWRAM: 0x03000000 - offset = -0x03000000 < 0x8000, classified as tile
    tracker.track_vram_write(0x03000000, b"\x00" * 32, 32)
    # EWRAM: 0x02000000 - offset = -0x04000000 < 0x8000, classified as tile
    tracker.track_vram_write(0x02000000, b"\x00" * 32, 32)
    
    # Note: Negative offsets are < 0x8000, so they get classified as tiles
    # This is a potential bug - should check offset >= 0
    assert len(tracker.tile_write_addrs) == 2
    assert 0x03000000 in tracker.tile_write_addrs
    assert 0x02000000 in tracker.tile_write_addrs
    
    print("✓ test_track_vram_write_non_vram_address passed")


def test_track_palette_write_bg_palette():
    """track_palette_write: BG palette (0x05000000-0x050001FF) tracked."""
    tracker = OracleAssetTracker()
    
    tracker.track_palette_write(0x05000000, b"\x00" * 4, 4)
    tracker.track_palette_write(0x050001FF, b"\x00" * 4, 4)
    
    assert len(tracker.palette_write_addrs) == 2
    assert 0x05000000 in tracker.palette_write_addrs
    assert 0x050001FF in tracker.palette_write_addrs
    
    print("✓ test_track_palette_write_bg_palette passed")


def test_track_palette_write_obj_palette():
    """track_palette_write: OBJ palette (0x05000200-0x050003FF) tracked."""
    tracker = OracleAssetTracker()
    
    tracker.track_palette_write(0x05000200, b"\x00" * 4, 4)
    tracker.track_palette_write(0x050003FF, b"\x00" * 4, 4)
    
    assert len(tracker.palette_write_addrs) == 2
    assert 0x05000200 in tracker.palette_write_addrs
    assert 0x050003FF in tracker.palette_write_addrs
    
    print("✓ test_track_palette_write_obj_palette passed")


def test_track_palette_write_boundary():
    """track_palette_write: Boundary at 0x05000200 (BG vs OBJ split)."""
    tracker = OracleAssetTracker()
    
    tracker.track_palette_write(0x050001FF, b"\x00" * 4, 4)
    tracker.track_palette_write(0x05000200, b"\x00" * 4, 4)
    
    assert 0x050001FF in tracker.palette_write_addrs
    assert 0x05000200 in tracker.palette_write_addrs
    assert len(tracker.palette_write_addrs) == 2
    
    print("✓ test_track_palette_write_boundary passed")


def test_track_oam_write_valid():
    """track_oam_write: Valid OAM write (8+ bytes) tracked."""
    tracker = OracleAssetTracker()
    
    # 8-byte sprite attributes (required minimum)
    data = b'\x00\x00\x00\x00\x00\x00\x00\x00'
    
    tracker.track_oam_write(0x07000000, data)
    
    assert len(tracker.oam_writes) == 1
    sprite = tracker.oam_writes[0]
    assert sprite["addr"] == 0x07000000
    assert sprite["y"] == 0
    assert sprite["x"] == 0
    assert sprite["tile"] == 0
    
    print("✓ test_track_oam_write_valid passed")


def test_track_oam_write_multiple():
    """track_oam_write: Multiple OAM writes tracked."""
    tracker = OracleAssetTracker()
    
    for i in range(4):
        # 8 bytes minimum required
        data = bytes([i, 0, 0, 0, 0, i, 0, 0])  # y=i, tile=i
        tracker.track_oam_write(0x07000000 + i * 8, data)
    
    assert len(tracker.oam_writes) == 4
    assert tracker.oam_writes[0]["y"] == 0
    assert tracker.oam_writes[3]["y"] == 3
    
    print("✓ test_track_oam_write_multiple passed")


def test_extract_assets_from_trace_empty():
    """extract_assets_from_trace: Empty tracker returns empty asset structure."""
    tracker = OracleAssetTracker()
    assets = tracker.extract_assets_from_trace()
    
    assert assets["tiles"] == []
    assert assets["palettes"]["bg"] == []
    assert assets["palettes"]["obj"] == []
    assert assets["tilemaps"]["bg0"] == []
    assert assets["tilemaps"]["bg1"] == []
    assert assets["tilemaps"]["bg2"] == []
    assert assets["tilemaps"]["bg3"] == []
    assert assets["sprites"] == []
    
    print("✓ test_extract_assets_from_trace_empty passed")


if __name__ == "__main__":
    test_oracle_asset_tracker_construction()
    test_track_vram_write_tile_region_bg()
    test_track_vram_write_tilemap_region()
    test_track_vram_write_framebuffer_region()
    test_track_vram_write_boundary_tile_start()
    test_track_vram_write_boundary_tile_end()
    test_track_vram_write_boundary_tilemap_start()
    test_track_vram_write_boundary_tilemap_end()
    test_track_vram_write_boundary_framebuffer_start()
    test_track_vram_write_one_past_tile_end()
    test_track_vram_write_one_past_tilemap_end()
    test_track_vram_write_multiple_writes()
    test_track_vram_write_address_zero()
    test_track_vram_write_max_address()
    test_track_vram_write_non_vram_address()
    test_track_palette_write_bg_palette()
    test_track_palette_write_obj_palette()
    test_track_palette_write_boundary()
    test_track_oam_write_valid()
    test_track_oam_write_multiple()
    test_extract_assets_from_trace_empty()
    
    print("\nAll 21 OracleAssetTracker tests passed!")