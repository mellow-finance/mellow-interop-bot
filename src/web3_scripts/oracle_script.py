try:
    from .base import *
except ImportError:
    from base import *
from dataclasses import dataclass


@dataclass
class OracleValidationResult:
    oracle_address: str
    chain_id: int
    oracle_value: int
    actual_value: int
    needs_update: bool
    remaining_time: int
    source_nonces: tuple[int, int]
    target_nonces: tuple[int, int]
    transfer_in_progress: bool


def run_oracle_validation(
    source_core_address: str,
    target_core_address: str,
    source_rpc: str,
    target_rpc: str,
    source_core_helper: str,
    target_core_helper: str,
    oracle_freshness_in_seconds: int,
) -> OracleValidationResult:
    source_w3 = get_w3(source_rpc)
    target_w3 = get_w3(target_rpc)

    source_helper = get_contract(
        source_w3, source_core_helper, "SourceHelper"
    ).functions
    target_helper = get_contract(
        target_w3, target_core_helper, "TargetHelper"
    ).functions

    source_core = get_contract(source_w3, source_core_address, "SourceCore").functions
    timestamp = source_w3.eth.get_block("latest").timestamp
    secure_timestamp = timestamp - SECURE_INTERVAL
    source_block = get_block_before_timestamp(source_w3, secure_timestamp)
    target_block = get_block_before_timestamp(target_w3, secure_timestamp)

    source_nonces = source_helper.getNonces(source_core_address).call(
        block_identifier=source_block
    )
    target_nonces = target_helper.getNonces(target_core_address).call(
        block_identifier=target_block
    )

    oracle_address = source_core.oracle().call(block_identifier=source_block)
    oracle = get_contract(source_w3, oracle_address, "Oracle").functions

    oracle_value = oracle.value().call(block_identifier=source_block)
    oracle_timestamp = oracle.lastUpdated().call(block_identifier=source_block)
    oracle_max_age = oracle.maxAge().call(block_identifier=source_block)

    source_value = source_helper.getSourceValue(source_core_address).call(
        block_identifier=source_block
    )
    target_value = target_helper.getTargetValue(target_core_address).call(
        block_identifier=target_block
    )

    total_supply = source_core.totalSupply().call(block_identifier=source_block)
    secure_value = (source_value + target_value) * 10**18 // total_supply
    remaining_time = oracle_timestamp + oracle_max_age - timestamp

    transfer_in_progress = (
        source_nonces[0] != target_nonces[1] or source_nonces[1] != target_nonces[0]
    )
    needs_update = not transfer_in_progress and (
        remaining_time <= oracle_freshness_in_seconds or oracle_value != secure_value
    )

    result = OracleValidationResult(
        oracle_address=oracle_address,
        chain_id=source_w3.eth.chain_id,
        oracle_value=oracle_value,
        actual_value=secure_value,
        needs_update=needs_update,
        remaining_time=remaining_time,
        source_nonces=source_nonces,
        target_nonces=target_nonces,
        transfer_in_progress=transfer_in_progress,
    )

    color = "green"
    if transfer_in_progress:
        color = "yellow"
    elif needs_update:
        color = "red"

    print_colored(format_oracle_validation_result(result), color)

    return result


def format_oracle_validation_result(result: OracleValidationResult) -> str:
    if result.transfer_in_progress:
        return "Oracle(address={}, chain_id={}) has OFT transfers in progress: source nonces {}, target nonces {}".format(
            result.oracle_address,
            result.chain_id,
            result.source_nonces,
            result.target_nonces,
        )

    remaining_time_formatted = (
        f"{round(result.remaining_time / 3600, 1)} hours"
        if result.remaining_time > 3600
        else f"{result.remaining_time} seconds"
    )
    if result.needs_update:
        return "Oracle(address={}, chain_id={}) needs update: remaining time {}, oracle value {}, actual value {}".format(
            result.oracle_address,
            result.chain_id,
            remaining_time_formatted,
            result.oracle_value,
            result.actual_value,
        )
    else:
        return "Oracle(address={}, chain_id={}) is up to date (value={}). Remaining time: {}".format(
            result.oracle_address,
            result.chain_id,
            result.oracle_value,
            remaining_time_formatted,
        )


if __name__ == "__main__":
    import os
    import dotenv

    dotenv.load_dotenv()

    oracle_freshness_in_seconds = int(os.getenv("ORACLE_FRESHNESS_IN_SECONDS", "3600"))
    target_rpc = os.getenv("TARGET_RPC")
    target_core_helper = os.getenv("TARGET_CORE_HELPER")

    deployments = [
        (
            os.getenv("SOURCE_CORE_WSTETH_ADDRESS"),
            os.getenv("TARGET_CORE_WSTETH_ADDRESS"),
            os.getenv("SOURCE_HELPER_LISK_ADDRESS"),
            os.getenv("LISK_RPC"),
        ),
        (
            os.getenv("SOURCE_CORE_MBTC_ADDRESS"),
            os.getenv("TARGET_CORE_MBTC_ADDRESS"),
            os.getenv("SOURCE_HELPER_LISK_ADDRESS"),
            os.getenv("LISK_RPC"),
        ),
        (
            os.getenv("SOURCE_CORE_LSK_ADDRESS"),
            os.getenv("TARGET_CORE_LSK_ADDRESS"),
            os.getenv("SOURCE_HELPER_LISK_ADDRESS"),
            os.getenv("LISK_RPC"),
        ),
        (
            os.getenv("SOURCE_CORE_FRAX_ADDRESS"),
            os.getenv("TARGET_CORE_FRAX_ADDRESS"),
            os.getenv("SOURCE_HELPER_FRAX_ADDRESS"),
            os.getenv("FRAX_RPC"),
        ),
        (
            os.getenv("SOURCE_CORE_CYCLE_ADDRESS"),
            os.getenv("TARGET_CORE_CYCLE_ADDRESS"),
            os.getenv("SOURCE_HELPER_BSC_ADDRESS"),
            os.getenv("BSC_RPC"),
        ),
    ]

    for (
        source_core_address,
        target_core_address,
        source_core_helper,
        source_rpc,
    ) in deployments:
        run_oracle_validation(
            source_core_address=source_core_address,
            target_core_address=target_core_address,
            source_rpc=source_rpc,
            target_rpc=target_rpc,
            source_core_helper=source_core_helper,
            target_core_helper=target_core_helper,
            oracle_freshness_in_seconds=oracle_freshness_in_seconds,
        )
