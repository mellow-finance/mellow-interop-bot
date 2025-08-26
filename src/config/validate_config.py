from re import I
import sys
import os
from packaging.version import Version
from urllib.parse import urljoin

if __name__ == "__main__":
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from web3_scripts.base import *
    from safe_global import (
        get_client_gateway_version,
        get_nonce,
        get_transaction_api_version,
    )
    from config.read_config import (
        Config,
        SourceConfig,
        Deployment,
        read_config,
        SafeGlobal,
    )
else:
    from web3_scripts.base import *
    from safe_global import (
        get_client_gateway_version,
        get_nonce,
        get_transaction_api_version,
    )
    from .read_config import Config, SourceConfig, Deployment, SafeGlobal


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
    if source.safe_global:
        validate_safe_global(w3, source.safe_global)


def validate_safe_global(w3: Web3, safe: SafeGlobal):
    print(f"Validating safe global {safe.safe_address}...")
    safe_contract = get_contract(w3, safe.safe_address, "Safe")

    min_version = Version("1.3.0")
    version = Version(safe_contract.functions.VERSION().call())
    if version < min_version:
        raise Exception(
            f"Safe contract version {version} is not supported, support for {min_version} or higher is required"
        )

    proposer_address = Account.from_key(safe.proposer_private_key).address
    nonce = safe_contract.functions.nonce().call()
    print(f"Proposer address: {proposer_address}, version: {version}, nonce: {nonce}")

    if validate_safe_client_gateway_api_url(w3, safe, nonce):
        # When safe URL is a Client Gateway API, the proposer should be an owner of the safe
        owners = safe_contract.functions.getOwners().call()
        if proposer_address not in owners:
            raise Exception(f"Proposer {proposer_address} is not an owner of the safe")
    elif not validate_safe_transaction_api_url(safe):
        raise Exception(f"Invalid safe API URL: {safe.api_url}")


def validate_safe_client_gateway_api_url(
    w3: Web3, safe: SafeGlobal, contract_nonce: int
) -> bool:
    chainId = w3.eth.chain_id
    version = None
    try:
        version = get_client_gateway_version(safe.api_url)
    except Exception as e:
        return False
    nonce = get_nonce(safe.api_url, chainId, safe.safe_address)
    if contract_nonce != nonce:
        raise Exception(
            f"Safe contract nonce {contract_nonce} does not match the nonce from client gateway {nonce}"
        )
    print(f"Client gateway API URL is valid (version: {version}), nonce is aligned ✅")
    return True


def validate_safe_transaction_api_url(safe: SafeGlobal):
    try:
        version = get_transaction_api_version(safe.api_url, safe.api_key)
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
        raise Exception(f"RPC URL {w3.provider.endpoint_uri} is not valid")


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
        raise Exception(
            f"Source helper ({source.source_core_helper}) is not valid: {e}"
        )


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
        raise Exception(
            f"Target helper ({config.target_core_helper}) is not valid: {e}"
        )


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
