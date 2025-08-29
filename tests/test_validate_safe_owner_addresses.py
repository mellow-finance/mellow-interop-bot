import os
import sys
import unittest
import importlib.util
from unittest.mock import patch, MagicMock
from web3 import constants, Web3


def load_validate_function():
    """Load just the validate_safe_owner_addresses function with mocked dependencies"""
    root = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(root, "src", "config", "validate_config.py")

    # Create proper mock for web3_scripts that includes real Web3
    mock_web3_scripts = MagicMock()
    # Import the real Web3 class and assign it to the mock
    from web3 import Web3

    mock_web3_scripts.Web3 = Web3
    mock_web3_scripts.Account = MagicMock()

    mock_safe_global = MagicMock()
    mock_config = MagicMock()

    # Temporarily add mocks to sys.modules
    original_modules = {}
    modules_to_mock = {
        "web3_scripts": mock_web3_scripts,
        "safe_global": mock_safe_global,
        "config": mock_config,
    }

    for module_name, mock_module in modules_to_mock.items():
        if module_name in sys.modules:
            original_modules[module_name] = sys.modules[module_name]
        sys.modules[module_name] = mock_module

    try:
        spec = importlib.util.spec_from_file_location("validate_config", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)
        return mod.validate_safe_owner_addresses
    finally:
        # Restore original modules
        for module_name in modules_to_mock.keys():
            if module_name in original_modules:
                sys.modules[module_name] = original_modules[module_name]
            else:
                sys.modules.pop(module_name, None)


