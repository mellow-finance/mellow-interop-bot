import dotenv
import yaml
import os
import asyncio
from collections import defaultdict
from typing import List, Optional, Tuple

from telegram_bot import send_message, print_telegram_info
from config import read_config, Config, SourceConfig
from web3_scripts import (
    OracleValidationResult,
    run_oracle_validation,
    format_remaining_time,
)
from dataclasses import dataclass


@dataclass
class OracleData:
    name: str
    validation: Optional[OracleValidationResult]


async def main():
    try:
        # Load environment variables
        dotenv.load_dotenv()

        # Read config
        config = read_config(os.getcwd() + "/config.yml")

        # Print Telegram info (Bot and group)
        await print_telegram_info(
            config.telegram_bot_api_key, config.telegram_group_chat_id
        )

        # Validate and get oracles data
        oracle_validation_results = validate_oracles(config)

        # Compose message
        message = compose_oracle_data_message(config, oracle_validation_results)

        # Send message
        if not message:
            print("No message to send")
        else:
            await send_message(
                config.telegram_bot_api_key, config.telegram_group_chat_id, message
            )
    except FileNotFoundError:
        print(f"Error: config.yml not found")
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


def compose_oracle_data_message(
    config: Config,
    oracle_validation_results: List[Tuple[SourceConfig, OracleData]],
) -> str:
    # Skip if telegram variables are not set
    if not config.telegram_bot_api_key or not config.telegram_group_chat_id:
        return ""

    # Skip if there are no oracle validation results
    if len(oracle_validation_results) == 0:
        return ""

    # Skip if there are no required updates
    should_report = any(
        oracle_data.validation is None  # Error during validation on-chain data
        or oracle_data.validation.almost_expired
        or oracle_data.validation.transfer_in_progress
        or oracle_data.validation.incorrect_value
        for _, oracle_data in oracle_validation_results
    )
    if not should_report:
        return ""

    # Group validation results by source.name
    grouped_data: defaultdict[str, List[OracleData]] = defaultdict(list)
    for source, oracle_data in oracle_validation_results:
        grouped_data[source.name].append(oracle_data)

    message = ""

    # Process each group
    for source_name, oracle_data_list in grouped_data.items():
        message += f"\n**{source_name}**:\n"
        message += "```\n"
        for oracle_data in oracle_data_list:
            message += f" - {oracle_data.name}: "
            if oracle_data.validation is not None:
                validation = oracle_data.validation
                if validation.transfer_in_progress:
                    message += f"ℹ️ OFT transfers in progress (remaining time: {format_remaining_time(validation.remaining_time)}), address: {validation.oracle_address})"
                elif validation.almost_expired:
                    message += f"⚠️ Almost expired, needs update (remaining time: {format_remaining_time(validation.remaining_time)}, address: {validation.oracle_address})"
                elif validation.incorrect_value:
                    message += f"⚠️ Incorrect value, needs update (oracle value: {validation.oracle_value}, actual value: {validation.actual_value}, address: {validation.oracle_address})"
                else:
                    message += f"✅ Up to date (remaining time: {format_remaining_time(validation.remaining_time)})"
            else:
                message += f"❌ Error during validation (RPC problem)"
            message += "\n"
        message += "```"

    return message


def validate_oracles(
    config: Config,
) -> List[Tuple[SourceConfig, OracleData]]:
    result: List[Tuple[SourceConfig, OracleData]] = []
    for source in config.sources:
        for deployment in source.deployments:
            validation_result: Optional[OracleValidationResult] = None
            try:
                oracle_validation_result = run_oracle_validation(
                    source_core_address=deployment.source_core,
                    target_core_address=deployment.target_core,
                    source_rpc=source.rpc,
                    target_rpc=config.target_rpc,
                    source_core_helper=source.source_core_helper,
                    target_core_helper=config.target_core_helper,
                    oracle_freshness_in_seconds=config.oracle_freshness_in_seconds,
                )
                validation_result = oracle_validation_result
            except Exception as e:
                print(f"Error validating oracle for source {source.name}: {e}")
            oracle_data = OracleData(name=deployment.name, validation=validation_result)
            result.append((source, oracle_data))
    return result


if __name__ == "__main__":
    asyncio.run(main())
