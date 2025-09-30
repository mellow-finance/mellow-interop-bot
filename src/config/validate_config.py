import sys
import os
from packaging.version import Version
from web3 import constants

if __name__ == "__main__":
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from web3_scripts import get_w3, print_colored, get_contract, Account, Web3
from safe_global import client_gateway_api, transaction_api
from safe_global.multi_send_call import multi_send_contracts

# Handle both relative and absolute imports
try:
    from .read_config import Config, SourceConfig, Deployment, SafeGlobal, read_config
    from .mask_sensitive_data import mask_url_credentials, mask_source_sensitive_data
except ImportError:
    from config.read_config import Config, SourceConfig, Deployment, SafeGlobal, read_config
    from config.mask_sensitive_data import mask_url_credentials, mask_source_sensitive_data


def validate_config(config: Config):
    w3 = get_w3(config.target_rpc)
    validate_rpc_url(w3, "target")
    validate_target_helper(w3, config)
    for source in config.sources:
        validate_source(w3, source)


def validate_source(target_w3: Web3, source: SourceConfig):
    w3 = get_w3(source.rpc)
    validate_rpc_url(w3, source.name)
    validate_source_helper(w3, source)
    validate_deployments(w3, target_w3, source)
    validate_safe_global(w3, source)


def validate_safe_global(w3: Web3, source: SourceConfig):
    safe = source.safe_global
    if not safe:
        print(f"No safe global config is set for {source.name}, skipping validation...")
        return

    if not safe.safe_address:
        print(f"No safe address is set for {source.name}, skipping validation...")
        return

    print(f"Validating safe global {safe.safe_address}...")
    safe_contract = get_contract(w3, safe.safe_address, "Safe")

    min_version = Version("1.3.0")
    version = Version(safe_contract.functions.VERSION().call())
    if version < min_version:
        raise Exception(
            f"Safe contract version {version} is not supported, support for {min_version} or higher is required"
        )

    if safe.proposer_private_key:
        proposer_address = Account.from_key(safe.proposer_private_key).address
    else:
        proposer_address = "N/A"

    nonce = safe_contract.functions.nonce().call()
    print(f"Proposer address: {proposer_address}, version: {version}, nonce: {nonce}")

    validate_multi_send_contract_compatibility(w3, safe)

    if validate_safe_client_gateway_api_url(w3, safe, nonce):
        pass
    elif not validate_safe_transaction_api_url(safe):
        # Mask API URL which might contain credentials
        error_msg = f"Invalid safe API URL: {safe.api_url}"
        masked_error = mask_url_credentials(error_msg, safe.api_url)
        raise Exception(masked_error)


def validate_safe_owner_addresses(config: Config):
    owners = config.telegram_owner_nicknames
    if len(owners) == 0:
        print("No telegram nicknames for safe owners are set, skipping validation...")
        return

    all_zero = True
    all_non_zero = True
    for nickname, address in owners.items():
        if not address.startswith("0x") or not Web3.is_address(address):
            raise ValueError(f"Invalid address for nickname {nickname}!")
        if address != constants.ADDRESS_ZERO:
            all_zero = False
        else:
            all_non_zero = False

    if not all_zero and not all_non_zero:
        raise ValueError("All addresses must be set or all must be omitted!")

    if all_non_zero and len(owners) != len(set(owners.values())):
        raise ValueError("Duplicate owner addresses found!")


def validate_multi_send_contract_compatibility(w3: Web3, safe: SafeGlobal):
    print(
        f"Validating multi-send contract compatibility for safe {safe.safe_address}..."
    )

    safe_contract = get_contract(w3, safe.safe_address, "Safe")
    version_str = safe_contract.functions.VERSION().call()
    version = Version(version_str)

    base_version = version.base_version
    if base_version not in multi_send_contracts:
        supported_versions = ", ".join(multi_send_contracts.keys())
        raise Exception(
            f"Safe contract version {base_version} is not supported by multi-send contracts. "
            f"Supported versions: {supported_versions}"
        )

    multi_send_address = multi_send_contracts[base_version]
    # Check that the contract is deployed on the current network
    code = w3.eth.get_code(Web3.to_checksum_address(multi_send_address))
    bytecode = code.hex()
    if not bytecode or bytecode == "0x":
        raise Exception(
            f"Multi-send contract {multi_send_address} (version {base_version}) "
            f"is not deployed on the current network (chain ID: {w3.eth.chain_id})"
        )

    # Validate bytecode contains `multiSend` function selector
    MULTISEND_FUNCTION_SELECTOR = "8d80ff0a"  # multiSend(bytes)
    clean_bytecode = bytecode.lower().replace("0x", "")
    if MULTISEND_FUNCTION_SELECTOR not in clean_bytecode:
        raise Exception(
            f"Multi-send contract {multi_send_address} (version {base_version}) "
            f"does not contain multiSend function (selector: {MULTISEND_FUNCTION_SELECTOR})"
        )

    print(
        f"Multi-send contract compatibility validated ✅ (version: {base_version}, address: {multi_send_address})"
    )


