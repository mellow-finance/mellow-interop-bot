import json
from web3 import Web3
from web3.contract import Contract, ContractFunction, ContractFunctions
from eth_account import Account
from web3.middleware import geth_poa_middleware

BLOCK_GAP = 10000

def get_w3(rpc: str) -> Web3:
    w3 = Web3(Web3.HTTPProvider(rpc))
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    return w3

def get_contract(w3: Web3, address: str, name: str) -> Contract:
    with open("./abi/{}.json".format(name), "r") as f:
        abi = json.load(f)
        return w3.eth.contract(address=w3.to_checksum_address(address), abi=abi)


def execute(contractFunction: ContractFunction, value: int, operator_pk: str):
    operator_address = Account.from_key(operator_pk).address
    w3 = contractFunction.web3

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
            contractFunction.estimateGas(
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

    transaction = contractFunction.buildTransaction(
        {
            "gas": gas,
            "maxFeePerGas": base_fee + max_priority_fee,
            "maxPriorityFeePerGas": max_priority_fee,
            "value": value,
            "from": operator_address,
            "nonce": w3.eth.getTransactionCount(operator_address),
        }
    )
    signed_txn = w3.eth.account.signTransaction(transaction, private_key=operator_pk)
    tx = w3.eth.sendRawTransaction(signed_txn.rawTransaction)
    print("Transaction sent: {}".format(tx.hex()))
    receipt = w3.eth.waitForTransactionReceipt(tx)
    print("Transaction mined in block: {}. Chain id: {}".format(receipt.blockNumber, w3.eth.chain_id))


def block_before_timestamp(w3: Web3, timestamp: int) -> int:
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
