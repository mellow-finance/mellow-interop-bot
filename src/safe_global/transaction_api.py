import requests
from safe_eth.safe import SafeTx
from safe_global.common import (
    ThresholdWithOwners,
    PendingTransactionInfo,
    validate_confirmation_accounting,
    validate_transaction_id,
    retry_with_backoff,
)


def get_version(api_url: str, api_key: str) -> str:
    url = f"{api_url.rstrip('/')}/api/v1/about"
    headers = {"Accept": "application/json", "Authorization": f"Bearer {api_key}"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(
            f"Failed to get transaction api version: {response.status_code}"
        )
    result = response.json()
    if result["name"] != "Safe Transaction Service":
        raise Exception(f"Provided API URL is not a transaction api: {api_url}")
    return result["version"]


def propose_safe_tx(api_url: str, api_key: str, safe_tx: SafeTx) -> str:
    url = f"{api_url.rstrip('/')}/api/v2/safes/{safe_tx.safe_address}/multisig-transactions"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
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
        "contractTransactionHash": "0x" + safe_tx.safe_tx_hash.hex(),
        "sender": safe_tx.signers[0],
        "signature": "0x" + safe_tx.signatures.hex(),
    }

    def propose():
        response = requests.post(url, headers=headers, json=body, timeout=15)
        if response.status_code != 201:
            raise Exception(
                f"Failed to propose safe tx: {response.status_code} - {response.text}"
            )
        return body["contractTransactionHash"]

    return retry_with_backoff(propose, max_attempts=3, backoff_factor=2.0)


def _get_queued_transactions(
    api_url: str,
    api_key: str,
    safe_address: str,
    safe_nonce: int,
    to: str,
):
    url = f"{api_url.rstrip('/')}/api/v2/safes/{safe_address}/multisig-transactions?nonce__gte={safe_nonce}&to={to}&executed=false&trusted=true"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    def fetch():
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            raise Exception(
                f"Failed to get queued transactions: {response.status_code} - {response.text}"
            )
        return response.json()["results"]

    return retry_with_backoff(fetch, max_attempts=5, backoff_factor=2.0)


def _get_queued_transaction_by_calldata(
    api_url: str,
    api_key: str,
    safe_address: str,
    safe_nonce: int,
    to: str,
    calldata: str,
):
    queued_transactions = _get_queued_transactions(
        api_url, api_key, safe_address, safe_nonce, to
    )
    for transaction in queued_transactions:
        calldata_from_tx = transaction.get("data")
        if calldata_from_tx is None:
            raise Exception(f"Cannot get 'data' from transaction: {transaction}")

        to_from_tx = transaction.get("to")
        if to_from_tx is None:
            raise Exception(f"Cannot get 'to' address from transaction: {transaction}")

        if calldata_from_tx == calldata and to_from_tx == to:
            return transaction

    return None


def _get_owners_and_threshold(
    api_url: str, api_key: str, safe_address: str
) -> ThresholdWithOwners:
    """
    Get Safe owners and threshold information.
    """
    url = f"{api_url.rstrip('/')}/api/v1/safes/{safe_address}"
    headers = {"Accept": "application/json", "Authorization": f"Bearer {api_key}"}

    def fetch():
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            raise Exception(
                f"Failed to get Safe info: {response.status_code} - {response.text}"
            )

        data = response.json()

        threshold = data.get("threshold")
        owners = data.get("owners", [])

        if threshold is None:
            raise Exception(f"Missing 'threshold' field in API response: {data}")

        if not isinstance(owners, list):
            raise Exception(f"'owners' field must be a list in API response: {data}")

        if len(owners) == 0:
            raise Exception(f"No owners found in API response: {data}")

        return ThresholdWithOwners(threshold=threshold, owners=owners)

    return retry_with_backoff(fetch, max_attempts=5, backoff_factor=2.0)


def get_queued_transaction(
    api_url: str,
    api_key: str,
    safe_address: str,
    safe_nonce: int,
    to: str,
    calldata: str,
) -> PendingTransactionInfo:
    transaction = _get_queued_transaction_by_calldata(
        api_url, api_key, safe_address, safe_nonce, to, calldata
    )
    if transaction is None:
        return None

    threshold_with_owners = _get_owners_and_threshold(api_url, api_key, safe_address)

    # Extract confirmed owners from transaction confirmations
    confirmations = [conf["owner"] for conf in transaction.get("confirmations", [])]

    # Calculate missing confirmations (owners who haven't confirmed yet)
    missing_confirmations = [
        owner for owner in threshold_with_owners.owners if owner not in confirmations
    ]

    # Create compound ID as specified
    safe_tx_hash = transaction.get("safeTxHash")
    if not safe_tx_hash:
        raise Exception(f"Missing safeTxHash in transaction: {transaction}")

    transaction_id = f"multisig_{safe_address}_{safe_tx_hash}"

    # Get required confirmations from transaction or use threshold
    required_confirmations = transaction.get(
        "confirmationsRequired", threshold_with_owners.threshold
    )

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
