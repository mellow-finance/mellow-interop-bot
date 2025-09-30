"""
Utility functions for masking sensitive data in error messages and logs.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .read_config import Config, SourceConfig


def mask_sensitive_data(message: str, sensitive_value: str) -> str:
    """Mask sensitive data in error messages"""
    if not sensitive_value or len(sensitive_value) < 8:
        return message
    # Replace the sensitive value with masked version (show first 4 chars)
    masked = sensitive_value[:4] + "*" * (len(sensitive_value) - 4)
    return message.replace(sensitive_value, masked)


def mask_url_credentials(message: str, url: str) -> str:
    """Mask credentials in URLs (API keys in query params or auth)"""
    if not url:
        return message

    # Check if URL contains credentials, API keys, or paths (RPC URLs often have sensitive paths)
    has_credentials = "@" in url
    has_query_params = "?" in url
    has_api_key_keywords = "apikey" in url.lower() or "api_key" in url.lower()
    has_path = "/" in url.split("://")[1] if "://" in url else False

    # Mask if URL has any sensitive indicators or paths (common in RPC URLs)
    if has_credentials or has_query_params or has_api_key_keywords or has_path:
        try:
            if "://" in url:
                protocol = url.split("://")[0]
                rest = url.split("://")[1]

                # Handle authentication in URL (user:password@domain)
                if "@" in rest:
                    domain_part = rest.split("@")[-1]  # Get part after @
                    domain = domain_part.split("/")[0].split("?")[0]
                    masked_url = f"{protocol}://{domain}/***"
                else:
                    # No auth, just get domain
                    domain = rest.split("/")[0].split("?")[0]
                    masked_url = f"{protocol}://{domain}/***"

                message = message.replace(url, masked_url)
        except:
            # If parsing fails, just mask the whole URL
            message = mask_sensitive_data(message, url)

    return message


def mask_source_sensitive_data(message: str, source: "SourceConfig") -> str:
    """Mask sensitive data from a specific source configuration"""
    if not source:
        return message

    # Mask source RPC URL credentials
    if source.rpc:
        message = mask_url_credentials(message, source.rpc)

    # Mask safe global sensitive data
    if source.safe_global:
        # Mask proposer private key
        if source.safe_global.proposer_private_key:
            message = mask_sensitive_data(
                message, source.safe_global.proposer_private_key
            )

        # Mask safe API key
        if source.safe_global.api_key:
            message = mask_sensitive_data(message, source.safe_global.api_key)

    return message


def mask_all_sensitive_config_data(message: str, config: "Config") -> str:
    """Mask all sensitive data from config in error messages"""
    if not config:
        return message

    # Mask telegram bot API key
    if config.telegram_bot_api_key:
        message = mask_sensitive_data(message, config.telegram_bot_api_key)

    # Mask telegram group chat ID
    if config.telegram_group_chat_id:
        message = mask_sensitive_data(message, config.telegram_group_chat_id)

    # Mask telegram owner addresses
    if config.telegram_owner_nicknames:
        for nickname, address in config.telegram_owner_nicknames.items():
            if address and len(address) >= 8:
                message = mask_sensitive_data(message, address)

    # Mask target RPC URL credentials
    if config.target_rpc:
        message = mask_url_credentials(message, config.target_rpc)

    # Mask source-specific sensitive data
    for source in config.sources:
        message = mask_source_sensitive_data(message, source)

    return message
