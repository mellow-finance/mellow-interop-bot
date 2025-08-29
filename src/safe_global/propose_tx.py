import time
from web3 import Web3, constants
from safe_eth.safe import SafeTx
from safe_eth.eth import EthereumClient

from . import client_gateway_api, transaction_api
from .multi_send_call import encode_multi, resolve_multi_send_contract
from .common import PendingTransactionInfo

from web3_scripts import get_contract, print_colored, get_w3
from config import SourceConfig, SafeGlobal


def _create_calldata(contract_name: str, method: str, args: list) -> str:
    contract = get_contract(Web3(), address=constants.ADDRESS_ZERO, name=contract_name)
    calldata = contract.encode_abi(method, args)
    return calldata


def _create_signed_safe_tx(
    rpc_url: str,
    safe_address: str,
    private_key: str,
    to: str,
    calldata: str,
    operation: int,
) -> SafeTx:
    safe_tx = SafeTx(
        ethereum_client=EthereumClient(rpc_url),
        safe_address=safe_address,
        to=to,
        value=0,
        data=calldata,
        operation=operation,
        safe_tx_gas=0,
        base_gas=0,
        gas_price=0,
        gas_token=None,
        refund_receiver=None,
    )
    safe_tx.sign(private_key)
    return safe_tx


def _create_signed_safe_tx_for_source(
    source: SourceConfig, to: str, calldata: str, operation: int
) -> SafeTx:
    safe_tx = _create_signed_safe_tx(
        source.rpc,
        source.safe_global.safe_address,
        source.safe_global.proposer_private_key,
        to,
        calldata,
        operation,
    )
    return safe_tx


def _is_transaction_api(safe: SafeGlobal) -> bool:
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


def _propose_tx_for_source(safe_tx: SafeTx, source: SourceConfig):
    if _is_transaction_api(source.safe_global):
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


def _get_queued_transaction_for_source(
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
    if _is_transaction_api(source.safe_global):
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


def propose_tx_if_needed(
    contract_name: str, method: str, calls: list[tuple[str, list]], source: SourceConfig
) -> PendingTransactionInfo:
    print(
        f"Starting proposing transaction... source: '{source.name}', contract: '{contract_name}', method: '{method}', calls: {calls}..."
    )

    multi_send = len(calls) > 1
    if multi_send:
        to = resolve_multi_send_contract(source.rpc, source.safe_global.safe_address)
        calls_with_calldata = [
            (to, _create_calldata(contract_name, method, args)) for to, args in calls
        ]
        calldata = encode_multi(calls_with_calldata)
        operation = 1  # delegatecall
        print(
            f"Going to propose multi-send transaction to multi-send contract {to} with calldata: {calldata}..."
        )
    else:
        to, args = calls[0]
        calldata = _create_calldata(contract_name, method, args)
        operation = 0  # call
        print(
            f"Going to propose single transaction to {to} with args: {args} (calldata: {calldata})..."
        )

    safe_tx = _create_signed_safe_tx_for_source(source, to, calldata, operation)

    print(f"Trying to find existing transaction...")
    queued_transaction = _get_queued_transaction_for_source(to, calldata, source)
    if queued_transaction:
        print_colored(
            f"Transaction '{queued_transaction.id}' is already queued", "yellow"
        )
        return queued_transaction

    print(f"Proposing transaction: {safe_tx}...")
    tx_hash = _propose_tx_for_source(safe_tx, source)
    print_colored(f"Transaction proposed: {tx_hash}", "green")

    # Transaction might not be immediately created, try getting it again with several attempts
    attempts = 8
    for attempt in range(attempts):
        time.sleep(attempt + 1)

        print(
            f"Trying to get transaction: {tx_hash}... (attempt {attempt + 1} of {attempts})"
        )
        transaction = _get_queued_transaction_for_source(to, calldata, source)
        if transaction:
            tx_id = f"multisig_{source.safe_global.safe_address}_{tx_hash}"
            if transaction.id != tx_id:
                raise Exception(
                    f"Transaction ID mismatch: expected {tx_id}, got {transaction.id}"
                )
            return transaction

    raise Exception(
        f"Transaction not found after {attempts} attempts. Expected transaction hash: {tx_hash}"
    )
