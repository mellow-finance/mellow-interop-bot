from web3 import Web3, constants
from safe_eth.safe import SafeTx
from web3_scripts import get_contract, OracleValidationResult
from config.read_config import SafeGlobal

def create_calldata(amount: int) -> str:
    contract = get_contract(Web3(), address=constants.ADDRESS_ZERO, name="Oracle")
    calldata = contract.encode_abi("setValue", args=[amount])
    return calldata


def propose_tx(oracle_validation_result: OracleValidationResult, safe_global: SafeGlobal) -> bool:
    pass