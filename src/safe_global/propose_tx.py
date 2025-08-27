import sys
import os
from web3 import Web3, constants
from safe_eth.safe import SafeTx
from safe_eth.eth import EthereumClient

if __name__ == "__main__":
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from web3_scripts import get_contract, print_colored, get_w3
from config import SourceConfig, SafeGlobal
from safe_global import client_gateway_api, transaction_api, PendingTransactionInfo


def create_calldata(method: str, args: list[str]) -> str:
    contract = get_contract(Web3(), address=constants.ADDRESS_ZERO, name="Oracle")
    calldata = contract.encode_abi(method, args)
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


def create_signed_safe_tx_for_source(
    source: SourceConfig, to: str, method: str, args: list[str]
) -> SafeTx:
    safe_tx = create_signed_safe_tx(
        source.rpc,
        source.safe_global.safe_address,
        source.safe_global.proposer_private_key,
        to,
        create_calldata(method, args),
    )
    return safe_tx


def is_transaction_api(safe: SafeGlobal) -> bool:
    try:
        transaction_api.get_version(safe.api_url, safe.api_key)
        return True
    except Exception:
        try:
            client_gateway_api.get_version(safe.api_url)
        except Exception:
            raise Exception(
                "Unable to resolve API type, please check the API URL and API key"
            )
        return False


def propose_tx_for_source(safe_tx: SafeTx, source: SourceConfig):
    if is_transaction_api(source.safe_global):
        print_colored(
            f"Proposing transaction using Transaction API: {safe_tx}", "yellow"
        )
        return transaction_api.propose_safe_tx(
            source.safe_global.api_url, source.safe_global.api_key, safe_tx
        )
    else:
        print_colored(
            f"Proposing transaction using Client Gateway API: {safe_tx}", "yellow"
        )
        return client_gateway_api.propose_safe_tx(source.safe_global.api_url, safe_tx)


def get_queued_transaction_for_source(
    to: str, calldata: str, source: SourceConfig
) -> PendingTransactionInfo:
    w3 = get_w3(source.rpc)
    chain_id = w3.eth.chain_id
    safe_contract = get_contract(
        w3, address=source.safe_global.safe_address, name="Safe"
    )
    api_url = source.safe_global.api_url
    api_key = source.safe_global.api_key
    safe_address = source.safe_global.safe_address
    if is_transaction_api(source.safe_global):
        nonce = safe_contract.functions.nonce().call()
        return transaction_api.get_queued_transaction(
            api_url,
            api_key,
            safe_address,
            nonce,
            to,
            calldata,
        )
    else:
        version = safe_contract.functions.VERSION().call()
        return client_gateway_api.get_queued_transaction(
            api_url,
            chain_id,
            safe_address,
            version,
            to,
            calldata,
        )


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

    # Find for certain source
    source_name = "BSC"  # "FRAX"
    source = next((s for s in config.sources if s.name == source_name), None)
    if not source:
        raise Exception(f"{source_name} source not found")
    print("--------------------------------")
    print(f"BSC: {source.safe_global.safe_address}")
    print("--------------------------------")

    to = "0x94928C3853eFEf2759A18eD9d249768Eb260dF8C"
    calldata = create_calldata("setValue", [1000000000000000000])
    print(get_queued_transaction_for_source(to, calldata, source))

    # safe_tx = create_signed_safe_tx_for_source(
    #     source,
    #     "0x94928C3853eFEf2759A18eD9d249768Eb260dF8C",
    #     "setValue",
    #     [1000000000000000000],
    # )
    # propose_result = propose_tx_for_source(safe_tx, source)
    # print(propose_result)

    # ----- FRAX
    source_name = "FRAX"  # "FRAX"
    source = next((s for s in config.sources if s.name == source_name), None)
    if not source:
        raise Exception(f"{source_name} source not found")
    print("--------------------------------")
    print(f"FRAX: {source.safe_global.safe_address}")
    print("--------------------------------")

    print(get_queued_transaction_for_source(to, calldata, source))
    # safe_tx = create_signed_safe_tx_for_source(
    #     source,
    #     "0x94928C3853eFEf2759A18eD9d249768Eb260dF8C",
    #     "setValue",
    #     [1000000000000000000],
    # )
    # propose_result = propose_tx_for_source(safe_tx, source)
    # print(propose_result)
