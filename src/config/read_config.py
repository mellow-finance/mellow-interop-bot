import os
import json
from web3 import Web3, constants
from typing import Any, Dict, List, Tuple
from dataclasses import dataclass


@dataclass(frozen=True)
class Deployment:
    name: str
    source_core: str
    target_core: str


@dataclass(frozen=True)
class SafeGlobal:
    safe_address: str
    proposer_private_key: str
    api_url: str
    api_key: str = None
    web_client_url: str = None
    eip_3770: str = None


@dataclass(frozen=True)
class SourceConfig:
    name: str
    rpc: str
    source_core_helper: str
    deployments: Tuple[Deployment, ...]  # Changed from List to tuple for hashability
    safe_global: SafeGlobal = None


@dataclass
class Config:
    telegram_bot_api_key: str
    telegram_group_chat_id: str
    telegram_owner_nicknames: Dict[str, str]
    telegram_proposal_message_prefix: str
    oracle_expiry_threshold_seconds: int
    oracle_recent_update_threshold_seconds: int
    target_rpc: str
    target_core_helper: str
    sources: List[SourceConfig]


def read_config(config_path: str) -> Config:
    """
    Read and parse the config.json file with the following transformations:
    1. Convert kebab-case keys to snake_case
    2. Replace ${VAR:default} patterns with environment variables or defaults
    3. Support nested variable substitution (e.g., ${BSC_SAFE_API_KEY:${SAFE_API_KEY}})

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
    - Replace ${VAR:default} patterns with environment variables (supports nested substitution)
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


def _substitute_env_vars(value: str, visited_vars: set = None) -> str:
    """
    Replace ${VAR:default} patterns with environment variables or default values.
    Supports nested variable substitution with circular reference detection.

    Examples:
        ${TELEGRAM_BOT_API_KEY} -> os.getenv('TELEGRAM_BOT_API_KEY', '')
        ${TARGET_RPC:https://eth.drpc.org} -> os.getenv('TARGET_RPC', 'https://eth.drpc.org')
        ${BSC_SAFE_API_KEY:${SAFE_API_KEY}} -> tries BSC_SAFE_API_KEY first, then SAFE_API_KEY
        ${VAR1:${VAR2:${VAR3:fallback}}} -> tries VAR1, then VAR2, then VAR3, then uses 'fallback'

    Args:
        value: The string containing variable patterns to substitute
        visited_vars: Set of variable names being processed (for circular reference detection)

    Returns:
        String with all variable patterns substituted

    Raises:
        ValueError: If a circular reference is detected in variable substitution
    """
    if visited_vars is None:
        visited_vars = set()

    result = value
    max_iterations = 64
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        start = result.rfind("${")
        if start == -1:
            break  # No more patterns

        # Parse variable name until ':' or '}'
        name_start = start + 2
        i = name_start
        while i < len(result) and result[i] not in ":}":
            i += 1
        if i >= len(result):
            break  # Incomplete pattern; leave as-is

        var_name = result[name_start:i]
        if not var_name:
            # Skip malformed and continue searching earlier occurrences
            result = result[:start] + result[start + 2 :]
            continue

        # Determine default value and closing brace position
        if result[i] == "}":
            default_value = ""
            close = i
        else:
            # We started from the last '${', so the next '}' is the matching close
            default_start = i + 1
            close = result.find("}", default_start)
            if close == -1:
                break  # Unmatched; leave as-is
            default_value = result[default_start:close]

        if var_name in visited_vars:
            raise ValueError(
                f"Circular reference detected in variable substitution: {var_name}"
            )

        env_value = os.getenv(var_name)
        replacement_source = env_value if env_value else default_value

        # Recursively resolve nested variables in the replacement source
        new_visited = visited_vars.copy()
        new_visited.add(var_name)
        replacement = _substitute_env_vars(replacement_source, new_visited)

        # Splice the resolved value back into the string
        result = result[:start] + replacement + result[close + 1 :]

    if iteration >= max_iterations:
        raise ValueError(
            f"Maximum substitution iterations exceeded. Possible complex circular reference in: {value}"
        )

    return result


def _parse_telegram_owners(telegram_owner_nicknames: str) -> Dict[str, str]:
    """
    Parse telegram owner nicknames string into a dictionary mapping nicknames to addresses.

    Supports two formats:
    1. Comma-separated nicknames: "@josh,@anna,@dexter"
    2. Comma-separated nickname:address pairs: "@josh:0x00..000,@anna:0xab..412"

    Args:
        telegram_owner_nicknames: String containing telegram nicknames

    Returns:
        Dictionary mapping telegram nicknames to addresses (zero address if not specified)
    """
    result = {}

    if not telegram_owner_nicknames:
        return result

    # Split by comma and process each entry
    entries = [
        entry.strip() for entry in telegram_owner_nicknames.split(",") if entry.strip()
    ]

    for entry in entries:
        # Check if entry contains address (format: @nickname:0xaddress)
        if ":" in entry:
            nickname, address = entry.split(":", 1)
            result[nickname.strip().lstrip("@")] = address.strip()
        else:
            # Format: @nickname (no address specified)
            result[entry.strip().lstrip("@")] = constants.ADDRESS_ZERO

    return result


def _dict_to_config(config_dict: Dict[str, Any]) -> Config:
    """
    Convert a dictionary to a typed Config object.
    """

    # Convert source configurations
    def create_source_config(source_dict: Dict[str, Any]) -> SourceConfig:
        deployments = tuple(
            Deployment(
                name=dep["name"],
                source_core=dep["source_core"],
                target_core=dep["target_core"],
            )
            for dep in source_dict["deployments"]
        )

        # Handle optional safe_global configuration
        safe_global = None
        if "safe_global" in source_dict:
            safe_global_dict = source_dict["safe_global"]

            # Handle eip_3770 fallback: use lowercased source name if not provided
            eip_3770 = safe_global_dict.get("eip_3770")
            if eip_3770 is None:
                eip_3770 = source_dict["name"].lower()

            safe_global = SafeGlobal(
                safe_address=safe_global_dict["safe_address"],
                proposer_private_key=safe_global_dict["proposer_private_key"],
                api_url=safe_global_dict["api_url"],
                api_key=safe_global_dict.get("api_key"),
                web_client_url=safe_global_dict.get("web_client_url"),
                eip_3770=eip_3770,
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
        telegram_owner_nicknames=_parse_telegram_owners(
            config_dict["telegram_owner_nicknames"]
        ),
        telegram_proposal_message_prefix=config_dict[
            "telegram_proposal_message_prefix"
        ],
        oracle_expiry_threshold_seconds=int(
            config_dict["oracle_expiry_threshold_seconds"]
        ),
        oracle_recent_update_threshold_seconds=int(
            config_dict["oracle_recent_update_threshold_seconds"]
        ),
        target_rpc=config_dict["target_rpc"],
        target_core_helper=config_dict["target_core_helper"],
        sources=sources,
    )
