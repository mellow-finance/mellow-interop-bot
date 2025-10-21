try:
    from .base import *
    from .oracle_script import run_oracle_validation
except ImportError:
    from base import *
    from oracle_script import run_oracle_validation
from typing import List

LAYER_ZERO_DUST = 1000_000_000_000


def run(
    source_core_address: str,
    target_core_address: str,
    source_rpc: str,
    target_rpc: str,
    source_core_helper: str,
    target_core_helper: str,
    source_ratio_d3: int,
    max_source_ratio_d3: int,
) -> List[str]:
    oracle_validation_result = run_oracle_validation(
        source_core_address,
        target_core_address,
        source_rpc,
        target_rpc,
        source_core_helper,
        target_core_helper,
        oracle_expiry_threshold_seconds=3600,
        oracle_recent_update_threshold_seconds=0,
    )

    if oracle_validation_result.transfer_in_progress:
        print_colored("OFT transfers in progress", "yellow")
        return []

    if oracle_validation_result.almost_expired:
        print_colored("Oracle is almost expired", "red")
        return []

    if oracle_validation_result.incorrect_value:
        print_colored("Oracle value is incorrect", "red")
        return []

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
        print_colored(
            "OFT transfers in progress. source chain {} target chain {}".format(
                source_nonces, target_nonces
            ),
            "yellow",
        )
        return []

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
        print_colored(
            "Withdrawal demand is greater or equal to total assets. Invalid state."
        )
        return []

    current_ratio_d3 = int(
        1000
        * (source_value - withdrawal_demand)
        // (source_value + target_value - withdrawal_demand)
    )

    required_actions = []

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
            required_actions.append(
                f"TargetCore({target_core.address}).redeem({data[2]})"
            )
        if data[1]:
            required_actions.append(
                f"TargetCore({target_core.address}).claim({data[1].hex()})"
            )
        if data[0] > 0:
            value = target_helper.quotePushToSource(target_core_address).call()
            required_actions.append(
                f"TargetCore({target_core.address}).pushToSource{{value: {value}}}({data[0]})"
            )
            required_actions.append(
                "Please, wait for LayerZero tx finalization (~5-10 minutes) and rerun script again..."
            )
    elif current_ratio_d3 > max_source_ratio_d3:
        print("Assets surplus. Current ratio: {}%".format(current_ratio_d3 / 10))
        value = source_helper.quotePushToTarget(source_core_address).call()
        required_actions.append(
            f"SourceCore({source_core.address}).pushToTarget{{value:{value}}}()"
        )
        required_actions.append(
            "Please, wait for LayerZero tx finalization (~5-10 minutes) and rerun script again..."
        )

    data = target_helper.getAmounts(target_core_address, 0).call()

    if data[1]:
        required_actions.append(
            f"TargetCore({target_core.address}).claim({data[1].hex()})"
        )
    if data[3] >= LAYER_ZERO_DUST:
        required_actions.append(f"TargetCore({target_core.address}).deposit({data[3]})")
    return required_actions


if __name__ == "__main__":
    import os
    import dotenv
    import sys
    from pathlib import Path

    # Add src directory to path to import config module
    src_path = Path(__file__).parent.parent
    sys.path.insert(0, str(src_path))

    from config.read_config import read_config

    dotenv.load_dotenv()

    # Read configuration from config.json
    config_path = src_path.parent / "config.json"
    config = read_config(str(config_path))

    target_rpc = config.target_rpc
    target_core_helper = config.target_core_helper

    source_ratio_d3 = int(os.getenv("SOURCE_RATIO_D3", 50))
    max_source_ratio_d3 = int(os.getenv("MAX_SOURCE_RATIO_D3", 100))

    # Build deployments from config
    deployments = []
    for source in config.sources:
        for deployment in source.deployments:
            deployments.append(
                (
                    deployment.source_core,
                    deployment.target_core,
                    source.source_core_helper,
                    source.rpc,
                )
            )

    for (
        source_core_address,
        target_core_address,
        source_core_helper,
        source_rpc,
    ) in deployments:
        source_core_name = (
            get_contract(get_w3(source_rpc), source_core_address, "SourceCore")
            .functions.name()
            .call()
        )
        print(f"Analyzing {add_color(source_core_name, 'yellow')} vault...")

        try:
            required_actions = run(
                source_core_address=source_core_address,
                target_core_address=target_core_address,
                source_rpc=source_rpc,
                target_rpc=target_rpc,
                source_core_helper=source_core_helper,
                target_core_helper=target_core_helper,
                source_ratio_d3=source_ratio_d3,
                max_source_ratio_d3=max_source_ratio_d3,
            )

            if required_actions:
                print("Required actions:")
                for index, action in enumerate(required_actions):
                    print(f'{index + 1}: {add_color(action, "red")}')
            else:
                print_colored("No actions required.", "green")
        except Exception as e:
            print_colored(f"Error: {e}", "red")

        print("\n" + "-" * 25 + "\n")
