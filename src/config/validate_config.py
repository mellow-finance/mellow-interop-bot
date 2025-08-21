import sys
import os

if __name__ == "__main__":
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from web3_scripts.base import *
    from config.read_config import Config, SourceConfig, Deployment, read_config
else:
    from web3_scripts.base import *
    from .read_config import Config, SourceConfig, Deployment


def validate_config(config: Config):
    w3 = get_w3(config.target_rpc)
    validate_rpc_url(w3)
    validate_target_helper(w3, config)

    for source in config.sources:
        validate_source(w3, source)


def validate_source(target_w3: Web3, source: SourceConfig):
    w3 = get_w3(source.rpc)
    validate_rpc_url(w3)
    validate_source_helper(w3, source)
    validate_deployments(w3, target_w3, source)


def validate_rpc_url(w3: Web3):
    """
    Validate the RPC URL is an active RPC endpoint.
    """
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


def validate_source_helper(w3: Web3, source: SourceConfig):
    """
    Validate the source helper address is valid SourceHelper contract.
    """
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


if __name__ == "__main__":
    import os
    import dotenv

    dotenv.load_dotenv()

    config = read_config(os.getcwd() + "/config.yml")

    validate_config(config)
