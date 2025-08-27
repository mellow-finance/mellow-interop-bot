import requests
from urllib.parse import urljoin
from safe_eth.safe import SafeTx
from safe_eth.eth import EthereumClient
from safe_global.common import (
    ThresholdWithOwners,
    PendingTransactionInfo,
    validate_confirmation_accounting,
    validate_transaction_id,
)


def get_version(api_url: str) -> str:
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


def propose_safe_tx(api_url: str, safe_tx: SafeTx) -> str:
    url = urljoin(
        api_url,
        f"/v1/chains/{safe_tx.chain_id}/transactions/{safe_tx.safe_address}/propose",
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
            f"Failed to propose safe tx: {response.status_code} - {response.text}"
        )

    response_data = response.json()
    safe_tx_hash = response_data.get("detailedExecutionInfo", {}).get("safeTxHash")
    if not safe_tx_hash:
        safe_tx_hash = response_data.get("txId").split("_")[-1]

    if not safe_tx_hash:
        raise Exception(
            f"Could not extract safe tx hash from response: {response_data}"
        )

    if safe_tx_hash != body["safeTxHash"]:
        raise Exception(
            f"Safe tx hash mismatch: {safe_tx_hash} != {body['safeTxHash']}"
        )

    return safe_tx_hash


def _get_queued_transactions(api_url: str, chainId: int, safe_address: str):
    url = urljoin(
        api_url,
        f"/v1/chains/{chainId}/safes/{safe_address}/transactions/queued?trusted=true",
    )
    response = requests.get(url, headers={"Accept": "application/json"})
    if response.status_code != 200:
        raise Exception(
            f"Failed to get queued transactions: {response.status_code} - {response.text}"
        )
    results = response.json()["results"]
    return [result for result in results if result.get("type") == "TRANSACTION"]


def _build_safe_tx_hash(
    safe_address: str, chainId: int, nonce: int, to: str, calldata: str, version: str
) -> SafeTx:
    """Internal helper to regenerate a safe tx hash from the calldata."""
    safe_tx = SafeTx(
        ethereum_client=EthereumClient(),
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
        chain_id=chainId,
        safe_nonce=nonce,
        safe_version=version,
    )
    return "0x" + safe_tx.safe_tx_hash.hex()


def _get_queued_transaction_by_calldata(
    api_url: str,
    chain_id: int,
    safe_address: str,
    safe_version: str,
    to: str,
    calldata: str,
):
    queued_transactions = _get_queued_transactions(api_url, chain_id, safe_address)
    for transaction in queued_transactions:
        data = transaction.get("transaction")
        if data is None:
            raise Exception(
                f"Cannot get transaction data from transaction: {transaction}"
            )

        id_parts = data.get("id", "").split("_")
        if len(id_parts) != 3:
            raise Exception(
                f"Cannot get valid transaction id from transaction data: {data}"
            )

        queued_safe_tx_hash = id_parts[-1]
        if queued_safe_tx_hash is None or not queued_safe_tx_hash.startswith("0x"):
            raise Exception(f"Invalid transaction id: {data.get('id')}")

        nonce = data.get("executionInfo", {}).get("nonce")
        if nonce is None:
            raise Exception(
                f"Cannot get nonce from execution info: {data.get('executionInfo')}"
            )

        safe_tx_hash = _build_safe_tx_hash(
            safe_address, chain_id, nonce, to, calldata, safe_version
        )
        if queued_safe_tx_hash == safe_tx_hash:
            return transaction
    return None


def _get_owners_and_threshold(
    api_url: str, chain_id: int, safe_address: str
) -> ThresholdWithOwners:
    """
    Get Safe owners and threshold information from the client gateway API.
    """
    url = urljoin(api_url, f"/v1/chains/{chain_id}/safes/{safe_address}")
    headers = {"Accept": "application/json"}

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(
            f"Failed to get Safe info: {response.status_code} - {response.text}"
        )

    data = response.json()

    threshold = data.get("threshold")
    owners_data = data.get("owners", [])

    if threshold is None:
        raise Exception(f"Missing 'threshold' field in API response: {data}")

    if not isinstance(owners_data, list):
        raise Exception(f"'owners' field must be a list in API response: {data}")

    if len(owners_data) == 0:
        raise Exception(f"No owners found in API response: {data}")

    # Extract owner addresses from the owner objects
    owners = []
    for owner in owners_data:
        if not isinstance(owner, dict):
            raise Exception(f"Owner must be an object: {owner}")

        owner_address = owner.get("value")
        if not owner_address:
            raise Exception(f"Missing 'value' field in owner object: {owner}")

        owners.append(owner_address)

    return ThresholdWithOwners(threshold=threshold, owners=owners)


def get_queued_transaction(
    api_url: str,
    chain_id: int,
    safe_address: str,
    safe_version: str,
    to: str,
    calldata: str,
) -> PendingTransactionInfo:
    transaction = _get_queued_transaction_by_calldata(
        api_url, chain_id, safe_address, safe_version, to, calldata
    )
    threshold_with_owners = _get_owners_and_threshold(api_url, chain_id, safe_address)

    if transaction is None:
        raise Exception(f"No queued transaction found for calldata: {calldata}")

    # Extract transaction data from the client gateway response
    transaction_data = transaction.get("transaction")
    if not transaction_data:
        raise Exception(f"Missing transaction data in response: {transaction}")

    execution_info = transaction_data.get("executionInfo", {})
    if execution_info.get("type") != "MULTISIG":
        raise Exception(
            f"Expected MULTISIG transaction type, got: {execution_info.get('type')}"
        )

    # Extract transaction ID (already in the correct format)
    transaction_id = transaction_data.get("id")
    if not transaction_id:
        raise Exception(f"Missing transaction id in response: {transaction_data}")

    # Get required confirmations and missing signers
    required_confirmations = execution_info.get("confirmationsRequired")
    if required_confirmations is None:
        raise Exception(
            f"Missing confirmationsRequired in executionInfo: {execution_info}"
        )

    # Extract missing signers (owners who haven't confirmed yet)
    missing_signers_data = execution_info.get("missingSigners", [])
    missing_confirmations = [signer["value"] for signer in missing_signers_data]

    # Calculate confirmed owners by finding the difference between all owners and missing ones
    confirmations = [
        owner
        for owner in threshold_with_owners.owners
        if owner not in missing_confirmations
    ]

    # Validate transaction id
    validate_transaction_id(transaction_id, safe_address)

    # Validate confirmations
    validate_confirmation_accounting(
        confirmations, missing_confirmations, threshold_with_owners.owners
    )

    return PendingTransactionInfo(
        id=transaction_id,
        number_of_required_confirmations=required_confirmations,
        threshold_with_owners=threshold_with_owners,
        confirmations=confirmations,
        missing_confirmations=missing_confirmations,
    )
