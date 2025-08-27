from dataclasses import dataclass
from typing import List


@dataclass
class ThresholdWithOwners:
    """
    Data structure representing Safe threshold and owners information.

    Attributes:
        threshold: The number of confirmations required for transaction execution
        owners: List of owner addresses for the Safe
    """

    threshold: int
    owners: List[str]


@dataclass
class PendingTransactionInfo:
    """
    Data structure representing pending transaction information.
    """

    id: str
    number_of_required_confirmations: int
    threshold_with_owners: ThresholdWithOwners
    confirmations: List[str]
    missing_confirmations: List[str]


def validate_transaction_id(id: str, safe_address: str) -> None:
    if not id.startswith("multisig_"):
        raise Exception(f"Invalid id, expected 'multisig_' prefix: {id}")

    split_parts = id.split("_")
    if len(split_parts) != 3:
        raise Exception(f"Invalid id, expected 3 parts separated by '_': {id}")

    if split_parts[1] != safe_address:
        raise Exception(f"Invalid id, expected safe address in the second part: {id}")

    if not split_parts[2].startswith("0x"):
        raise Exception(f"Invalid id, expected '0x' prefix in the third part: {id}")


def validate_confirmation_accounting(
    confirmations: List[str], missing_confirmations: List[str], all_owners: List[str]
) -> None:
    """
    Validates that confirmations + missing_confirmations accounts for all owners exactly once.

    Args:
        confirmations: List of owner addresses who have confirmed
        missing_confirmations: List of owner addresses who haven't confirmed
        all_owners: List of all owner addresses for the Safe

    Raises:
        Exception: If the accounting doesn't match or there are duplicates
    """
    confirmations_set = set(confirmations)
    missing_confirmations_set = set(missing_confirmations)
    all_owners_set = set(all_owners)

    # Check for duplicates within each list
    if len(confirmations_set) != len(confirmations):
        raise Exception(f"Duplicate addresses found in confirmations: {confirmations}")

    if len(missing_confirmations_set) != len(missing_confirmations):
        raise Exception(
            f"Duplicate addresses found in missing_confirmations: {missing_confirmations}"
        )

    if len(all_owners_set) != len(all_owners):
        raise Exception(f"Duplicate addresses found in all_owners: {all_owners}")

    # Check for overlap between confirmations and missing_confirmations
    overlap = confirmations_set.intersection(missing_confirmations_set)
    if overlap:
        raise Exception(
            f"Addresses found in both confirmations and missing_confirmations: {list(overlap)}"
        )

    # Check that union equals all owners
    accounted_owners = confirmations_set.union(missing_confirmations_set)
    if accounted_owners != all_owners_set:
        missing_from_accounting = all_owners_set - accounted_owners
        extra_in_accounting = accounted_owners - all_owners_set

        error_msg = "Confirmation accounting mismatch:"
        if missing_from_accounting:
            error_msg += f" Missing owners: {list(missing_from_accounting)}"
        if extra_in_accounting:
            error_msg += f" Extra owners: {list(extra_in_accounting)}"

        raise Exception(error_msg)
