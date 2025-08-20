import yaml
import os
from config import read_config, validate_config

def main():
    try:
        config = read_config(os.getcwd() + "/config.yml")
        print("Configuration loaded successfully:")
        # print(config)
        validate_config(config)
    except FileNotFoundError:
        print(f"Error: config.yml not found")
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()
