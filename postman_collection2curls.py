import os
from dotenv import find_dotenv, load_dotenv
import requests
import sys
import re
import logging
import argparse

# Configure the logger
logging.basicConfig(
    level=logging.INFO,  # Default logging level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Logging format
    handlers=[
        logging.StreamHandler()  # Log to console
    ]
)
logger = logging.getLogger(__name__)  # Set the logger for this module

load_dotenv(find_dotenv("postman.env"), verbose=True)

# Function to prompt for input if not provided via CLI
def get_user_input(prompt_message, default_value=None):
    user_input = input(prompt_message)
    return user_input.strip() if user_input.strip() else default_value

# Function to resolve Postman variables in a string
def resolve_variables(value, variables):
    if not value:
        return value
    return re.sub(r"\{\{(.*?)\}\}", lambda match: variables.get(match.group(1), match.group(0)), value)

# Fetch all variables (global, environment, collection)
def fetch_variables(api_key, environment_name, collection):
    variables = {}

    # Fetch global variables
    global_vars_url = "https://api.getpostman.com/globals"
    headers = {"X-Api-Key": api_key}
    global_response = requests.get(global_vars_url, headers=headers)

    if global_response.status_code == 200:
        global_vars = global_response.json()["globals"]["values"]
        variables.update({var["key"]: var["value"] for var in global_vars})

    # Fetch environment variables based on the environment name
    env_mapping = {
        "dev": "30382268-ec2778ce-9b32-49c8-bfad-1e4933f7162f",
        "uat": "30382268-c88532d8-4133-4a60-b870-09f83436d7ac",
        "s3b": "30382268-c66919bb-bf05-46f7-82d2-3a923d19e487",
        "pc1": "30382268-1a0ec786-ef49-4693-add0-e13ba7544fb9",
    }

    if environment_name not in env_mapping:
        raise ValueError(f"Invalid environment name: {environment_name}")

    environment_id = env_mapping[environment_name]
    env_vars_url = f"https://api.getpostman.com/environments/{environment_id}"
    env_response = requests.get(env_vars_url, headers=headers)

    if env_response.status_code == 200:
        env_vars = env_response.json()["environment"]["values"]
        variables.update({var["key"]: var["value"] for var in env_vars})

    # Fetch collection variables
    collection_variables = collection.get("variable", [])
    variables.update({var["key"]: var["value"] for var in collection_variables})

    # logger.info(f"variables: {variables}")
    return variables

# Recursive function to collect all requests in nested folders
def collect_requests(items, requests_list):
    for item in items:
        if "item" in item:  # If this is a folder, recurse into it
            collect_requests(item["item"], requests_list)
        elif "request" in item:  # If this is a request, add to the list
            requests_list.append(item)
    return requests_list

if __name__ == "__main__":
    # Argument parser
    parser = argparse.ArgumentParser(description="Execute Postman API requests.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging for requests.")
    args = parser.parse_args()

    # Adjust logger level based on verbosity
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Assign arguments to variables or prompt for input
    API_KEY = os.getenv("API_KEY") if os.getenv("API_KEY") else get_user_input("Enter your Postman API Key: ")
    COLLECTION_ID = os.getenv("COLLECTION_ID") if os.getenv("COLLECTION_ID") else get_user_input("Enter your Postman Collection ID: ")
    ENVIRONMENT_NAME = os.getenv("ENVIRONMENT_NAME") if os.getenv("ENVIRONMENT_NAME") else get_user_input("Enter the environment (dev, uat, s3b, pc1): ").lower()

    logger.info(f"API_KEY: {API_KEY}, COLLECTION_ID: {COLLECTION_ID}, ENVIRONMENT_NAME: {ENVIRONMENT_NAME}")

    # Ensure required inputs are provided
    if not API_KEY:
        raise ValueError("Postman API Key is required.")
    if not COLLECTION_ID:
        raise ValueError("Postman Collection ID is required.")
    if ENVIRONMENT_NAME not in ["dev", "uat", "s3b", "pc1"]:
        raise ValueError("Invalid environment name. Choose from: dev, uat, s3b, pc1.")

    # Fetch collection data
    collection_url = f"https://api.getpostman.com/collections/{COLLECTION_ID}"
    headers = {"X-Api-Key": API_KEY}
    response = requests.get(collection_url, headers=headers)

    if response.status_code != 200:
        raise ValueError(f"Failed to fetch collection: {response.text}")

    collection = response.json()["collection"]

    # Fetch all variables
    variables = fetch_variables(API_KEY, ENVIRONMENT_NAME, collection)

    # Collect all requests
    all_requests = collect_requests(collection["item"], [])
    logger.debug(f"Total requests found: {len(all_requests)}")

    # Execute all requests and store results
    results = []
    for request_data in all_requests:
        name = resolve_variables(request_data["name"], variables)
        request = request_data["request"]
        method = request["method"]

        url = resolve_variables(request["url"]["raw"], variables)
        headers = {resolve_variables(h["key"], variables): resolve_variables(h["value"], variables) for h in request.get("header", [])}
        body = resolve_variables(request.get("body", {}).get("raw", ""), variables)

        # logger.debug(f"Executing request: {name} | Method: {method} | URL: {url} | Headers: {headers} | Body: {body}")

        try:
            # Execute the request based on the method
            if method.upper() == "GET":
                res = requests.get(url, headers=headers, verify=False)
            elif method.upper() == "POST":
                res = requests.post(url, headers=headers, data=body, verify=False)
            elif method.upper() == "PUT":
                res = requests.put(url, headers=headers, data=body, verify=False)
            elif method.upper() == "DELETE":
                res = requests.delete(url, headers=headers, verify=False)
            else:
                results.append((name, "UNKNOWN METHOD", "FAIL", None))
                continue

            # Determine pass/fail status
            status = "PASS" if res.status_code < 400 else "FAIL"

            # Store the result
            results.append((name, res.status_code, status))
            logger.debug(f"Request {name} executed with status: {res.status_code}")

        except Exception as e:
            # Handle exceptions
            results.append((name, "ERROR", "FAIL"))
            logger.error(f"Error executing request {name}: {e}")

    # Print detailed results
    if args.verbose:
        print("\nDetailed Execution Results:")
        for name, status_code, status in results:
            print(f"{name} - {status_code} - {status}")

    # Print summary
    pass_count = sum(1 for result in results if result[2] == "PASS")
    total_count = len(results)
    print(f"\nSUMMARY: {pass_count}/{total_count} PASS")
