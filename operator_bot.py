from base import *
from oracle_bot import run_oracle_validation
import time

LAYER_ZERO_DUST = 1000_000_000_000


def wait_for_layer_zero_finalization(
    source_helper: ContractFunctions,
    target_helper: ContractFunctions,
    source_core_address: str,
    target_core_address: str,
) -> None:
    iteration = 1
    time.sleep(60)
    while True:
        source_nonces = source_helper.getNonces(source_core_address).call()
        target_nonces = target_helper.getNonces(target_core_address).call()
        # requirement: source.inboundNonce == target.outboundNonce && source.outboundNonce == target.inboundNonce
        if source_nonces[0] != target_nonces[1] or source_nonces[1] != target_nonces[0]:
            print("Waiting for LayerZero finalization ({})...".format(iteration))
            iteration += 1
            time.sleep(60)
        else:
            time.sleep(15)
            break


def wrap_text(text: str, color="yellow") -> str:
    if color == "red":
        return "\033[31m" + text + "\033[0m"
    elif color == "green":
        return "\033[32m" + text + "\033[0m"
    elif color == "yellow":
        return "\033[33m" + text + "\033[0m"
    else:
        return text


def run(
    source_core_address: str,
    target_core_address: str,
    source_rpc: str,
    target_rpc: str,
    source_core_helper: str,
    target_core_helper: str,
    operator_pk: str,
    source_ratio_d3: int,
    max_source_ratio_d3: int,
) -> None:
    if not run_oracle_validation(
        source_core_address,
        target_core_address,
        source_rpc,
        target_rpc,
        source_core_helper,
        target_core_helper,
    ):
        raise Exception("Oracle validation failed")

    source_w3 = get_w3(source_rpc)
    target_w3 = get_w3(target_rpc)

    source_helper = get_contract(
        source_w3, source_core_helper, "SourceHelper"
    ).functions
    target_helper = get_contract(
        target_w3, target_core_helper, "TargetHelper"
    ).functions

    source_core = get_contract(source_w3, source_core_address, "SourceCore").functions
    target_core = get_contract(target_w3, target_core_address, "TargetCore").functions

    source_block = source_w3.eth.get_block("latest").number
    target_block = target_w3.eth.get_block("latest").number

    source_nonces = source_helper.getNonces(source_core_address).call(
        block_identifier=source_block
    )
    target_nonces = target_helper.getNonces(target_core_address).call(
        block_identifier=target_block
    )
    # requirement: source.inboundNonce == target.outboundNonce && source.outboundNonce == target.inboundNonce
    if source_nonces[0] != target_nonces[1] or source_nonces[1] != target_nonces[0]:
        raise Exception(
            "OFT transfers in progress. source chain {} target chain {}".format(
                source_nonces, target_nonces
            )
        )

    source_value = source_helper.getSourceValue(source_core_address).call(
        block_identifier=source_block
    )
    target_value = target_helper.getTargetValue(target_core_address).call(
        block_identifier=target_block
    )
    withdrawal_data = source_helper.getWithdrawalData(source_core_address).call(
        block_identifier=source_block
    )
    withdrawal_demand = withdrawal_data[0]
    total_supply = withdrawal_data[1]
    withdrawal_demand = (
        (source_value + target_value) * withdrawal_demand // total_supply
    )

    if source_value + target_value <= withdrawal_demand:
        raise Exception(
            "Withdrawal demand is greater or equal to total assets. Invalid state."
        )

    """

    
    """

    current_ratio_d3 = int(
        1000
        * (source_value - withdrawal_demand)
        // (source_value + target_value - withdrawal_demand)
    )

    print(
        "Source value: {}. Target value: {}. Withdrawal demand: {}".format(
            source_value, target_value, withdrawal_demand
        )
    )

    if current_ratio_d3 < 0:
        assets_deficit = (
            (source_ratio_d3 - current_ratio_d3)
            * (source_value + target_value - withdrawal_demand)
            // 1000
        )
        assets_deficit = (assets_deficit // LAYER_ZERO_DUST + 1) * LAYER_ZERO_DUST
        print(
            "Assets deficit: {}. Current ratio: {}%".format(
                assets_deficit, current_ratio_d3 / 10
            )
        )
        data = target_helper.getAmounts(target_core_address, assets_deficit).call()
        if data[2] > 0:
            print(wrap_text("TargetCore.redeem({})".format(data[2])))
            execute(target_core.redeem(data[2]), 0, operator_pk)
        if data[1]:
            print(wrap_text("TargetCore.claim({})".format(data[1].hex())))
            execute(target_core.claim(data[1].hex()), 0, operator_pk)
        if data[0] > 0:
            value = target_helper.quotePushToSource(target_core_address).call()
            print(
                wrap_text(
                    "TargetCore.pushToSource{{value:{}}}({})".format(value, data[0])
                )
            )
            execute(
                target_core.pushToSource(data[0]),
                value,
                operator_pk,
            )
            print("Waiting for LayerZero finalization...")
            wait_for_layer_zero_finalization(
                source_helper, target_helper, source_core_address, target_core_address
            )
            print("LayerZero finalization completed.")
    elif current_ratio_d3 > max_source_ratio_d3:
        print("Assets surplus. Current ratio: {}%".format(current_ratio_d3 / 10))
        value = source_helper.quotePushToTarget(source_core_address).call()
        print(wrap_text("SourceCore.pushToTarget{{value:{}}}()".format(value)))
        execute(
            source_core.pushToTarget(),
            value,
            operator_pk,
        )
        print("Waiting for LayerZero finalization...")
        wait_for_layer_zero_finalization(
            source_helper, target_helper, source_core_address, target_core_address
        )
        print("LayerZero finalization completed.")
    else:
        print(
            wrap_text(
                "No crosschain action required. Current ratio: {}%. Target SourceCore ratio: {}%. Max SourceCore ratio: {}%.".format(
                    current_ratio_d3 / 10,
                    source_ratio_d3 / 10,
                    max_source_ratio_d3 / 10,
                ),
                "green",
            )
        )

    data = target_helper.getAmounts(target_core_address, 0).call()
    
    if data[1]:
        print(wrap_text("TargetCore.claim({})".format(data[1].hex())))
        execute(target_core.claim(data[1].hex()), 0, operator_pk)
    if data[3] >= LAYER_ZERO_DUST:
        print(wrap_text("TargetCore.deposit({})".format(data[3])))
        execute(target_core.deposit(data[3]), 0, operator_pk)


if __name__ == "__main__":
    import os
    import dotenv

    dotenv.load_dotenv()

    operator_pk = os.getenv("OPERATOR_PK")
    source_rpc = os.getenv("SOURCE_RPC")
    target_rpc = os.getenv("TARGET_RPC")
    source_core_helper = os.getenv("SOURCE_CORE_HELPER")
    target_core_helper = os.getenv("TARGET_CORE_HELPER")

    source_core_address = os.getenv("SOURCE_CORE_ADDRESS")
    target_core_address = os.getenv("TARGET_CORE_ADDRESS")

    source_ratio_d3 = int(os.getenv("SOURCE_RATIO_D3", 1000))
    max_source_ratio_d3 = int(os.getenv("MAX_SOURCE_RATIO_D3", 1200))

    run(
        source_core_address=source_core_address,
        target_core_address=target_core_address,
        source_rpc=source_rpc,
        target_rpc=target_rpc,
        source_core_helper=source_core_helper,
        target_core_helper=target_core_helper,
        operator_pk=operator_pk,
        source_ratio_d3=source_ratio_d3,
        max_source_ratio_d3=max_source_ratio_d3,
    )
