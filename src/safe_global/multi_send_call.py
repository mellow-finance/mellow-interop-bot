import sys
import os
from typing import List, Optional
from web3 import Web3, constants
from eth_abi import encode

if __name__ == "__main__":
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from web3_scripts import get_contract, get_w3

# Multi-send contract addresses for different versions
# https://docs.safe.global/advanced/smart-account-supported-networks?expand=1&page=2
multi_send_contracts = {
    "1.5.0": "0xA83c336B20401Af773B6219BA5027174338D1836",
    "1.4.1": "0x9641d764fc13c8B624c04430C7356C1C7C8102e2",
    "1.3.0": "0x40A2aCCbd92BCA938b02010E17A5b8929b49130D",
}


def hex_data_length(hex_data: str) -> int:
    """
    Calculate the byte length of hex data.
    """
    if hex_data.startswith("0x"):
        hex_data = hex_data[2:]
    return len(hex_data) // 2


def encode_packed(to: str, data: str) -> bytes:
    operation = 0
    value = 0
    to_address = Web3.to_checksum_address(to)
    data_length = hex_data_length(data)
    data_bytes = bytes.fromhex(data[2:] if data.startswith("0x") else data)
    return (
        operation.to_bytes(1, "big")
        + Web3.to_bytes(hexstr=to_address)
        + value.to_bytes(32, "big")
        + data_length.to_bytes(32, "big")
        + data_bytes
    )


def encode_multi(calls: List[tuple[str, str]]) -> str:
    if not calls:
        raise ValueError("Cannot create multi-send with empty calls list")

    encoded_calls = []
    for to, data in calls:
        encoded_calls.append(encode_packed(to, data).hex())

    calls_encoded = "0x" + "".join(encoded_calls)

    w3 = Web3()
    contract = get_contract(w3, address=constants.ADDRESS_ZERO, name="SafeMultiSend")
    data = contract.encode_abi("multiSend", [bytes.fromhex(calls_encoded[2:])])

    return data


def resolve_multi_send_contract(rpc_url: str, safe_address: str) -> str:
    w3 = get_w3(rpc_url)
    contract = get_contract(w3, address=safe_address, name="Safe")
    version = contract.functions.VERSION().call()
    contract_address = multi_send_contracts.get(version)
    if contract_address is None:
        raise ValueError(f"No multi-send contract found for version {version}")
    return contract_address


if __name__ == "__main__":

    from safe_eth.safe import SafeTx
    from safe_eth.eth import EthereumClient

    def _build_safe_tx_hash(
        safe_address: str,
        chainId: int,
        nonce: int,
        to: str,
        calldata: str,
        version: str,
    ) -> SafeTx:
        """Internal helper to regenerate a safe tx hash from the calldata."""
        safe_tx = SafeTx(
            ethereum_client=EthereumClient(),
            safe_address=safe_address,
            to=to,
            value=0,
            data=calldata,
            operation=1,
            safe_tx_gas=0,
            base_gas=0,
            gas_price=0,
            gas_token=None,
            refund_receiver=None,
            chain_id=chainId,
            safe_nonce=nonce,
            safe_version=version,
        )
        return "0x" + safe_tx.safe_tx_hash.hex()

    calls = [
        (
            "0x83D65E663B48bd19488a3AB9996175805760dcbF",
            "0x552410770000000000000000000000000000000000000000000000000de0b6b3a7640000",
        ),
        (
            "0xfEf5CE93C866A64B65A553eFE973dd228f44afdC",
            "0x552410770000000000000000000000000000000000000000000000000de0b6b3a7640000",
        ),
        (
            "0xFe5EA142755e82a5364cBC1F7cF4b10c7D929EC2",
            "0x552410770000000000000000000000000000000000000000000000000de0b6b3a7640000",
        ),
    ]

    print(encode_multi(calls) + "\n")

    expected = "0x8d80ff0a0000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000000000000000016b0083d65e663b48bd19488a3ab9996175805760dcbf00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000024552410770000000000000000000000000000000000000000000000000de0b6b3a764000000fef5ce93c866a64b65a553efe973dd228f44afdc00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000024552410770000000000000000000000000000000000000000000000000de0b6b3a764000000fe5ea142755e82a5364cbc1f7cf4b10c7d929ec200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000024552410770000000000000000000000000000000000000000000000000de0b6b3a7640000000000000000000000000000000000000000000000"
    if encode_multi(calls) != expected:
        raise Exception("Encoded multi-send call is not as expected")

    safe_tx = _build_safe_tx_hash(
        "0x62339BF5c4EB32EFAC9482F0277D68957A822641",
        1135,
        5,
        "0x9641d764fc13c8B624c04430C7356C1C7C8102e2",
        encode_multi(calls),
        "1.4.1",
    )

    # "multisig_0x62339BF5c4EB32EFAC9482F0277D68957A822641_0x709c2338478adffdb9058a9436d1af8591a14356312379f405e608a438723024"

    print(safe_tx)
