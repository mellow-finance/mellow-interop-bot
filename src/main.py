import dotenv
import os
import asyncio
from collections import defaultdict
from typing import List, Optional, Tuple, Dict

from telegram_bot import send_message, print_telegram_info
from config import (
    read_config,
    Config,
    SourceConfig,
    SafeGlobal,
    mask_source_sensitive_data,
    mask_url_credentials,
    mask_all_sensitive_config_data,
)
from web3_scripts import (
    OracleValidationResult,
    run_oracle_validation,
    format_remaining_time,
)
from safe_global import PendingTransactionInfo, propose_tx_if_needed
from dataclasses import dataclass

from web3_scripts.base import print_colored


@dataclass
class OracleData:
    name: str
    validation: Optional[OracleValidationResult]


@dataclass
class SafeProposal:
    method: str  # e.g. "setValue"
    deployment_names: list[str]  # e.g. ["BSC", "FRAXTAL", ...]
    calls: list[
        tuple[str, list[int]]
    ]  # List of tuples(<oracle_address>, <args>), e.g. [("0x123", [1e18]), ...]
    transaction: Optional[PendingTransactionInfo]


async def main():
    config = None
    try:
        # Load environment variables
        dotenv.load_dotenv()

        # Read config
        config = read_config(os.getcwd() + "/config.json")

        # Print Telegram info (Bot and group)
        await print_telegram_info(
            config.telegram_bot_api_key, config.telegram_group_chat_id
        )

        # Validate and get oracles data
        oracle_validation_results = validate_oracles(config)

        # Compose message with oracle statuses
        message = compose_oracle_data_message(config, oracle_validation_results)
        if not message:
            print("No invalid oracle statuses to report")
            return

        # Send message with oracle statuses
        status_message = await send_message(
            config.telegram_bot_api_key, config.telegram_group_chat_id, message
        )

        # Propose tx to update oracle
        safe_proposals = propose_tx_to_update_oracle(oracle_validation_results)

        # Compose message with safe data
        for source, safe_proposal in safe_proposals:
            message = compose_safe_proposal_message(
                config.telegram_owner_nicknames,
                source.name,
                source.safe_global,
                safe_proposal,
            )

            # Send message with safe proposal for each source
            if message:
                if config.telegram_proposal_message_prefix:
                    message = config.telegram_proposal_message_prefix + "\n" + message

                await send_message(
                    config.telegram_bot_api_key,
                    config.telegram_group_chat_id,
                    message,
                    reply_to_message_id=status_message.message_id if status_message else None,
                )
        print(f"Sent {len(safe_proposals)} message(s) with safe proposal")
    except FileNotFoundError:
        print(f"Error: config.json not found")
    except Exception as e:
        error_message = str(e)
        # Mask all sensitive config data if config was loaded
        error_message = mask_all_sensitive_config_data(error_message, config)
        print(f"Unexpected error: {error_message}")


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

    # Skip if there are no required (or recent) updates
    has_any_problem = any(
        oracle_data.validation is None  # Error during validation on-chain data
        or oracle_data.validation.almost_expired
        or oracle_data.validation.transfer_in_progress
        or oracle_data.validation.incorrect_value
        for _, oracle_data in oracle_validation_results
    )
    has_recent_update = any(
        oracle_data.validation is not None and oracle_data.validation.recently_updated
        for _, oracle_data in oracle_validation_results
    )
    should_report = has_any_problem or has_recent_update
    if not should_report:
        return ""

    # Group validation results by source.name
    grouped_data: defaultdict[str, List[OracleData]] = defaultdict(list)
    for source, oracle_data in oracle_validation_results:
        grouped_data[source.name].append(oracle_data)

    message = ""

    # Process each group
    for source_name, oracle_data_list in grouped_data.items():
        message += f"\n{source_name}:\n"
        message += "```solidity\n"
        for oracle_data in oracle_data_list:
            message += f"- {oracle_data.name}: "
            if oracle_data.validation is not None:
                validation = oracle_data.validation
                if validation.transfer_in_progress:
                    message += f"ℹ️ OFT transfers in progress (remaining time: {format_remaining_time(validation.remaining_time)}, address: {validation.oracle_address})"
                elif validation.almost_expired:
                    if validation.remaining_time < 0:
                        message += f"⚠️ Already expired, needs update (overdue: {format_remaining_time(-validation.remaining_time)}, oracle value: {validation.oracle_value}, actual value: {validation.actual_value}, address: {validation.oracle_address})"
                    else:
                        message += f"⚠️ Almost expired, needs update (remaining time: {format_remaining_time(validation.remaining_time)}, oracle value: {validation.oracle_value}, actual value: {validation.actual_value}, address: {validation.oracle_address})"
                elif validation.incorrect_value:
                    message += f"⚠️ Incorrect value, needs update (remaining time: {format_remaining_time(validation.remaining_time)}, oracle value: {validation.oracle_value}, actual value: {validation.actual_value}, address: {validation.oracle_address})"
                else:
                    message += f"✅ Up to date (remaining time: {format_remaining_time(validation.remaining_time)})"
            else:
                message += f"❌ Error during validation (RPC problem)"
            message += "\n"
        message += "```"

    return message


