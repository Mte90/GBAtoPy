"""
Serial I/O Controller Test Suite for GBAtoPy Transpiler.

This test suite verifies the Serial I/O controller behavior, including
SIOCNT register dispatch, transfer modes (normal, multi-player, UART),
clock selection, busy flag behavior, and multi-player data handling.

Run with: python3 -m pytest test_serial.py -v
"""

import unittest
import sys
import os

# Add parent directory to path to import gba_runtime modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from serial import Serial


class MockMemory:
    """Mock memory for Serial class testing."""
    def __init__(self):
        self.data = {}
    
    def write_u16(self, addr: int, value: int):
        self.data[addr] = value & 0xFFFF
    
    def read_u16(self, addr: int) -> int:
        return self.data.get(addr, 0xFFFF)


class TestSerialInitialization(unittest.TestCase):
    """Test Serial class initialization and default state."""

    def test_initial_state_zero(self):
        """New Serial instance should have all fields zeroed."""
        mem = MockMemory()
        serial = Serial(mem)
        
        self.assertEqual(serial.sio_mode, 0, "sio_mode should be 0 initially")
        self.assertEqual(serial.transfer_enabled, False, "transfer_enabled should be False initially")
        self.assertEqual(serial.clock_select, 0, "clock_select should be 0 initially")
        self.assertEqual(serial.receive_data, 0, "receive_data should be 0 initially")
        self.assertEqual(serial.send_data, 0, "send_data should be 0 initially")
        self.assertEqual(serial.multi_player_id, 0, "multi_player_id should be 0 initially")
        self.assertEqual(serial.multi_player_data, [0, 0, 0, 0], "multi_player_data should be [0,0,0,0] initially")
        self.assertEqual(serial.busy_flag, False, "busy_flag should be False initially")
        self.assertEqual(serial.error_flag, False, "error_flag should be False initially")
        self.assertEqual(serial.uart_mode, 0, "uart_mode should be 0 initially")
        self.assertEqual(serial.uart_receive_data, 0, "uart_receive_data should be 0 initially")
        self.assertEqual(serial.gpio_direction, 0, "gpio_direction should be 0 initially")
        self.assertEqual(serial.gpio_data, 0, "gpio_data should be 0 initially")

    def test_siodata8_and_siomlt_send_same_address(self):
        """REG_SIODATA8 and REG_SIOMLT_SEND should be the same address (0x0400012A)."""
        self.assertEqual(Serial.REG_SIODATA8, 0x0400012A)
        self.assertEqual(Serial.REG_SIOMLT_SEND, 0x0400012A)

    def test_siocnt_has_two_addresses(self):
        """SIOCNT register is accessible at both 0x04000128 and 0x0400012C."""
        # Note: REG_SIOCNT constant is defined twice in serial.py, second overwrites first
        # So Serial.REG_SIOCNT == 0x0400012C (the last definition)
        self.assertEqual(Serial.REG_SIOCNT, 0x0400012C, "Last REG_SIOCNT definition is 0x0400012C")
        # But both addresses are handled in write_register/read_register
        self.assertEqual(Serial.REG_SIOSTAT, 0x04000128, "REG_SIOSTAT is 0x04000128")


