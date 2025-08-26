# Mellow Interop Bot

A cross-chain oracle monitoring and validation bot that tracks oracle states across multiple blockchain networks and sends alerts via Telegram when intervention is needed.

## Prerequisites

- Python 3.11+ (or Docker)
- Access to blockchain RPC endpoints
- Telegram Bot API key (Optional)
- Smart contract addresses for monitoring

### Environment Variables

All environment variables can be optional.

- `ORACLE_FRESHNESS_IN_SECONDS` - Oracle freshness threshold (default: `3600`).
- `TARGET_RPC` - Target blockchain RPC endpoint (see default in `config.json`).
- `BSC_RPC` - BSC RPC endpoint (see default in `config.json`).
- `FRAX_RPC` - Fraxtal RPC endpoint (see default in `config.json`).
- `LISK_RPC` - Lisk RPC endpoint (see default in `config.json`).
- `DRY_RUN` - Run without sending telegram messages (default: `false`).

Optional if `DRY_RUN` is `true`:

- `TELEGRAM_BOT_API_KEY` - Your Telegram bot API key
- `TELEGRAM_GROUP_CHAT_ID` - Target Telegram group chat ID

## Usage

### Running locally

1. Create a virtual environment:

    ```bash
    python -m venv .venv
    source .venv/bin/activate 
    ```

2. Install dependencies:

    ```bash
    pip install -r requirements.txt
    ```

3. Set up environment variables if needed (you can use `.env` file). It is recommended to explicitly set `*_RPC` variables to use custom RPC endpoints to avoid 400/429 network errors.

4. Run the main script:

    ```bash
    python ./src/main.py
    ```

    You may want to run it without sending messages first:

    ```bash
    DRY_RUN=true python ./src/main.py
    ```

5. Optionally, run tests:

    ```bash
    python -m unittest discover -s tests -p "test_*.py" -v
    ```

### Running with Docker

1. Build the container:

    ```bash
    docker build -t mellow-interop-bot .
    ```

2. Run with environment variables:

    ```bash
    docker run --env-file .env mellow-interop-bot
    ```

### Running scripts

The `./src/web3_scripts` folder contains scripts that can be run separately. These scripts are also based on the configuration from the `config.json` file, but have their own settings provided through environment variables.

#### `oracle_script.py`

```bash
python ./src/web3_scripts/oracle_script.py
```

---

#### `operator_script.py`

```bash
python ./src/web3_scripts/oracle_script.py
```

Environment variables

- SOURCE_RATIO_D3 - Determines if rebalance is required due to asset deficit (default: `50`)
- MAX_SOURCE_RATIO_D3 - Maximum asset ratio threshold that triggers surplus rebalancing (default: `100`)

---

#### `operator_bot.py`

```bash
OPERATOR_PK=<pk> DEPLOYMENTS=<source:symbol> python ./src/web3_scripts/operator_bot.py
```

If you want to run a script on a newly added deployment, you may need to validate it first by executing the following command:

```bash
python ./src/config/validate_config.py 
```

Environment variables

Same `SOURCE_RATIO_D3` and `MAX_SOURCE_RATIO_D3`, plus:

- OPERATOR_PK - Private key to send transactions (required)
- DEPLOYMENTS - Comma-separated list of deployments for which the script needs to be run (required, example: `BSC:CYC,FRAX:FRAX`). See the `config.json` for all avaiable pairs.
