import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from main import propose_tx_to_update_oracle, OracleData, SafeProposal
from config.read_config import SourceConfig, SafeGlobal, Deployment
from web3_scripts.oracle_script import OracleValidationResult
from safe_global.common import PendingTransactionInfo, ThresholdWithOwners


class TestProposeTxToUpdateOracle(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures with mock data"""
        
        # Create mock SafeGlobal configurations
        self.safe_global_1 = SafeGlobal(
            safe_address="0x1234567890123456789012345678901234567890",
            proposer_private_key="0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            api_url="https://safe-api-1.example.com",
            api_key="test-api-key-1",
            web_client_url="https://safe-web-1.example.com",
            eip_3770="eth"
        )
        
        self.safe_global_2 = SafeGlobal(
            safe_address="0x2345678901234567890123456789012345678901",
            proposer_private_key="0xbcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890a",
            api_url="https://safe-api-2.example.com",
            api_key="test-api-key-2",
            web_client_url="https://safe-web-2.example.com",
            eip_3770="bsc"
        )
        
        # Create mock SourceConfig objects
        self.source_config_1 = SourceConfig(
            name="Ethereum",
            rpc="https://eth-rpc.example.com",
            source_core_helper="0x1111111111111111111111111111111111111111",
            deployments=(
                Deployment(
                    name="ETH-BSC",
                    source_core="0x2222222222222222222222222222222222222222",
                    target_core="0x3333333333333333333333333333333333333333"
                ),
            ),
            safe_global=self.safe_global_1
        )
        
        self.source_config_2 = SourceConfig(
            name="BSC",
            rpc="https://bsc-rpc.example.com",
            source_core_helper="0x4444444444444444444444444444444444444444",
            deployments=(
                Deployment(
                    name="BSC-ETH",
                    source_core="0x5555555555555555555555555555555555555555",
                    target_core="0x6666666666666666666666666666666666666666"
                ),
            ),
            safe_global=self.safe_global_2
        )
        
        # Create source config without safe_global (should be skipped)
        self.source_config_no_safe = SourceConfig(
            name="Polygon",
            rpc="https://polygon-rpc.example.com",
            source_core_helper="0x7777777777777777777777777777777777777777",
            deployments=(),
            safe_global=None
        )
        
        # Create mock oracle validation results
        self.oracle_validation_expired = OracleValidationResult(
            oracle_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            chain_id=1,
            oracle_value=1000000000000000000,  # 1 ETH
            actual_value=1100000000000000000,  # 1.1 ETH
            remaining_time=0,
            source_nonces=(100, 101),
            target_nonces=(200, 201),
            transfer_in_progress=False,
            almost_expired=True,
            incorrect_value=False
        )
        
        self.oracle_validation_incorrect = OracleValidationResult(
            oracle_address="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            chain_id=1,
            oracle_value=2000000000000000000,  # 2 ETH
            actual_value=2200000000000000000,  # 2.2 ETH
            remaining_time=3600,
            source_nonces=(102, 103),
            target_nonces=(202, 203),
            transfer_in_progress=False,
            almost_expired=False,
            incorrect_value=True
        )
        
        self.oracle_validation_transfer_in_progress = OracleValidationResult(
            oracle_address="0xcccccccccccccccccccccccccccccccccccccccc",
            chain_id=56,
            oracle_value=3000000000000000000,  # 3 BNB
            actual_value=3300000000000000000,  # 3.3 BNB
            remaining_time=0,
            source_nonces=(104, 105),
            target_nonces=(204, 205),
            transfer_in_progress=True,  # Should be skipped
            almost_expired=True,
            incorrect_value=False
        )
        
        self.oracle_validation_no_update_needed = OracleValidationResult(
            oracle_address="0xdddddddddddddddddddddddddddddddddddddddd",
            chain_id=56,
            oracle_value=4000000000000000000,  # 4 BNB
            actual_value=4000000000000000000,  # Same value
            remaining_time=7200,
            source_nonces=(106, 107),
            target_nonces=(206, 207),
            transfer_in_progress=False,
            almost_expired=False,  # Not expired
            incorrect_value=False  # Correct value
        )
        
        self.oracle_validation_bsc_expired = OracleValidationResult(
            oracle_address="0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
            chain_id=56,
            oracle_value=5000000000000000000,  # 5 BNB
            actual_value=5500000000000000000,  # 5.5 BNB
            remaining_time=0,
            source_nonces=(108, 109),
            target_nonces=(208, 209),
            transfer_in_progress=False,
            almost_expired=True,
            incorrect_value=False
        )
        
        # Create mock oracle data
        self.oracle_data_expired = OracleData(
            name="ETH-BSC Oracle 1",
            validation=self.oracle_validation_expired
        )
        
        self.oracle_data_incorrect = OracleData(
            name="ETH-BSC Oracle 2", 
            validation=self.oracle_validation_incorrect
        )
        
        self.oracle_data_transfer_in_progress = OracleData(
            name="BSC-ETH Oracle 1",
            validation=self.oracle_validation_transfer_in_progress
        )
        
        self.oracle_data_no_update_needed = OracleData(
            name="BSC-ETH Oracle 2",
            validation=self.oracle_validation_no_update_needed
        )
        
        self.oracle_data_bsc_expired = OracleData(
            name="BSC-ETH Oracle 3",
            validation=self.oracle_validation_bsc_expired
        )
        
        self.oracle_data_no_validation = OracleData(
            name="Failed Oracle",
            validation=None  # Should be skipped
        )
        
        # Create mock pending transaction
        self.mock_pending_transaction = PendingTransactionInfo(
            id="multisig_0x1234567890123456789012345678901234567890_0xabcdef",
            number_of_required_confirmations=2,
            threshold_with_owners=ThresholdWithOwners(
                threshold=2,
                owners=[
                    "0x1111111111111111111111111111111111111111",
                    "0x2222222222222222222222222222222222222222",
                    "0x3333333333333333333333333333333333333333"
                ]
            ),
            confirmations=["0x1111111111111111111111111111111111111111"],
            missing_confirmations=[
                "0x2222222222222222222222222222222222222222",
                "0x3333333333333333333333333333333333333333"
            ]
        )

    @patch('main.propose_tx_if_needed')
    def test_single_source_single_oracle_expired(self, mock_propose_tx):
        """Test with single source and single expired oracle"""
        mock_propose_tx.return_value = self.mock_pending_transaction
        
        oracle_validation_results = [
            (self.source_config_1, self.oracle_data_expired)
        ]
        
        result = propose_tx_to_update_oracle(oracle_validation_results)
        
        # Verify result structure
        self.assertEqual(len(result), 1)
        source, proposal = result[0]
        
        # Verify source is correct
        self.assertEqual(source, self.source_config_1)
        
        # Verify proposal structure
        self.assertIsInstance(proposal, SafeProposal)
        self.assertEqual(proposal.method, "setValue")
        self.assertEqual(proposal.deployment_names, ["ETH-BSC Oracle 1"])
        self.assertEqual(len(proposal.calls), 1)
        self.assertEqual(proposal.calls[0], ("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", [1100000000000000000]))
        self.assertEqual(proposal.transaction, self.mock_pending_transaction)
        
        # Verify propose_tx_if_needed was called correctly
        mock_propose_tx.assert_called_once_with(
            "Oracle",
            "setValue", 
            [("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", [1100000000000000000])],
            self.source_config_1
        )

    @patch('main.propose_tx_if_needed')
    def test_single_source_multiple_oracles_batched(self, mock_propose_tx):
        """Test with single source and multiple oracles that should be batched"""
        mock_propose_tx.return_value = self.mock_pending_transaction
        
        oracle_validation_results = [
            (self.source_config_1, self.oracle_data_expired),
            (self.source_config_1, self.oracle_data_incorrect)
        ]
        
        result = propose_tx_to_update_oracle(oracle_validation_results)
        
        # Verify result structure
        self.assertEqual(len(result), 1)
        source, proposal = result[0]
        
        # Verify source is correct
        self.assertEqual(source, self.source_config_1)
        
        # Verify proposal has both oracles batched
        self.assertEqual(proposal.method, "setValue")
        self.assertEqual(set(proposal.deployment_names), {"ETH-BSC Oracle 1", "ETH-BSC Oracle 2"})
        self.assertEqual(len(proposal.calls), 2)
        
        # Check both calls are present (order might vary due to dict iteration)
        expected_calls = [
            ("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", [1100000000000000000]),
            ("0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", [2200000000000000000])
        ]
        for expected_call in expected_calls:
            self.assertIn(expected_call, proposal.calls)
        
        # Verify propose_tx_if_needed was called with batched calls
        mock_propose_tx.assert_called_once()
        args = mock_propose_tx.call_args[0]
        self.assertEqual(args[0], "Oracle")
        self.assertEqual(args[1], "setValue")
        self.assertEqual(len(args[2]), 2)
        self.assertEqual(args[3], self.source_config_1)

    @patch('main.propose_tx_if_needed')
    def test_multiple_sources_separate_proposals(self, mock_propose_tx):
        """Test with multiple sources - should create separate proposals"""
        mock_propose_tx.return_value = self.mock_pending_transaction
        
        oracle_validation_results = [
            (self.source_config_1, self.oracle_data_expired),
            (self.source_config_2, self.oracle_data_bsc_expired)
        ]
        
        result = propose_tx_to_update_oracle(oracle_validation_results)
        
        # Verify result structure - should have 2 separate proposals
        self.assertEqual(len(result), 2)
        
        # Extract sources and proposals
        sources = [source for source, _ in result]
        proposals = [proposal for _, proposal in result]
        
        # Verify both sources are present and unique
        self.assertIn(self.source_config_1, sources)
        self.assertIn(self.source_config_2, sources)
        self.assertEqual(len(set(sources)), 2)  # Ensure sources are unique
        
        # Verify each proposal has correct data
        for source, proposal in result:
            self.assertIsInstance(proposal, SafeProposal)
            self.assertEqual(proposal.method, "setValue")
            self.assertEqual(len(proposal.calls), 1)
            self.assertEqual(proposal.transaction, self.mock_pending_transaction)
            
            if source == self.source_config_1:
                self.assertEqual(proposal.deployment_names, ["ETH-BSC Oracle 1"])
                self.assertEqual(proposal.calls[0], ("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", [1100000000000000000]))
            elif source == self.source_config_2:
                self.assertEqual(proposal.deployment_names, ["BSC-ETH Oracle 3"])
                self.assertEqual(proposal.calls[0], ("0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", [5500000000000000000]))
        
        # Verify propose_tx_if_needed was called twice (once per source)
        self.assertEqual(mock_propose_tx.call_count, 2)

    @patch('main.propose_tx_if_needed')
    def test_filtering_logic(self, mock_propose_tx):
        """Test that oracles are properly filtered based on validation criteria"""
        mock_propose_tx.return_value = self.mock_pending_transaction
        
        oracle_validation_results = [
            (self.source_config_1, self.oracle_data_expired),  # Should be included
            (self.source_config_2, self.oracle_data_transfer_in_progress),  # Should be skipped
            (self.source_config_2, self.oracle_data_no_update_needed),  # Should be skipped
            (self.source_config_2, self.oracle_data_no_validation),  # Should be skipped
            (self.source_config_2, self.oracle_data_bsc_expired)  # Should be included
        ]
        
        result = propose_tx_to_update_oracle(oracle_validation_results)
        
        # Should have 2 proposals (one for source_config_1, one for source_config_2)
        self.assertEqual(len(result), 2)
        
        # Find proposals for each source
        source1_proposal = None
        source2_proposal = None
        
        for source, proposal in result:
            if source == self.source_config_1:
                source1_proposal = proposal
            elif source == self.source_config_2:
                source2_proposal = proposal
        
        # Verify source1 proposal (should have 1 oracle)
        self.assertIsNotNone(source1_proposal)
        self.assertEqual(len(source1_proposal.calls), 1)
        self.assertEqual(source1_proposal.deployment_names, ["ETH-BSC Oracle 1"])
        
        # Verify source2 proposal (should have 1 oracle, others filtered out)
        self.assertIsNotNone(source2_proposal)
        self.assertEqual(len(source2_proposal.calls), 1)
        self.assertEqual(source2_proposal.deployment_names, ["BSC-ETH Oracle 3"])
        
        # Verify propose_tx_if_needed was called twice
        self.assertEqual(mock_propose_tx.call_count, 2)

    @patch('main.propose_tx_if_needed')
    def test_source_without_safe_global_skipped(self, mock_propose_tx):
        """Test that sources without safe_global configuration are skipped"""
        oracle_validation_results = [
            (self.source_config_no_safe, self.oracle_data_expired)  # Should be skipped
        ]
        
        result = propose_tx_to_update_oracle(oracle_validation_results)
        
        # Should have no results
        self.assertEqual(len(result), 0)
        
        # propose_tx_if_needed should not be called
        mock_propose_tx.assert_not_called()

    @patch('main.propose_tx_if_needed')
    def test_no_oracles_need_update(self, mock_propose_tx):
        """Test when no oracles need updates"""
        oracle_validation_results = [
            (self.source_config_1, self.oracle_data_transfer_in_progress),
            (self.source_config_1, self.oracle_data_no_update_needed),
            (self.source_config_1, self.oracle_data_no_validation)
        ]
        
        result = propose_tx_to_update_oracle(oracle_validation_results)
        
        # Should have no results
        self.assertEqual(len(result), 0)
        
        # propose_tx_if_needed should not be called
        mock_propose_tx.assert_not_called()

    @patch('main.propose_tx_if_needed')
    @patch('main.print_colored')
    def test_propose_tx_exception_handling(self, mock_print_colored, mock_propose_tx):
        """Test exception handling when propose_tx_if_needed fails"""
        mock_propose_tx.side_effect = Exception("Network error")
        
        oracle_validation_results = [
            (self.source_config_1, self.oracle_data_expired)
        ]
        
        result = propose_tx_to_update_oracle(oracle_validation_results)
        
        # Should still return a result but with transaction=None
        self.assertEqual(len(result), 1)
        source, proposal = result[0]
        
        self.assertEqual(source, self.source_config_1)
        self.assertEqual(proposal.method, "setValue")
        self.assertEqual(len(proposal.calls), 1)
        self.assertIsNone(proposal.transaction)  # Should be None due to exception
        
        # Verify error was logged
        mock_print_colored.assert_called_once()
        error_message = mock_print_colored.call_args[0][0]
        self.assertIn("Error proposing tx for source Ethereum", error_message)
        self.assertIn("Network error", error_message)

    @patch('main.propose_tx_if_needed')
    def test_empty_input(self, mock_propose_tx):
        """Test with empty input list"""
        result = propose_tx_to_update_oracle([])
        
        self.assertEqual(len(result), 0)
        mock_propose_tx.assert_not_called()

    @patch('main.propose_tx_if_needed')
    def test_grouping_by_source_correctness(self, mock_propose_tx):
        """Test that grouping by source works correctly with same source appearing multiple times"""
        mock_propose_tx.return_value = self.mock_pending_transaction
        
        # Same source appears multiple times in different positions
        oracle_validation_results = [
            (self.source_config_1, self.oracle_data_expired),
            (self.source_config_2, self.oracle_data_bsc_expired),
            (self.source_config_1, self.oracle_data_incorrect),  # Same source again
        ]
        
        result = propose_tx_to_update_oracle(oracle_validation_results)
        
        # Should have exactly 2 results (one per unique source)
        self.assertEqual(len(result), 2)
        
        # Extract sources
        result_sources = [source for source, _ in result]
        
        # Verify each source appears exactly once
        self.assertEqual(len(set(result_sources)), 2)
        self.assertIn(self.source_config_1, result_sources)
        self.assertIn(self.source_config_2, result_sources)
        
        # Find the proposal for source_config_1
        source1_proposal = None
        for source, proposal in result:
            if source == self.source_config_1:
                source1_proposal = proposal
                break
        
        # Verify source1 has both oracles batched
        self.assertIsNotNone(source1_proposal)
        self.assertEqual(len(source1_proposal.calls), 2)
        self.assertEqual(set(source1_proposal.deployment_names), {"ETH-BSC Oracle 1", "ETH-BSC Oracle 2"})


if __name__ == '__main__':
    unittest.main()
