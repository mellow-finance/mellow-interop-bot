import sys
import os
import re

if __name__ == "__main__":
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from web3_scripts.base import *
    from config.read_config import Config, SourceConfig, Deployment, read_config, SafeGlobal
else:
    from web3_scripts.base import *
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
    version = safe_contract.functions.VERSION().call()
    if not re.match(r'^\d+\.\d+\.\d+$', version):
        raise Exception(f"Invalid safe contract, version is not in the format x.y.z: {version}")

    proposer_address = Account.from_key(safe.proposer_private_key).address
    print(f"Proposer address: {proposer_address}, version: {version} ✅")


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
