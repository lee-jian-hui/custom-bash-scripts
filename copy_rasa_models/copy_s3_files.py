import boto3
import os
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)



ENDPOINT_URL = os.getenv("ENDPOINT_URL")
BUCKET_NAME = os.getenv("BUCKET_NAME")



def ping_s3_client(s3_client):
    """
    Pings the S3 client by listing buckets to ensure it is configured correctly.
    """
    try:
        response = s3_client.list_buckets()
        logging.info("Successfully connected to S3. Buckets available:")
        for bucket in response['Buckets']:
            logging.info(f"  - {bucket['Name']}")
        return True
    except Exception as e:
        logging.error(f"Failed to connect to S3: {e}")
        return False


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
    ping_s3_client(s3)
    
    for team in teams:
        source_key = f"bots/{team}/models/{env2}/default.tar.gz"
        destination_key = f"bots/{team}/models/{env1}/default.tar.gz"

        logging.info(f"Attempting to copy model for team '{team}'...")
        logging.info(f"Source Bucket: {BUCKET_NAME}, Source Key: {source_key}")
        logging.info(f"Destination Bucket: {BUCKET_NAME}, Destination Key: {destination_key}")

        try:
            s3.copy_object(
                Bucket=BUCKET_NAME,
                CopySource={'Bucket': BUCKET_NAME, 'Key': source_key},
                Key=destination_key
            )
            logging.info(f"Successfully copied model for team '{team}' from {env2} to {env1}.")
        except s3.exceptions.NoSuchBucket:
            logging.error(f"Bucket '{BUCKET_NAME}' does not exist.")
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