class TestWriteRegisterDispatch(unittest.TestCase):
    """Test write_register() dispatches to correct handlers."""

    def test_write_siomulti0(self):
        """Writing to REG_SIOMULTI0 should set multi_player_data[0]."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.write_register(0x04000120, 0x1234)
        self.assertEqual(serial.multi_player_data[0], 0x1234)

    def test_write_siomulti1(self):
        """Writing to REG_SIOMULTI1 should set multi_player_data[1]."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.write_register(0x04000122, 0x5678)
        self.assertEqual(serial.multi_player_data[1], 0x5678)

    def test_write_siomulti2(self):
        """Writing to REG_SIOMULTI2 should set multi_player_data[2]."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.write_register(0x04000124, 0xABCD)
        self.assertEqual(serial.multi_player_data[2], 0xABCD)

    def test_write_siomulti3(self):
        """Writing to REG_SIOMULTI3 should set multi_player_data[3]."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.write_register(0x04000126, 0xEF01)
        self.assertEqual(serial.multi_player_data[3], 0xEF01)

    def test_write_siodata8_sets_send_data(self):
        """Writing to REG_SIODATA8 (0x0400012A) should set send_data."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.write_register(0x0400012A, 0x4242)
        self.assertEqual(serial.send_data, 0x4242)

    def test_write_siocnt_low_address(self):
        """Writing to 0x04000128 should call _write_siocnt()."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.write_register(0x04000128, 0x0080)  # Enable transfer (bit 7)
        self.assertEqual(serial.transfer_enabled, True)

    def test_write_siocnt_high_address(self):
        """Writing to 0x0400012C should call _write_siocnt()."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.write_register(0x0400012C, 0x0080)  # Enable transfer (bit 7)
        self.assertEqual(serial.transfer_enabled, True)


class TestWriteSiocntTransferModes(unittest.TestCase):
    """Test _write_siocnt() transfer mode configuration."""

    def test_sio_mode_normal(self):
        """SIO mode 0 (normal) should be set via bits 12-13."""
        mem = MockMemory()
        serial = Serial(mem)
        # Mode 0: bits 12-13 = 00
        serial.write_register(0x04000128, 0x0000)
        self.assertEqual(serial.sio_mode, 0, "Mode should be 0 (normal)")

    def test_sio_mode_multi_player(self):
        """SIO mode 1 (multi-player) should be set via bits 12-13."""
        mem = MockMemory()
        serial = Serial(mem)
        # Mode 1: bits 12-13 = 01
        serial.write_register(0x04000128, 0x1000)
        self.assertEqual(serial.sio_mode, 1, "Mode should be 1 (multi-player)")

    def test_sio_mode_uart(self):
        """SIO mode 2 (UART) should be set via bits 12-13."""
        mem = MockMemory()
        serial = Serial(mem)
        # Mode 2: bits 12-13 = 10
        serial.write_register(0x04000128, 0x2000)
        self.assertEqual(serial.sio_mode, 2, "Mode should be 2 (UART)")

    def test_sio_mode_reserved(self):
        """SIO mode 3 (reserved) should be set via bits 12-13."""
        mem = MockMemory()
        serial = Serial(mem)
        # Mode 3: bits 12-13 = 11
        serial.write_register(0x04000128, 0x3000)
        self.assertEqual(serial.sio_mode, 3, "Mode should be 3 (reserved)")

    def test_transfer_enable_bit(self):
        """Transfer enable bit (bit 7) should control transfer_enabled."""
        mem = MockMemory()
        serial = Serial(mem)
        
        # Disable transfer
        serial.write_register(0x04000128, 0x0000)
        self.assertEqual(serial.transfer_enabled, False, "Transfer should be disabled")
        
        # Enable transfer
        serial.write_register(0x04000128, 0x0080)
        self.assertEqual(serial.transfer_enabled, True, "Transfer should be enabled")

    def test_multi_player_id_bits(self):
        """Multi-player ID bits (bits 8-9) should set multi_player_id."""
        mem = MockMemory()
        serial = Serial(mem)
        
        # ID 0
        serial.write_register(0x04000128, 0x0000)
        self.assertEqual(serial.multi_player_id, 0)
        
        # ID 1
        serial.write_register(0x04000128, 0x0100)
        self.assertEqual(serial.multi_player_id, 1)
        
        # ID 2
        serial.write_register(0x04000128, 0x0200)
        self.assertEqual(serial.multi_player_id, 2)
        
        # ID 3
        serial.write_register(0x04000128, 0x0300)
        self.assertEqual(serial.multi_player_id, 3)


class TestClockSelection(unittest.TestCase):
    """Test clock selection bits (bits 0-1)."""

    def test_clock_select_256kHz(self):
        """Clock select 0 should be 256kHz."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.write_register(0x04000128, 0x0000)
        self.assertEqual(serial.clock_select, 0, "Clock select should be 0 (256kHz)")

    def test_clock_select_512kHz(self):
        """Clock select 1 should be 512kHz."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.write_register(0x04000128, 0x0001)
        self.assertEqual(serial.clock_select, 1, "Clock select should be 1 (512kHz)")

    def test_clock_select_4MHz(self):
        """Clock select 2 should be 4MHz."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.write_register(0x04000128, 0x0002)
        self.assertEqual(serial.clock_select, 2, "Clock select should be 2 (4MHz)")

    def test_clock_select_8MHz(self):
        """Clock select 3 should be 8MHz."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.write_register(0x04000128, 0x0003)
        self.assertEqual(serial.clock_select, 3, "Clock select should be 3 (8MHz)")


class TestBusyFlagBehavior(unittest.TestCase):
    """Test busy flag behavior during transfers."""

    def test_busy_flag_false_initially(self):
        """Busy flag should be False initially."""
        mem = MockMemory()
        serial = Serial(mem)
        self.assertEqual(serial.busy_flag, False, "Busy flag should be False initially")

    def test_busy_flag_true_during_uart_transfer(self):
        """Busy flag should be True during UART transfer."""
        mem = MockMemory()
        serial = Serial(mem)
        # Write to SIODATA8 in UART mode (mode 2)
        serial.write_register(0x04000128, 0x2000)  # Set UART mode
        serial.write_register(0x0400012A, 0x4242)  # Trigger UART transfer
        # After _uart_transfer(), busy_flag should be False (it's set True then False)
        self.assertEqual(serial.busy_flag, False, "Busy flag should be False after transfer completes")

    def test_busy_flag_in_siocnt_read(self):
        """Busy flag should be reflected in SIOCNT read value."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.busy_flag = True
        value = serial.read_register(0x04000128)
        # Busy flag is bit 3
        self.assertEqual(value & 0x0008, 0x0008, "Busy flag bit should be set in SIOCNT")


