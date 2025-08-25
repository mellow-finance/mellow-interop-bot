import os
import re
import json
from typing import Any, Dict, List
from dataclasses import dataclass


@dataclass
class Deployment:
    name: str
    source_core: str
    target_core: str


@dataclass
class SafeGlobal:
    safe_address: str
    proposer_private_key: str
    api_url: str


@dataclass
class SourceConfig:
    name: str
    rpc: str
    source_core_helper: str
    deployments: List[Deployment]
    safe_global: SafeGlobal = None


@dataclass
class Config:
    telegram_bot_api_key: str
    telegram_group_chat_id: str
    oracle_freshness_in_seconds: int
    target_rpc: str
    target_core_helper: str
    sources: List[SourceConfig]


def read_config(config_path: str) -> Config:
    """
    Read and parse the config.json file with the following transformations:
    1. Convert kebab-case keys to snake_case
    2. Replace ${VAR:default} patterns with environment variables or defaults

    Args:
        config_path: Path to the config.json file

    Returns:
        Config object with parsed and transformed configuration
    """
    # Read the JSON file
    with open(config_path, "r") as file:
        config = json.load(file)

    # Transform the configuration
    transformed_config = _transform_config(config)

    # Convert dictionary to typed Config object
    return _dict_to_config(transformed_config)


def _transform_config(obj: Any) -> Any:
    """
    Recursively transform the configuration object:
    - Convert kebab-case keys to snake_case
    - Replace ${VAR:default} patterns with environment variables
    """
    if isinstance(obj, dict):
        transformed = {}
        for key, value in obj.items():
            # Convert kebab-case to snake_case
            snake_key = key.replace("-", "_")
            # Recursively transform the value
            transformed[snake_key] = _transform_config(value)
        return transformed
    elif isinstance(obj, list):
        # Transform each item in the list
        return [_transform_config(item) for item in obj]
    elif isinstance(obj, str):
        # Handle environment variable substitution
        return _substitute_env_vars(obj)
    else:
        # Return primitive types as-is
        return obj


def _substitute_env_vars(value: str) -> str:
    """
    Replace ${VAR:default} patterns with environment variables or default values.

    Examples:
        ${TELEGRAM_BOT_API_KEY} -> os.getenv('TELEGRAM_BOT_API_KEY', '')
        ${TARGET_RPC:https://eth.drpc.org} -> os.getenv('TARGET_RPC', 'https://eth.drpc.org')
    """
    # Pattern to match ${VAR} or ${VAR:default}
    pattern = r"\$\{([^}:]+)(?::([^}]*))?\}"

    def replace_match(match):
        var_name = match.group(1)
        default_value = match.group(2) if match.group(2) is not None else ""
        return os.getenv(var_name, default_value)

    # Replace all occurrences in the string
    result = re.sub(pattern, replace_match, value)
    return result


def _dict_to_config(config_dict: Dict[str, Any]) -> Config:
    """
    Convert a dictionary to a typed Config object.
    """

    # Convert source configurations
    def create_source_config(source_dict: Dict[str, Any]) -> SourceConfig:
        deployments = [
            Deployment(
                name=dep["name"],
                source_core=dep["source_core"],
                target_core=dep["target_core"],
            )
            for dep in source_dict["deployments"]
        ]

        # Handle optional safe_global configuration
        safe_global = None
        if "safe_global" in source_dict:
            safe_global_dict = source_dict["safe_global"]
            safe_global = SafeGlobal(
                safe_address=safe_global_dict["safe_address"],
                proposer_private_key=safe_global_dict["proposer_private_key"],
                api_url=safe_global_dict["api_url"],
            )

        return SourceConfig(
            name=source_dict["name"],
            rpc=source_dict["rpc"],
            source_core_helper=source_dict["source_core_helper"],
            deployments=deployments,
            safe_global=safe_global,
        )

    # Convert all sources
    sources = [create_source_config(source) for source in config_dict["sources"]]

    return Config(
        telegram_bot_api_key=config_dict["telegram_bot_api_key"],
        telegram_group_chat_id=config_dict["telegram_group_chat_id"],
        oracle_freshness_in_seconds=int(config_dict["oracle_freshness_in_seconds"]),
        target_rpc=config_dict["target_rpc"],
        target_core_helper=config_dict["target_core_helper"],
        sources=sources,
    )
