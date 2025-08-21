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
    remaining_time: int
    source_nonces: tuple[int, int]
    target_nonces: tuple[int, int]
    transfer_in_progress: bool
    almost_expired: bool
    incorrect_value: bool


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
    almost_expired = remaining_time <= oracle_freshness_in_seconds
    incorrect_value = oracle_value != secure_value

    result = OracleValidationResult(
        oracle_address=oracle_address,
        chain_id=source_w3.eth.chain_id,
        oracle_value=oracle_value,
        actual_value=secure_value,
        remaining_time=remaining_time,
        source_nonces=source_nonces,
        target_nonces=target_nonces,
        transfer_in_progress=transfer_in_progress,
        almost_expired=almost_expired,
        incorrect_value=incorrect_value,
    )

    print_oracle_validation_result(result)

    return result


def print_oracle_validation_result(result: OracleValidationResult) -> str:
    if result.transfer_in_progress:
        print_colored(
            "Oracle(address={}, chain_id={}) has OFT transfers in progress: source nonces {}, target nonces {}".format(
                result.oracle_address,
                result.chain_id,
                result.source_nonces,
                result.target_nonces,
            ),
            "yellow",
        )
        return

    remaining_time_formatted = format_remaining_time(result.remaining_time)
    if result.almost_expired or result.incorrect_value:
        print_colored(
            "Oracle(address={}, chain_id={}) needs update: remaining time {}, oracle value {}, actual value {}".format(
                result.oracle_address,
                result.chain_id,
                remaining_time_formatted,
                result.oracle_value,
                result.actual_value,
            ),
            "red",
        )
    else:
        print_colored(
            "Oracle(address={}, chain_id={}) is up to date (value={}). Remaining time: {}".format(
                result.oracle_address,
                result.chain_id,
                result.oracle_value,
                remaining_time_formatted,
            ),
            "green",
        )


def format_remaining_time(remaining_time: int) -> str:
    return (
        f"{round(remaining_time / 3600, 1)} hours"
        if remaining_time > 3600
        else f"{remaining_time} seconds"
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