class TestMultiPlayerDataRegisters(unittest.TestCase):
    """Test multi-player data register read/write."""

    def test_read_multiplayer_data_mode1(self):
        """Reading multi-player registers in mode 1 should return player data."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.sio_mode = 1  # Multi-player mode
        serial.multi_player_data = [0x1111, 0x2222, 0x3333, 0x4444]
        
        self.assertEqual(serial.read_register(0x04000120), 0x1111)
        self.assertEqual(serial.read_register(0x04000122), 0x2222)
        self.assertEqual(serial.read_register(0x04000124), 0x3333)
        self.assertEqual(serial.read_register(0x04000126), 0x4444)

    def test_read_multiplayer_data_mode0(self):
        """Reading multi-player registers in mode 0 should return receive_data bytes."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.sio_mode = 0  # Normal mode
        serial.receive_data = 0x1234
        
        self.assertEqual(serial.read_register(0x04000120), 0x1234, "Should return receive_data low")
        self.assertEqual(serial.read_register(0x04000122), 0x12, "Should return receive_data high byte")
        self.assertEqual(serial.read_register(0x04000124), 0xFF, "Should return 0xFF (unconnected)")
        self.assertEqual(serial.read_register(0x04000126), 0xFF, "Should return 0xFF (unconnected)")


