import boto3
import os
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

ENDPOINT_URL = "https://cloudstorage.onefs.dell.com"

def copy_rasa_models_s3(env1, env2):
    teams = ["gta", "cti", "database", "general", "server", "digital"]

    # Initialize S3 client with a custom endpoint
    s3 = boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        endpoint_url=ENDPOINT_URL,
        verify=False  # Disable SSL validation for testing
    )

    bucket_name = "cloudstorage.onefs.dell.com"

    for team in teams:
        source_key = f"babblebot/bots/{team}/models/{env2}/default.tar.gz"
        destination_key = f"babblebot/bots/{team}/models/{env1}/default.tar.gz"

        logging.info(f"Attempting to copy model for team '{team}'...")
        logging.info(f"Source Bucket: {bucket_name}, Source Key: {source_key}")
        logging.info(f"Destination Bucket: {bucket_name}, Destination Key: {destination_key}")

        try:
            s3.copy_object(
                Bucket=bucket_name,
                CopySource={'Bucket': bucket_name, 'Key': source_key},
                Key=destination_key
            )
            logging.info(f"Successfully copied model for team '{team}' from {env2} to {env1}.")
        except s3.exceptions.NoSuchBucket:
            logging.error(f"Bucket '{bucket_name}' does not exist.")
        except s3.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'AccessDenied':
                logging.error("Access denied. Please check your AWS credentials and permissions.")
            else:
                logging.error(f"ClientError occurred: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    # Get user inputs
    env1 = input("Enter the destination environment (env1): ").strip()
    env2 = input("Enter the source environment (env2): ").strip()

    # Execute the copy operation
    copy_rasa_models_s3(env1, env2)
