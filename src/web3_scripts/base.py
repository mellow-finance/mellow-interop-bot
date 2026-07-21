import json
import time
from web3 import Web3
from web3.contract import Contract
from web3.providers.rpc import HTTPProvider
from eth_account import Account
from web3.middleware import ExtraDataToPOAMiddleware


BLOCK_GAP = 10000
SECURE_INTERVAL = 5 * 60  # 5 minutes

RETRY_ATTEMPTS_PER_ENDPOINT = 3
RETRY_DELAY_SECONDS = 0.25
RETRY_BACKOFF_MULTIPLIER = 2


def add_color(text: str, color="yellow") -> str:
    if color == "red":
        text = "\033[31m" + text + "\033[0m"
    elif color == "green":
        text = "\033[32m" + text + "\033[0m"
    elif color == "yellow":
        text = "\033[33m" + text + "\033[0m"
    return text


def print_colored(text: str, color="yellow") -> str:
    print(add_color(text, color))


class FallbackHTTPProvider(HTTPProvider):
    """HTTPProvider that fails over across multiple endpoints per request.

    Each endpoint is attempted ``attempts_per_endpoint`` times before moving on
    to the next one. Between retries of the SAME endpoint the delay starts at
    ``retry_delay_seconds`` and is multiplied by ``backoff_multiplier`` after
    each wait; the backoff resets when failing over to the next endpoint, which
    happens immediately (no delay on switch). For two endpoints with the
    defaults (3 attempts, 0.25s, x2) the schedule is:
    try 0 -> 0.25s -> try 0 -> 0.5s -> try 0 -> try 1 -> 0.25s -> try 1 -> 0.5s -> try 1.
    """

    def __init__(
        self,
        endpoint_uris,
        attempts_per_endpoint=RETRY_ATTEMPTS_PER_ENDPOINT,
        retry_delay_seconds=RETRY_DELAY_SECONDS,
        backoff_multiplier=RETRY_BACKOFF_MULTIPLIER,
        **kwargs,
    ):
        uris = [uri.strip() for uri in endpoint_uris if uri and uri.strip()]
        if not uris:
            raise ValueError("FallbackHTTPProvider requires at least one endpoint")
        self._attempts_per_endpoint = attempts_per_endpoint
        self._retry_delay_seconds = retry_delay_seconds
        self._backoff_multiplier = backoff_multiplier
        # Disable web3's built-in per-request retry so this class fully controls
        # the attempt/backoff schedule below.
        kwargs.setdefault("exception_retry_configuration", None)
        super().__init__(uris[0], **kwargs)
        self._providers = [HTTPProvider(uri, **kwargs) for uri in uris]

    def make_request(self, method, params):
        last_error = None
        for index, provider in enumerate(self._providers):
            delay = self._retry_delay_seconds
            for attempt in range(self._attempts_per_endpoint):
                if attempt > 0:
                    time.sleep(delay)
                    delay *= self._backoff_multiplier
                # Log every attempt except the very first (RPC index only, never
                # the URL, which may contain an API key).
                if index > 0 or attempt > 0:
                    print_colored(
                        f"Retrying with RPC #{index}, attempt {attempt + 1}...",
                        "yellow",
                    )
                try:
                    response = provider.make_request(method, params)
                    self.endpoint_uri = provider.endpoint_uri
                    return response
                except Exception as e:
                    last_error = e
        raise ConnectionError(
            f"All {len(self._providers)} RPC endpoint(s) failed for method {method} "
            f"after {self._attempts_per_endpoint} attempt(s) each"
        ) from last_error


def get_w3(rpc: str) -> Web3:
    endpoints = [uri.strip() for uri in rpc.split(",") if uri.strip()]
    if not endpoints:
        raise ValueError("No RPC endpoint provided")
    provider = (
        Web3.HTTPProvider(endpoints[0])
        if len(endpoints) == 1
        else FallbackHTTPProvider(endpoints)
    )
    w3 = Web3(provider)
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def get_contract(w3: Web3, address: str, name: str) -> Contract:
    with open("./abi/{}.json".format(name), "r") as f:
        abi = json.load(f)
        return w3.eth.contract(address=w3.to_checksum_address(address), abi=abi)


def execute(contractFunction, value: int, operator_pk: str):
    operator_address = Account.from_key(operator_pk).address
    w3 = contractFunction.w3

    operator_balance = w3.eth.get_balance(operator_address)
    if operator_balance < value:
        raise Exception(
            "Operator balance is too low: {}. Required for LayerZero payment: {}".format(
                operator_balance / 1e18, value / 1e18
            )
        )

    base_fee = w3.eth.get_block("latest").baseFeePerGas * 105 // 100
    try:
        max_priority_fee = min(w3.eth.max_priority_fee * 3, w3.to_wei(10, "gwei"))
    except:
        max_priority_fee = w3.to_wei(2, "gwei")

    try:
        gas = (
            contractFunction.estimate_gas(
                {"from": Web3.to_checksum_address(operator_address), "value": value}
            )
            * 105
            // 100
        )
    except Exception as e:
        raise Exception("Gas estimation failed: {}".format(e))

    require_value_for_transaction_execution = (
        gas * (base_fee + max_priority_fee) + value
    )
    if operator_balance < require_value_for_transaction_execution:
        raise Exception(
            "Operator balance is too low: {}. Required for transaction execution: {}".format(
                operator_balance / 1e18, require_value_for_transaction_execution / 1e18
            )
        )

    transaction = contractFunction.build_transaction(
        {
            "gas": gas,
            "maxFeePerGas": base_fee + max_priority_fee,
            "maxPriorityFeePerGas": max_priority_fee,
            "value": value,
            "from": operator_address,
            "nonce": w3.eth.get_transaction_count(operator_address),
        }
    )
    signed_txn = w3.eth.account.sign_transaction(transaction, private_key=operator_pk)
    tx = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
    print("Transaction sent: {}".format(tx.hex()))
    receipt = w3.eth.wait_for_transaction_receipt(tx)
    print(
        "Transaction mined in block: {}. Chain id: {}".format(
            receipt.blockNumber, w3.eth.chain_id
        )
    )


def get_block_before_timestamp(w3: Web3, timestamp: int) -> int:
    latest_block = w3.eth.get_block("latest")
    from_block = w3.eth.get_block(latest_block.number - BLOCK_GAP)
    timespan = latest_block.timestamp - from_block.timestamp
    while timespan == 0:
        from_block = w3.eth.get_block(from_block.number - BLOCK_GAP)
        timespan = latest_block.timestamp - from_block.timestamp
    seconds_per_block = timespan / (latest_block.number - from_block.number)
    block_number_estimate = latest_block.number - int(
        (latest_block.timestamp - timestamp) / seconds_per_block
    )
    block_number_estimate = min(latest_block.number, block_number_estimate)
    block = w3.eth.get_block(block_identifier=block_number_estimate)
    if block.timestamp > timestamp:
        while block.timestamp > timestamp:
            prev_block = w3.eth.get_block(block.number - 1)
            if prev_block.timestamp <= timestamp:
                return prev_block.number
            block = prev_block
    else:
        while block.timestamp <= timestamp:
            if block.number == latest_block.number:
                return block.number
            next_block = w3.eth.get_block(block.number + 1)
            if next_block.timestamp > timestamp:
                return block.number
            block = next_block
    raise Exception("Block not found for timestamp {}".format(timestamp))