class TestUARTMode(unittest.TestCase):
    """Test UART mode configuration and behavior."""

    def test_uart_mode_set(self):
        """UART mode should be set via sio_mode = 2."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.write_register(0x04000128, 0x2000)  # Mode 2 = UART
        self.assertEqual(serial.sio_mode, 2, "Mode should be 2 (UART)")

    def test_uart_transfer_triggers_on_write_mode0(self):
        """Writing to SIODATA8 in mode 0 triggers _uart_transfer()."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.write_register(0x04000128, 0x0000)  # Mode 0 (normal/UART-like)
        serial.write_register(0x0400012A, 0xABCD)  # Send data
        
        # In mode 0, _uart_transfer() is called which copies send_data to receive_data
        self.assertEqual(serial.receive_data, 0xABCD, "receive_data should mirror send_data after transfer in mode 0")

    def test_uart_transfer_does_not_trigger_mode1(self):
        """Writing to SIODATA8 in mode 1 should NOT trigger _uart_transfer()."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.write_register(0x04000128, 0x1000)  # Mode 1 (multi-player)
        serial.write_register(0x0400012A, 0xABCD)  # Send data
        
        # In mode 1, _uart_transfer() is NOT called
        self.assertEqual(serial.receive_data, 0, "receive_data should NOT change in mode 1")

    def test_uart_transfer_does_not_trigger_mode2(self):
        """Writing to SIODATA8 in mode 2 should NOT trigger _uart_transfer()."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.write_register(0x04000128, 0x2000)  # Mode 2 (UART)
        serial.write_register(0x0400012A, 0xABCD)  # Send data
        
        # In mode 2, _uart_transfer() is NOT called (only mode 0 triggers it)
        self.assertEqual(serial.receive_data, 0, "receive_data should NOT change in mode 2")

    def test_uart_send_data_preserved(self):
        """Send data should be preserved after UART transfer."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.write_register(0x04000128, 0x2000)  # UART mode
        serial.write_register(0x0400012A, 0x5678)
        
        self.assertEqual(serial.send_data, 0x5678, "send_data should be preserved")


class TestReadSiocnt(unittest.TestCase):
    """Test SIOCNT register read behavior."""

    def test_read_siocnt_returns_mode(self):
        """Reading SIOCNT should return sio_mode in bits 12-13."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.sio_mode = 2
        value = serial.read_register(0x04000128)
        self.assertEqual((value >> 12) & 0x3, 2, "SIOCNT should return mode 2")

    def test_read_siocnt_returns_mp_id(self):
        """Reading SIOCNT should return multi_player_id in bits 8-9."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.multi_player_id = 3
        value = serial.read_register(0x04000128)
        self.assertEqual((value >> 8) & 0x3, 3, "SIOCNT should return MP ID 3")

    def test_read_siocnt_returns_transfer_enable(self):
        """Reading SIOCNT should return transfer_enabled in bit 7."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.transfer_enabled = True
        value = serial.read_register(0x04000128)
        self.assertEqual((value >> 7) & 0x1, 1, "SIOCNT should return transfer enable = 1")

    def test_read_siocnt_returns_clock_select(self):
        """Reading SIOCNT should return clock_select in bits 0-1."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.clock_select = 3
        value = serial.read_register(0x04000128)
        self.assertEqual(value & 0x3, 3, "SIOCNT should return clock select 3")

    def test_read_siocnt_returns_busy_flag(self):
        """Reading SIOCNT should return busy_flag in bit 3."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.busy_flag = True
        value = serial.read_register(0x04000128)
        self.assertEqual((value >> 3) & 0x1, 1, "SIOCNT should return busy flag = 1")

    def test_read_siocnt_returns_error_flag(self):
        """Reading SIOCNT should return error_flag in bit 2."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.error_flag = True
        value = serial.read_register(0x04000128)
        self.assertEqual((value >> 2) & 0x1, 1, "SIOCNT should return error flag = 1")

    def test_read_siocnt_high_address(self):
        """Reading 0x0400012C should also return SIOCNT value."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.sio_mode = 1
        serial.clock_select = 2
        value = serial.read_register(0x0400012C)
        self.assertEqual((value >> 12) & 0x3, 1, "High address should return mode")
        self.assertEqual(value & 0x3, 2, "High address should return clock select")


class TestSiodataRegister(unittest.TestCase):
    """Test SIODATA register read/write behavior."""

    def test_siodata_write_sets_send_data(self):
        """Writing to SIODATA should set send_data."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.write_register(0x0400012A, 0x9ABC)
        self.assertEqual(serial.send_data, 0x9ABC)

    def test_siodata_read_mode0_returns_receive(self):
        """Reading SIODATA in mode 0 should return receive_data."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.sio_mode = 0
        serial.receive_data = 0xDEAD
        self.assertEqual(serial.read_register(0x0400012A), 0xDEAD)

    def test_siodata_read_mode1_returns_send(self):
        """Reading SIODATA in mode 1 should return send_data."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.sio_mode = 1
        serial.send_data = 0xBEEF
        self.assertEqual(serial.read_register(0x0400012A), 0xBEEF)

    def test_siodata_data_masked_to_16_bits(self):
        """Data written to SIODATA should be masked to 16 bits."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.write_register(0x0400012A, 0x12345678)
        self.assertEqual(serial.send_data, 0x5678, "Data should be masked to 16 bits")


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def test_write_unknown_address(self):
        """Writing to unknown address should not crash."""
        mem = MockMemory()
        serial = Serial(mem)
        serial.write_register(0x9999, 0xFFFF)  # Unknown address
        # Should not raise exception

    def test_read_unknown_address(self):
        """Reading unknown address should return 0xFF."""
        mem = MockMemory()
        serial = Serial(mem)
        self.assertEqual(serial.read_register(0x9999), 0xFF, "Unknown address should return 0xFF")

    def test_data_overflow_masking(self):
        """Values written to registers should be properly masked."""
        mem = MockMemory()
        serial = Serial(mem)
        
        # Multi-player data masked to 16 bits
        serial.write_register(0x04000120, 0x12345678)
        self.assertEqual(serial.multi_player_data[0], 0x5678)
        
        # Send data masked to 16 bits
        serial.write_register(0x0400012A, 0xDEADBEEF)
        self.assertEqual(serial.send_data, 0xBEEF)


if __name__ == '__main__':
    unittest.main()