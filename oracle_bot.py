from base import *


def run_oracle_validation(
    source_core_address: str,
    target_core_address: str,
    source_rpc: str,
    target_rpc: str,
    source_core_helper: str,
    target_core_helper: str,
) -> bool:
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
    # requirement: source.inboundNonce == target.outboundNonce && source.outboundNonce == target.inboundNonce
    if source_nonces[0] != target_nonces[1] or source_nonces[1] != target_nonces[0]:
        print_colored(
            "OFT transfers in progress. source chain {} target chain {}".format(
                source_nonces, target_nonces
            ),
            "yellow",
        )
        return False

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
    if remaining_time <= 24 * 3600 or oracle_value != secure_value:
        print_colored(
            "Oracle needs update: remaining time {}, oracle value {}, actual value {}".format(
                remaining_time, oracle_value, secure_value
            ),
            "red",
        )
        return False
    else:
        print_colored(
            "Oracle is up to date. Remaining time: {} hours".format(
                round(remaining_time / 3600, 1)
            ),
            "green",
        )
        return True


if __name__ == "__main__":
    import os
    import dotenv

    dotenv.load_dotenv()

    source_rpc = os.getenv("SOURCE_RPC")
    target_rpc = os.getenv("TARGET_RPC")
    source_core_helper = os.getenv("SOURCE_CORE_HELPER")
    target_core_helper = os.getenv("TARGET_CORE_HELPER")

    source_core_address = os.getenv("SOURCE_CORE_ADDRESS")
    target_core_address = os.getenv("TARGET_CORE_ADDRESS")

    run_oracle_validation(
        source_core_address=source_core_address,
        target_core_address=target_core_address,
        source_rpc=source_rpc,
        target_rpc=target_rpc,
        source_core_helper=source_core_helper,
        target_core_helper=target_core_helper,
    )