def validate_safe_client_gateway_api_url(
    w3: Web3, safe: SafeGlobal, contract_nonce: int
) -> bool:
    chainId = w3.eth.chain_id
    version = None
    try:
        version = client_gateway_api.get_version(safe.api_url)
    except Exception as e:
        return False
    nonce = client_gateway_api.get_nonce(safe.api_url, chainId, safe.safe_address)
    if contract_nonce != nonce:
        raise Exception(
            f"Safe contract nonce {contract_nonce} does not match the nonce from client gateway {nonce}"
        )
    print(f"Client gateway API URL is valid (version: {version}), nonce is aligned ✅")
    return True


def validate_safe_transaction_api_url(safe: SafeGlobal):
    if not safe.api_key:
        print("No API key for safe transaction API is set, skipping validation...")
        return True
    try:
        version = transaction_api.get_version(safe.api_url, safe.api_key)
    except Exception:
        return False
    print(f"Transaction API URL is valid (version: {version}) ✅")
    return True


def validate_rpc_url(w3: Web3, label: str):
    """
    Validate the RPC URL is an active RPC endpoint.
    """
    print(f"Validating RPC URL for {label}...")
    if w3.eth.get_block("latest").number <= 0:
        # Mask RPC URL which might contain credentials
        rpc_url = str(w3.provider.endpoint_uri)
        error_msg = f"RPC URL {rpc_url} is not valid"
        masked_error = mask_url_credentials(error_msg, rpc_url)
        raise Exception(masked_error)


def validate_deployments(source_w3: Web3, target_w3: Web3, source: SourceConfig):
    # Track unique values for validation
    names = set()
    source_cores = set()
    target_cores = set()

    for deployment in source.deployments:
        # Validate deployment.source_core is not empty
        if not deployment.source_core or deployment.source_core.strip() == "":
            raise Exception(
                f"Source core cannot be empty for deployment {deployment.name} in source {source.name}"
            )

        # Validate deployment.target_core is not empty
        if not deployment.target_core or deployment.target_core.strip() == "":
            raise Exception(
                f"Target core cannot be empty for deployment {deployment.name} in source {source.name}"
            )

        # Validate source_core != target_core
        if deployment.source_core == deployment.target_core:
            raise Exception(
                f"Source core and target core must be different for deployment {deployment.name} in source {source.name}"
            )

        # Validate that deployment.name is unique in source.deployments array
        if deployment.name in names:
            raise Exception(
                f"Deployment name '{deployment.name}' is not unique in source {source.name}"
            )
        names.add(deployment.name)

        # Validate that deployment.source_core is unique in source.deployments array
        if deployment.source_core in source_cores:
            raise Exception(
                f"Source core '{deployment.source_core}' is not unique in source {source.name}"
            )
        source_cores.add(deployment.source_core)

        # Validate that deployment.target_core is unique in source.deployments array
        if deployment.target_core in target_cores:
            raise Exception(
                f"Target core '{deployment.target_core}' is not unique in source {source.name}"
            )
        target_cores.add(deployment.target_core)

        # Validate source <-> target core addresses refer to each other
        print(
            f"Validating deployment pair {deployment.name} ({deployment.source_core} <-> {deployment.target_core}) for source {source.name}..."
        )
        validate_deployment_pair(source_w3, target_w3, deployment)