def compose_safe_proposal_message(
    nickname_address_map: Dict[str, str],
    source_name: str,
    safe_global: SafeGlobal,
    proposal: SafeProposal,
) -> str:
    message = f"Approve tx for `{source_name}` to update {len(proposal.deployment_names)} oracle(s):\n"

    if proposal.transaction is None:
        message += "❌ Error occurred during proposal"
        return message

    message += "```solidity\n"
    for index, call in enumerate(proposal.calls):
        name = proposal.deployment_names[index]
        oracle_address = call[0]
        args = call[1]
        args_str = ", ".join(str(arg) for arg in args)
        message += (
            f"- {name}: {proposal.method}({args_str}), address: {oracle_address}\n"
        )
    message += "```"

    link = compose_safe_tx_link(safe_global, proposal)
    message += f"\nLink: [{link}]({link})\n"

    confirmations_message, is_confirmed = compose_safe_tx_confirmations(proposal)
    message += f"\n{confirmations_message}"

    if not is_confirmed:
        mentions = compose_owner_mentions(nickname_address_map, proposal)
        if mentions:
            message += f", cc {mentions}"
    else:
        message += " ✅, ready to be executed"

    return message


def compose_safe_tx_link(
    safe_global_config: SafeGlobal,
    proposal: SafeProposal,
) -> str:
    url = safe_global_config.web_client_url
    eip_3770 = safe_global_config.eip_3770
    safe_address = safe_global_config.safe_address
    return f"{url}/transactions/tx?safe={eip_3770}:{safe_address}&id={proposal.transaction.id}"


def compose_owner_mentions(
    nickname_address_map: Dict[str, str],
    proposal: SafeProposal,
) -> str:
    owners = []
    for nickname, address in nickname_address_map.items():
        if address in proposal.transaction.missing_confirmations:
            owners.append(nickname)
    return format_mentions(owners)


def format_mentions(mentions: List[str]) -> str:
    return ", ".join("@" + mention.replace("_", "\\_") for mention in mentions)


def compose_safe_tx_confirmations(proposal: SafeProposal) -> tuple[str, bool]:
    confirmations = len(proposal.transaction.confirmations)
    required_confirmations = proposal.transaction.number_of_required_confirmations
    return (
        f"Confirmations: {confirmations}/{required_confirmations}",
        confirmations >= required_confirmations,
    )


def propose_tx_to_update_oracle(
    oracle_validation_results: List[Tuple[SourceConfig, OracleData]],
) -> List[Tuple[SourceConfig, SafeProposal]]:
    result: List[Tuple[SourceConfig, SafeProposal]] = []

    # Group validation results by source.name
    grouped_data: defaultdict[SourceConfig, List[OracleData]] = defaultdict(list)
    for source, oracle_data in oracle_validation_results:
        grouped_data[source].append(oracle_data)

    # Process each source
    for source, oracle_data_list in grouped_data.items():
        safe_global = source.safe_global
        if safe_global is None:
            continue

        if not source.safe_global.proposer_private_key:
            print(f"Skipping proposal for {source.name} because proposer pk is not set")
            continue

        contract_abi = "Oracle"
        method = "setValue"
        deployment_names = []
        calls: list[tuple[str, list[int]]] = []

        # Process each oracle data
        for oracle_data in oracle_data_list:
            # Skip if oracle validation failed
            validation = oracle_data.validation
            if validation is None:
                continue

            # Skip if transfer is in progress
            if validation.transfer_in_progress:
                continue

            # Skip if oracle is not expired or incorrect
            if not validation.almost_expired and not validation.incorrect_value:
                continue

            # Update is required, add oracle data to calls
            to = validation.oracle_address
            args = [validation.actual_value]
            deployment_names.append(oracle_data.name)
            calls.append((to, args))

        if len(calls) == 0:
            print(f"No oracle updates required for source {source.name}")
            continue

        transaction = None
        try:
            transaction = propose_tx_if_needed(contract_abi, method, calls, source)
        except Exception as e:
            error_message = str(e)
            # Mask all source-related sensitive data (RPC URL, private key, API key)
            masked_error = mask_source_sensitive_data(error_message, source)
            print_colored(f"Error proposing tx for source {source.name}: {masked_error}", "red")

        proposal = SafeProposal(
            method=method,
            deployment_names=deployment_names,
            calls=calls,
            transaction=transaction,
        )
        result.append((source, proposal))

    return result


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
                    oracle_expiry_threshold_seconds=config.oracle_expiry_threshold_seconds,
                    oracle_recent_update_threshold_seconds=config.oracle_recent_update_threshold_seconds,
                )
                validation_result = oracle_validation_result
            except Exception as e:
                error_message = str(e)
                # Mask source RPC and target RPC URLs that might be in the error
                masked_error = mask_source_sensitive_data(error_message, source)
                masked_error = mask_url_credentials(masked_error, config.target_rpc)
                print(f"Error validating oracle for source {source.name}: {masked_error}")
            oracle_data = OracleData(name=deployment.name, validation=validation_result)
            result.append((source, oracle_data))
    return result


if __name__ == "__main__":
    asyncio.run(main())
