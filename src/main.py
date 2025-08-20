import dotenv
import yaml
import os
import asyncio
from typing import List

from telegram_bot import send_message
from config import read_config, validate_config, Config
from web3_scripts import run_oracle_validation
from web3_scripts.oracle_script import OracleValidationResult

async def main():
    try:
        dotenv.load_dotenv()

        config = read_config(os.getcwd() + "/config.yml")
        validate_config(config)

        if config.telegram_bot_api_key and config.telegram_group_chat_id:
            await send_message(config.telegram_bot_api_key, config.telegram_group_chat_id, "Hello, world!")
        else:
            print("Telegram bot API key or group chat ID not found in config.yml")
    except FileNotFoundError:
        print(f"Error: config.yml not found")
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


def validate_oracles(config: Config) -> List[OracleValidationResult]:
    validation_results: List[OracleValidationResult] = []
    for source in config.sources:
        for deployment in source.deployments:
            oracle_validation_result = run_oracle_validation(
                source_core_address=deployment.source_core,
                target_core_address=deployment.target_core,
                source_rpc=source.rpc,
                target_rpc=config.target_rpc,
                source_core_helper=source.source_core_helper,
                target_core_helper=config.target_core_helper,
                oracle_freshness_in_seconds=config.oracle_freshness_in_seconds,
            )
            validation_results.append(oracle_validation_result)
    
    return validation_results


if __name__ == "__main__":
    asyncio.run(main())
