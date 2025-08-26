import requests
from urllib.parse import urljoin
from web3 import Web3, constants
from eth_account import Account
from safe_eth.safe import SafeTx
from safe_eth.eth import EthereumClient


def get_client_gateway_version(api_url: str) -> str:
    url = urljoin(api_url, "/about")
    response = requests.get(url, headers={"Accept": "application/json"})
    if response.status_code != 200:
        raise Exception(f"Failed to get client gateway version: {response.status_code}")
    result = response.json()
    if result["name"] != "safe-client-gateway":
        raise Exception(f"Provided API URL is not a client gateway: {api_url}")
    return result["version"]


def get_nonce(api_url: str, chainId: int, safe_address: str) -> int:
    url = urljoin(api_url, f"/v1/chains/{chainId}/safes/{safe_address}/nonces")
    response = requests.get(url, headers={"Accept": "application/json"})
    if response.status_code != 200:
        raise Exception(
            f"Failed to get nonces: {response.status_code} - {response.text}"
        )
    return response.json()["currentNonce"]


def preview_safe_tx(
    api_url: str, chainId: int, safe_address: str, to: str, calldata: str
) -> SafeTx:
    url = urljoin(api_url, f"/v1/chains/{chainId}/transactions/{safe_address}/preview")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    body = {
        "operation": 0,
        "value": "0",
        "to": to,
        "data": calldata,
    }
    response = requests.post(url, headers=headers, json=body)
    if response.status_code != 200:
        raise Exception(
            f"Failed to preview safe tx: {response.status_code} - {response.text}"
        )
    return response.json()


def create_calldata(spender_address: str, amount: int) -> str:
    abi = [
        {
            "constant": False,
            "inputs": [
                {"name": "spender", "type": "address"},
                {"name": "amount", "type": "uint256"},
            ],
            "name": "approve",
            "outputs": [{"name": "", "type": "bool"}],
            "payable": False,
            "stateMutability": "nonpayable",
            "type": "function",
        }
    ]
    contract = Web3().eth.contract(address=constants.ADDRESS_ZERO, abi=abi)
    calldata = contract.encode_abi("approve", args=[spender_address, amount])
    return calldata


def create_signed_safe_tx(
    rpc_url: str, safe_address: str, private_key: str, to: str, calldata: str
) -> SafeTx:
    safe_tx = SafeTx(
        ethereum_client=EthereumClient(rpc_url),
        safe_address=safe_address,
        to=to,
        value=0,
        data=calldata,
        operation=0,
        safe_tx_gas=0,
        base_gas=0,
        gas_price=0,
        gas_token=None,
        refund_receiver=None,
    )
    safe_tx.sign(private_key)
    return safe_tx


def propose_safe_tx(api_url: str, safe_tx: SafeTx):
    url = urljoin(
        api_url, f"/v1/chains/{chainId}/transactions/{safe_tx.safe_address}/propose"
    )
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    body = {
        "to": str(safe_tx.to),
        "value": str(safe_tx.value),
        "data": "0x" + safe_tx.data.hex(),
        "operation": safe_tx.operation,
        "baseGas": str(safe_tx.base_gas),
        "gasPrice": str(safe_tx.gas_price),
        "gasToken": str(safe_tx.gas_token),
        "refundReceiver": str(safe_tx.refund_receiver),
        "nonce": str(safe_tx.safe_nonce),
        "safeTxGas": str(safe_tx.safe_tx_gas),
        "safeTxHash": "0x" + safe_tx.safe_tx_hash.hex(),
        "sender": safe_tx.signers[0],
        "signature": "0x" + safe_tx.signatures.hex(),
        "origin": '{"url":"https://safe.mainnet.frax.com/tx-builder/","name":"Transaction Builder"}',
    }
    response = requests.post(url, headers=headers, json=body)
    if response.status_code != 200:
        raise Exception(
            f"Failed to preview safe tx: {response.status_code} - {response.text}"
        )
    return response.json()


if __name__ == "__main__":
    import dotenv
    import sys
    from pathlib import Path

    # Add src directory to path to import config module
    src_path = Path(__file__).parent.parent
    sys.path.insert(0, str(src_path))

    from config.read_config import read_config
    from web3_scripts.base import get_w3

    dotenv.load_dotenv()

    # Read configuration from config.json
    config_path = src_path.parent / "config.json"
    config = read_config(str(config_path))

    # Find for FRAX source
    source = next((s for s in config.sources if s.name == "FRAX"), None)
    if not source:
        raise Exception("FRAX source not found")
    # w3 = get_w3(source.rpc)
    chainId = 252
    # safe_address = source.safe_global.safe_address
    # api_url = source.safe_global.api_url

    # create_safe_tx(source.rpc, source.safe_global.safe_address, source.safe_global.proposer_private_key)
    calldata = create_calldata("0x35b9a5EA6D8124FF2B8A72d7f67C6219864F4B5b", 1)
    to = "0xFC00000000000000000000000000000000000006"
    print(to)
    print(calldata)
    print(
        f"Proposer address: {Account.from_key(source.safe_global.proposer_private_key).address}"
    )
    # preview = preview_safe_tx(
    #     source.safe_global.api_url,
    #     chainId,
    #     source.safe_global.safe_address,
    #     "0xFC00000000000000000000000000000000000006",
    #     calldata,
    # )
    # print(preview)

    safe_tx = create_signed_safe_tx(
        source.rpc,
        source.safe_global.safe_address,
        source.safe_global.proposer_private_key,
        to,
        calldata,
    )
    propose_safe_tx(source.safe_global.api_url, safe_tx)
