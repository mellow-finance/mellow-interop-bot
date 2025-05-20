import json
import os
from dotenv import load_dotenv
from web3 import Web3
from web3.contract import Contract

load_dotenv()

TARGET_RPC = os.environ.get('TARGET_RPC')
SOURCE_RPC = os.environ.get('SOURCE_RPC')

SOURCE_HELPER_ADDRESS = os.environ.get('SOURCE_HELPER_ADDRESS')
TARGET_HELPER_ADDRESS = os.environ.get('TARGET_HELPER_ADDRESS')
TARGET_W3 = Web3(Web3.HTTPProvider(TARGET_RPC))
SOURCE_W3 = Web3(Web3.HTTPProvider(SOURCE_RPC))
PUSH_TO_GAS = 500000

def get_contract(w3: Web3, address: str, name: str) -> Contract:
    with open('./abi/{}.json'.format(name), 'r') as f:
        abi = json.load(f)
        return w3.eth.contract(address=w3.to_checksum_address(address), abi=abi)


def collect(source_core_address: str, target_core_address: str) -> None:
    source_helper = get_contract(
        SOURCE_W3, SOURCE_HELPER_ADDRESS, 'SourceHelper')
    source_nonces = source_helper.functions.getNonces(
        source_core_address).call()
    target_helper = get_contract(
        TARGET_W3, TARGET_HELPER_ADDRESS, 'TargetHelper')
    target_nonces = target_helper.functions.getNonces(
        target_core_address).call()

    # requirement: source.inboundNonce == target.outboundNonce && source.outboundNonce == target.inboundNonce
    if source_nonces[0] != target_nonces[1] or source_nonces[1] != target_nonces[0]:
        print('Nonces are not equal! (OFT transfers in progress)')
        print('Source Nonces:', source_nonces)
        print('Target Nonces:', target_nonces)
        return

    source_amounts = source_helper.functions.getAmounts(
        source_core_address).call()
    target_amounts = target_helper.functions.getAmounts(
        target_core_address, source_amounts[0]).call()

    print('Required actions for SourceCore({}) deployment:'.format(source_core_address))
    if source_amounts[1] > 0:
        print('SourceCore({})::pushToTarget{{value: {}}}({});'.format(
            source_core_address,
            PUSH_TO_GAS * TARGET_W3.eth.gas_price,
            source_amounts[1]
        ))
    if target_amounts[2] > 0:
        print('TargetCore({})::redeem({});'.format(
            target_core_address, target_amounts[2]))
    if target_amounts[1]:
        print('TargetCore({})::claim({});'.format(
            target_core_address, target_amounts[1].hex()))
    if target_amounts[0] > 0:
        print('TargetCore({})::pushToSource{{value: {}}}({});'.format(
            target_core_address,
            PUSH_TO_GAS * SOURCE_W3.eth.gas_price,
            target_amounts[0]
        ))
    if target_amounts[3] > 0:
        print('TargetCore({})::deposit({});'.format(
            target_core_address, target_amounts[3]))

    print('---------------')


if __name__ == '__main__':
    collect(
        os.environ.get('SOURCE_CORE_ADDRESS_LSK'),
        os.environ.get('TARGET_CORE_ADDRESS_LSK')
    )
    collect(
        os.environ.get('SOURCE_CORE_ADDRESS_WSTETH'),
        os.environ.get('TARGET_CORE_ADDRESS_WSTETH')
    )
    collect(
        os.environ.get('SOURCE_CORE_ADDRESS_MBTC'),
        os.environ.get('TARGET_CORE_ADDRESS_MBTC')
    )