class TestValidateSafeOwnerAddresses(unittest.TestCase):
    def setUp(self):
        # Load the function
        self.validate_safe_owner_addresses = load_validate_function()
        # Create a mock Config object
        self.mock_config = MagicMock()

    def test_empty_owners_skips_validation(self):
        """Test that empty owners dictionary skips validation"""
        self.mock_config.telegram_owner_nicknames = {}

        with patch("builtins.print") as mock_print:
            # Should not raise any exception
            self.validate_safe_owner_addresses(self.mock_config)
            mock_print.assert_called_once_with(
                "No telegram nicknames for safe owners are set, skipping validation..."
            )

    def test_single_zero_address_valid(self):
        """Test that single zero address is valid"""
        self.mock_config.telegram_owner_nicknames = {
            "alice": constants.ADDRESS_ZERO,
        }

        # Should not raise any exception
        self.validate_safe_owner_addresses(self.mock_config)

    def test_all_non_zero_addresses_valid(self):
        """Test that all non-zero valid addresses is valid"""
        self.mock_config.telegram_owner_nicknames = {
            "alice": "0x742d35Cc6635C0532925a3b8D4f25749d6d8f0C4",
            "bob": "0x8ba1f109551bD432803012645aac136c8c8b2e05",
            "charlie": "0x1234567890abcdef1234567890abcdef12345678",
        }

        # Should not raise any exception
        self.validate_safe_owner_addresses(self.mock_config)

    def test_mixed_zero_and_non_zero_addresses_invalid(self):
        """Test that mixing zero and non-zero addresses raises ValueError"""
        self.mock_config.telegram_owner_nicknames = {
            "alice": "0x742d35Cc6635C0532925a3b8D4f25749d6d8f0C4",
            "bob": constants.ADDRESS_ZERO,
            "charlie": "0x1234567890abcdef1234567890abcdef12345678",
        }

        with self.assertRaises(ValueError) as context:
            self.validate_safe_owner_addresses(self.mock_config)

        self.assertEqual(
            str(context.exception), "All addresses must be set or all must be omitted!"
        )

    def test_invalid_address_format_raises_error(self):
        """Test that invalid address format raises ValueError"""
        self.mock_config.telegram_owner_nicknames = {
            "alice": "invalid_address",
            "bob": "0x742d35Cc6635C0532925a3b8D4f25749d6d8f0C4",
        }

        with self.assertRaises(ValueError) as context:
            self.validate_safe_owner_addresses(self.mock_config)

        self.assertEqual(str(context.exception), "Invalid address for nickname alice!")

    def test_invalid_address_too_short_raises_error(self):
        """Test that address too short raises ValueError"""
        self.mock_config.telegram_owner_nicknames = {
            "alice": "0x123",
            "bob": "0x742d35Cc6635C0532925a3b8D4f25749d6d8f0C4",
        }

        with self.assertRaises(ValueError) as context:
            self.validate_safe_owner_addresses(self.mock_config)

        self.assertEqual(str(context.exception), "Invalid address for nickname alice!")

    def test_invalid_address_no_0x_prefix_raises_error(self):
        """Test that address without 0x prefix raises ValueError"""
        self.mock_config.telegram_owner_nicknames = {
            "alice": "742d35Cc6635C0532925a3b8D4f25749d6d8f0C4",
            "bob": "0x742d35Cc6635C0532925a3b8D4f25749d6d8f0C4",
        }

        with self.assertRaises(ValueError) as context:
            self.validate_safe_owner_addresses(self.mock_config)

        self.assertEqual(str(context.exception), "Invalid address for nickname alice!")

    def test_duplicate_addresses_raises_error(self):
        """Test that duplicate addresses raises ValueError"""
        self.mock_config.telegram_owner_nicknames = {
            "alice": "0x742d35Cc6635C0532925a3b8D4f25749d6d8f0C4",
            "bob": "0x742d35Cc6635C0532925a3b8D4f25749d6d8f0C4",  # Same address as alice
            "charlie": "0x8ba1f109551bD432803012645aac136c8c8b2e05",
        }

        with self.assertRaises(ValueError) as context:
            self.validate_safe_owner_addresses(self.mock_config)

        self.assertEqual(str(context.exception), "Duplicate owner addresses found!")

    def test_duplicate_zero_addresses_raises_error(self):
        """Test that duplicate (all) zero addresses are not raises ValueError"""
        self.mock_config.telegram_owner_nicknames = {
            "alice": constants.ADDRESS_ZERO,
            "bob": constants.ADDRESS_ZERO,
            "charlie": constants.ADDRESS_ZERO,
        }
        self.validate_safe_owner_addresses(self.mock_config)

    def test_single_owner_valid(self):
        """Test that single owner with valid address works"""
        self.mock_config.telegram_owner_nicknames = {
            "alice": "0x742d35Cc6635C0532925a3b8D4f25749d6d8f0C4",
        }

        # Should not raise any exception
        self.validate_safe_owner_addresses(self.mock_config)

    def test_single_owner_zero_address_valid(self):
        """Test that single owner with zero address works"""
        self.mock_config.telegram_owner_nicknames = {
            "alice": constants.ADDRESS_ZERO,
        }

        # Should not raise any exception
        self.validate_safe_owner_addresses(self.mock_config)

    def test_checksum_addresses_valid(self):
        """Test that properly checksummed addresses are valid"""
        self.mock_config.telegram_owner_nicknames = {
            "alice": "0x742d35Cc6635C0532925a3b8D4f25749d6d8f0C4",  # Proper checksum
            "bob": "0x8ba1f109551bD432803012645aac136c8c8b2e05",  # Proper checksum
        }

        # Should not raise any exception
        self.validate_safe_owner_addresses(self.mock_config)

    def test_lowercase_addresses_valid(self):
        """Test that lowercase addresses are valid (Web3.is_address should handle this)"""
        self.mock_config.telegram_owner_nicknames = {
            "alice": "0x742d35cc6635c0532925a3b8d4f25749d6d8f0c4",  # Lowercase
            "bob": "0x8ba1f109551bd432803012645aac136c8c8b2e05",  # Lowercase
        }

        # Should not raise any exception
        self.validate_safe_owner_addresses(self.mock_config)

    def test_uppercase_addresses_valid(self):
        """Test that uppercase addresses are valid"""
        self.mock_config.telegram_owner_nicknames = {
            "alice": "0x742D35CC6635C0532925A3B8D4F25749D6D8F0C4",  # Uppercase
            "bob": "0x8BA1F109551BD432803012645AAC136C8C8B2E05",  # Uppercase
        }

        # Should not raise any exception
        self.validate_safe_owner_addresses(self.mock_config)

    def test_multiple_invalid_addresses_reports_first(self):
        """Test that multiple invalid addresses reports the first invalid one"""
        self.mock_config.telegram_owner_nicknames = {
            "alice": "invalid1",
            "bob": "invalid2",
            "charlie": "0x742d35Cc6635C0532925a3b8D4f25749d6d8f0C4",
        }

        with self.assertRaises(ValueError) as context:
            self.validate_safe_owner_addresses(self.mock_config)

        # Should report the first invalid address encountered
        error_message = str(context.exception)
        self.assertTrue(error_message.startswith("Invalid address for nickname"))
        self.assertTrue("alice" in error_message or "bob" in error_message)


if __name__ == "__main__":
    unittest.main()
