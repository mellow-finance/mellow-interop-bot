from typing import List, Optional
from web3 import Web3, constants

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
