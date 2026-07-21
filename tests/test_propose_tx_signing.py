import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import safe_global.propose_tx as propose_tx
from config.read_config import SafeGlobal


class TestCreateSignedSafeTxForSafe(unittest.TestCase):
    """The signing path must route chain reads through get_w3 (fallback-capable)
    and sign fully offline, so it never hands a comma-separated RPC string to a
    node client that cannot parse it."""

    def setUp(self):
        # Throwaway well-known test key (Hardhat/Ganache account #0). Not a secret.
        self.private_key = (
            "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        )
        self.safe_global = SafeGlobal(
            safe_address="0x1234567890123456789012345678901234567890",
            proposer_private_key=self.private_key,
            api_url="https://safe-api.example.com",
        )

    @patch.object(propose_tx, "get_contract")
    @patch.object(propose_tx, "get_w3")
    def test_signs_offline_using_fallback_w3(self, mock_get_w3, mock_get_contract):
        fake_w3 = MagicMock()
        fake_w3.eth.chain_id = 56
        mock_get_w3.return_value = fake_w3

        fake_contract = MagicMock()
        fake_contract.functions.VERSION.return_value.call.return_value = "1.3.0"
        fake_contract.functions.nonce.return_value.call.return_value = 7
        mock_get_contract.return_value = fake_contract

        rpc = "https://a.example/KEY1, https://b.example/KEY2"

        safe_tx = propose_tx._create_signed_safe_tx_for_safe(
            rpc,
            self.safe_global,
            to="0x2222222222222222222222222222222222222222",
            calldata="0x",
            operation=0,
        )

        # Chain reads must go through the fallback-capable get_w3, which receives
        # the raw (possibly comma-joined) RPC string.
        mock_get_w3.assert_called_once_with(rpc)

        # Values are threaded explicitly into SafeTx so signing needs no node.
        self.assertEqual(safe_tx.chain_id, 56)
        self.assertEqual(safe_tx.safe_nonce, 7)
        self.assertEqual(safe_tx.safe_version, "1.3.0")

        # Signing produced a signature offline (no EthereumClient network access).
        self.assertTrue(len(safe_tx.signatures) > 0)


if __name__ == "__main__":
    unittest.main()