def validate_deployment_pair(source_w3: Web3, target_w3: Web3, deployment: Deployment):
    """
    Validate that the source and target core addresses are correct (refer to each other).
    """
    source_contract = get_contract(source_w3, deployment.source_core, "SourceCore")
    target_contract = get_contract(target_w3, deployment.target_core, "TargetCore")

    source_core_address_bytes32 = Web3.to_checksum_address(
        target_contract.functions.sourceCoreAddress().call()[-20:].hex()
    )
    target_core_address_bytes32 = Web3.to_checksum_address(
        source_contract.functions.targetCoreAddress().call()[-20:].hex()
    )

    if source_core_address_bytes32 != deployment.source_core:
        raise Exception(f"Source core address mismatch for {deployment.name}")
    if target_core_address_bytes32 != deployment.target_core:
        raise Exception(f"Target core address mismatch for {deployment.name}")

    validate_symbol(source_w3, target_w3, deployment)


def validate_source_helper(w3: Web3, source: SourceConfig):
    """
    Validate the source helper address is valid SourceHelper contract.
    """
    print(f"Validating source helper {source.source_core_helper}...")
    try:
        source_helper_contract = get_contract(
            w3, source.source_core_helper, "SourceHelper"
        )
        for deployment in source.deployments:
            value = source_helper_contract.functions.getSourceValue(
                deployment.source_core
            ).call()
            if value == 0:
                print_colored(
                    f"Source value is 0 for {deployment.name} on {source.name}",
                    "yellow",
                )
    except Exception as e:
        # Mask any RPC URLs or sensitive data in the error message
        error_msg = f"Source helper ({source.source_core_helper}) is not valid: {e}"
        masked_error = mask_source_sensitive_data(error_msg, source)
        raise Exception(masked_error)


def validate_target_helper(w3: Web3, config: Config):
    """
    Validate the target helper address is valid TargetHelper contract.
    """
    print(f"Validating target helper {config.target_core_helper}...")
    try:
        target_helper_contract = get_contract(
            w3, config.target_core_helper, "TargetHelper"
        )
        for source in config.sources:
            for deployment in source.deployments:
                value = target_helper_contract.functions.getTargetValue(
                    deployment.target_core
                ).call()
                if value == 0:
                    print_colored(
                        f"Target value is 0 for {deployment.name} on {source.name}",
                        "yellow",
                    )
    except Exception as e:
        # Mask any RPC URLs or sensitive data in the error message
        error_msg = f"Target helper ({config.target_core_helper}) is not valid: {e}"
        masked_error = mask_url_credentials(error_msg, config.target_rpc)
        raise Exception(masked_error)


def validate_symbol(source_w3: Web3, target_w3: Web3, deployment: Deployment):
    """
    Validate that the deployment name (from config.json) matches the symbol of the source core, target OFT, and target vault.
    """
    print(f"Validating symbol matching for {deployment.name}...")
    if deployment.name.startswith("_"):
        print(
            f"Skipping symbol validation for {deployment.name} (due to '_' prefix)..."
        )
        return

    source_contract = get_contract(source_w3, deployment.source_core, "SourceCore")

    target_oft_address = (
        get_contract(target_w3, deployment.target_core, "TargetCore")
        .functions.oft()
        .call()
    )
    target_vault_address = (
        get_contract(target_w3, deployment.target_core, "TargetCore")
        .functions.vault()
        .call()
    )

    target_oft_contract = get_contract(target_w3, target_oft_address, "SourceCore")
    target_vault_contract = get_contract(target_w3, target_vault_address, "SourceCore")

    source_core_symbol = source_contract.functions.symbol().call()
    target_oft_symbol = target_oft_contract.functions.symbol().call()
    target_vault_symbol = target_vault_contract.functions.symbol().call()

    unique_symbols = set([source_core_symbol, target_oft_symbol, target_vault_symbol])
    for symbol in unique_symbols:
        if not deployment.name in symbol:
            raise Exception(
                f"Deployment name {deployment.name} should be substring of every symbol: {', '.join(unique_symbols)}. "
                f"Source core: {source_core_symbol}, Target OFT: {target_oft_symbol}, Target Vault: {target_vault_symbol}"
            )
    print(
        f"Deployment name {deployment.name} matches every symbol: {', '.join(unique_symbols)} ✅"
    )


if __name__ == "__main__":
    import os
    import dotenv

    dotenv.load_dotenv()

    config = read_config(os.getcwd() + "/config.json")

    validate_config(config)
