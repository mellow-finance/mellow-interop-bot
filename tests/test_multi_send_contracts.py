import unittest
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple
from web3 import Web3

# Add src directory to path to import modules
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Import only what we need to avoid circular imports
import importlib.util

# Import read_config function directly
config_module_path = src_path / "config" / "read_config.py"
spec = importlib.util.spec_from_file_location("read_config", config_module_path)
read_config_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(read_config_module)
read_config = read_config_module.read_config

# Import multi_send_contracts directly
multi_send_call_path = src_path / "safe_global" / "multi_send_call.py"
spec = importlib.util.spec_from_file_location("multi_send_call", multi_send_call_path)
multi_send_call_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(multi_send_call_module)
multi_send_contracts = multi_send_call_module.multi_send_contracts

from web3_scripts.base import get_w3

# Function selectors (first 4 bytes of keccak256 hash of function signature)
MULTISEND_FUNCTION_SELECTOR = "8d80ff0a"  # multiSend(bytes)

# Expected bytecode size: 415 bytes ± 50 (based on actual contract sizes: ~410-421 bytes)
EXPECTED_BYTECODE_SIZE = 415
BYTECODE_SIZE_TOLERANCE = 50


class TestMultiSendContracts(unittest.TestCase):
    """Test multi send contracts across different networks."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test class with configuration."""
        # Load configuration using read_config
        config_path = Path(__file__).parent.parent / "config.json"
        config = read_config(str(config_path))
        
        # Extract RPC URLs from config
        cls.rpc_urls = {
            "Ethereum": config.target_rpc,
        }
        
        # Add source chain RPCs
        for source in config.sources:
            cls.rpc_urls[source.name] = source.rpc

    def check_multisend_function(self, bytecode: str) -> bool:
        """
        Check if the contract bytecode contains multiSend function selector.
        """
        if not bytecode or bytecode == "0x":
            return False
        
        # Remove '0x' prefix if present
        clean_bytecode = bytecode.lower().replace('0x', '')
        
        # Check for function selector in the bytecode
        return MULTISEND_FUNCTION_SELECTOR in clean_bytecode

    def get_contract_code(self, rpc_url: str, contract_address: str) -> Optional[str]:
        """
        Get the contract bytecode for a given contract address using Web3.
        """
        try:
            w3 = get_w3(rpc_url)
            
            # Check if connected
            self.assertTrue(w3.is_connected(), f"Failed to connect to RPC: {rpc_url}")
                
            # Get contract code
            code = w3.eth.get_code(w3.to_checksum_address(contract_address))
            bytecode = code.hex()
            
            return bytecode
            
        except Exception as e:
            self.fail(f"Error getting contract code for {contract_address} on {rpc_url}: {e}")

    def check_bytecode_size(self, bytecode: str) -> bool:
        """
        Check if bytecode size is within expected range (820 ± 50 bytes).
        """
        if not bytecode or bytecode == "0x":
            return False
            
        # Remove '0x' prefix if present
        clean_bytecode = bytecode.replace('0x', '')
        
        # Each hex character represents 4 bits, so 2 hex chars = 1 byte
        bytecode_size = len(clean_bytecode) // 2
        
        min_size = EXPECTED_BYTECODE_SIZE - BYTECODE_SIZE_TOLERANCE
        max_size = EXPECTED_BYTECODE_SIZE + BYTECODE_SIZE_TOLERANCE
        
        return min_size <= bytecode_size <= max_size

    def test_multi_send_contracts_exist_and_valid(self):
        """Test that multi send contracts exist on all networks and have valid bytecode."""
        for network_name, rpc_url in self.rpc_urls.items():
            with self.subTest(network=network_name):
                for version, contract_addresses in multi_send_contracts.items():
                    # Handle both single address and list of addresses
                    if isinstance(contract_addresses, list):
                        addresses_to_test = contract_addresses
                    else:
                        addresses_to_test = [contract_addresses]
                    
                    for contract_address in addresses_to_test:
                        with self.subTest(version=version, address=contract_address):
                            # Get contract bytecode
                            bytecode = self.get_contract_code(rpc_url, contract_address)
                            
                            # Skip if contract doesn't exist on this network
                            if not bytecode or bytecode == "0x":
                                continue
                            
                            # Check if multiSend function is present
                            has_multisend = self.check_multisend_function(bytecode)
                            self.assertTrue(has_multisend, 
                                f"Contract {version} at {contract_address} on {network_name} "
                                f"does not contain multiSend function (selector: {MULTISEND_FUNCTION_SELECTOR})")
                            
                            # Check bytecode size is within expected range
                            valid_size = self.check_bytecode_size(bytecode)
                            bytecode_size = len(bytecode.replace('0x', '')) // 2
                            self.assertTrue(valid_size, 
                                f"Contract {version} at {contract_address} on {network_name} "
                                f"has unexpected bytecode size: {bytecode_size} bytes "
                                f"(expected: {EXPECTED_BYTECODE_SIZE} ± {BYTECODE_SIZE_TOLERANCE})")

    def test_multi_send_function_selector_detection(self):
        """Test the multiSend function selector detection logic."""
        # Test cases for function selector detection
        test_cases = [
            # Valid bytecode with multiSend selector
            ("0x608060405234801561001057600080fd5b506004361061002b5760003560e01c80638d80ff0a14610030575b600080fd5b", True),
            # Bytecode without multiSend selector
            ("0x608060405234801561001057600080fd5b506004361061002b5760003560e01c8063abcdef1214610030575b600080fd5b", False),
            # Empty bytecode
            ("0x", False),
            # None bytecode
            (None, False),
            # Bytecode with selector in the middle
            ("0x1234567890abcdef8d80ff0aabcdef1234567890", True),
        ]
        
        for bytecode, expected in test_cases:
            with self.subTest(bytecode=bytecode):
                result = self.check_multisend_function(bytecode)
                self.assertEqual(result, expected, 
                    f"Function selector detection failed for bytecode: {bytecode}")

    def test_bytecode_size_validation(self):
        """Test the bytecode size validation logic."""
        # Test cases for bytecode size validation (each hex char = 4 bits, 2 hex chars = 1 byte)
        test_cases = [
            # Exactly 415 bytes (830 hex chars)
            ("0x" + "a" * 830, True),
            # 365 bytes (within tolerance: 415 - 50)
            ("0x" + "a" * 730, True),
            # 465 bytes (within tolerance: 415 + 50)
            ("0x" + "a" * 930, True),
            # 364 bytes (below tolerance)
            ("0x" + "a" * 728, False),
            # 466 bytes (above tolerance)
            ("0x" + "a" * 932, False),
            # Empty bytecode
            ("0x", False),
            # None bytecode
            (None, False),
        ]
        
        for bytecode, expected in test_cases:
            with self.subTest(bytecode=bytecode[:20] + "..." if bytecode and len(bytecode) > 20 else bytecode):
                result = self.check_bytecode_size(bytecode)
                self.assertEqual(result, expected, 
                    f"Bytecode size validation failed for bytecode of length: "
                    f"{len(bytecode.replace('0x', '')) // 2 if bytecode else 'None'} bytes")


if __name__ == "__main__":
    unittest.main()
