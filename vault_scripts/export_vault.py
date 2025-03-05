import hvac
import os
import json
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv("./.env")

# Vault configuration
VAULT_ADDR = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
VAULT_NAMESPACE = os.getenv("VAULT_NAMESPACE", "")  # e.g., infrastructure/aiops/
VAULT_ROLE_ID = os.getenv("VAULT_ROLE_ID")
VAULT_SECRET_ID = os.getenv("VAULT_SECRET_ID")
VAULT_TOKEN = os.getenv("VAULT_TOKEN", None)

# Define the correct KV v2 path
VAULT_KV_PATH = "kv"

# Path to the file containing paths to scan
VAULT_PATHS_FILE = "vault_paths.txt"

def connect_client():
    """Connects to Vault using a token or AppRole authentication."""
    try:
        client = hvac.Client(url=VAULT_ADDR, verify=False)

        if VAULT_NAMESPACE:
            client.adapter.session.headers.update({"X-Vault-Namespace": VAULT_NAMESPACE})

        if VAULT_TOKEN:
            client.token = VAULT_TOKEN
            if client.is_authenticated():
                print("✅ Successfully authenticated with Vault using token.")
            else:
                print("❌ Authentication failed! Check your VAULT_TOKEN.")
                exit(1)
        else:
            response = client.auth.approle.login(role_id=VAULT_ROLE_ID, secret_id=VAULT_SECRET_ID)
            client.token = response["auth"]["client_token"]
            print("✅ Successfully authenticated with AppRole.")

        return client
    except Exception as e:
        print(f"❌ Vault authentication failed: {e}")
        exit(1)

def validate_paths(client, paths):
    """Check if paths are valid before attempting to export."""
    valid_paths = []

    for path in paths:
        try:
            # Try to access the path without listing secrets
            # kv_path = f"{VAULT_KV_PATH}/data/{path}"
            print(f"trying kv path: {path}")
            client.secrets.kv.v2.read_secret_version(path=path, mount_point=VAULT_KV_PATH)

            valid_paths.append(path)
            print(f"✅ Valid path: {path}")

        except hvac.exceptions.InvalidPath:
            print(f"❌ Invalid path: {path} (Path does not exist)")
        except hvac.exceptions.Forbidden:
            print(f"⚠️ Permission denied for path: {path} (May exist but cannot be accessed)")
            valid_paths.append(path)  # Add it to valid paths since it exists but we lack permissions
        except Exception as e:
            print(f"❌ Error validating path {path}: {e}")

    return valid_paths


def list_secrets(client, path):
    """Fetch secret names or directories from Vault at the given path."""
    try:
        kv_metadata_path = f"metadata/{path}" if path else "metadata"
        response = client.secrets.kv.v2.list_secrets(path=path, mount_point=VAULT_KV_PATH)
        return response.get("data", {}).get("keys", [])
    except hvac.exceptions.Forbidden:
        print(f"🚫 Permission denied: {path}")
        return None
    except hvac.exceptions.InvalidPath:
        return []
    except Exception as e:
        print(f"❌ Error listing secrets for {path}: {e}")
        return []

def get_secret(client, path):
    """Retrieve a secret from Vault if it exists."""
    try:
        response = client.secrets.kv.v2.read_secret_version(path=path, mount_point=VAULT_KV_PATH)
        return response.get("data", {}).get("data", {})
    except hvac.exceptions.InvalidPath:
        return None
    except hvac.exceptions.Forbidden:
        print(f"🚫 Permission denied: {path}")
        return None
    except Exception as e:
        print(f"❌ Error retrieving secret {path}: {e}")
        return None

def export_namespace(client, base_path=""):
    """Recursively traverse and export secrets, ensuring top-level secrets are captured."""
    structure = {}
    paths = list_secrets(client, base_path)

    if paths is None:
        return None  # No access

    has_valid_secret = False  # Track if this namespace has any secrets

    for key in paths:
        full_path = f"{base_path}/{key}".strip("/") if base_path else key

        if key.endswith('/'):  # This is a directory (namespace)
            print(f"📂 Entering directory: {full_path}")
            nested_structure = export_namespace(client, full_path)
            if nested_structure:  # Only add non-empty directories
                structure[key.strip("/")] = nested_structure
        else:  # This is a valid secret
            print(f"🔑 Fetching secret: {full_path}")
            secret_data = get_secret(client, full_path)
            if secret_data:
                structure[key] = secret_data
                has_valid_secret = True

    # Also fetch secrets at the root level of this namespace
    if base_path:
        print(f"🔑 Checking for top-level secrets in {base_path}")
        secret_data = get_secret(client, base_path)
        if secret_data:
            structure["_root"] = secret_data  # Store root secrets separately
            has_valid_secret = True

    return structure if has_valid_secret else None  # Avoid empty JSON objects

def export_selected_paths(client, output_file):
    """Export secrets for selected paths in a structured way."""
    root_structure = {}

    if not os.path.exists(VAULT_PATHS_FILE):
        print(f"❌ Vault paths file '{VAULT_PATHS_FILE}' not found!")
        return

    with open(VAULT_PATHS_FILE, "r") as f:
        paths_to_scan = [line.strip() for line in f.readlines() if line.strip()]

    valid_paths = validate_paths(client, paths_to_scan)

    if not valid_paths:
        print("⚠️ No valid paths found. Exiting...")
        return

    for path in valid_paths:
        print(f"🔍 Scanning path: {path}")
        result = export_namespace(client, path)
        if result:
            root_structure[path.strip("/")] = result  # Normalize paths

    with open(output_file, "w") as f:
        json.dump(root_structure, f, indent=4)

    print(f"✅ Secrets exported successfully to {output_file}")

if __name__ == "__main__":
    client = connect_client()
    export_selected_paths(client, "vault_secrets_export.json")
