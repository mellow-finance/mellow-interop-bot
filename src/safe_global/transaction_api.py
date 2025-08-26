import requests

def get_transaction_api_version(api_url: str, api_key: str) -> str:
    url = f"{api_url.rstrip('/')}/api/v1/about"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to get transaction api version: {response.status_code}")
    result = response.json()
    if result["name"] != "Safe Transaction Service":
        raise Exception(f"Provided API URL is not a transaction api: {api_url}")
    return result["version"]




if __name__ == "__main__":
    import dotenv
    import sys
    from pathlib import Path

    # Add src directory to path to import config module
    src_path = Path(__file__).parent.parent
    sys.path.insert(0, str(src_path))

    from config.read_config import read_config
    from web3_scripts.base import get_w3

    dotenv.load_dotenv()

    # Read configuration from config.json
    config_path = src_path.parent / "config.json"
    config = read_config(str(config_path))

    # Find for FRAX source
    source = next((s for s in config.sources if s.name == "BSC"), None)
    if not source:
        raise Exception("BSC source not found")
    
    version = get_transaction_api_version(source.safe_global.api_url, source.safe_global.api_key)
    print(f"Transaction API version: {version}")

