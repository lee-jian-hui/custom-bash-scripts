import gitlab
import os
import logging
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("stop_pipelines.log", mode="a")
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
GITLAB_URL = os.getenv("GITLAB_URL")
PRIVATE_TOKEN = os.getenv("PRIVATE_TOKEN")
DEFAULT_TIMEFRAME = os.getenv("DEFAULT_TIMEFRAME")  # Default timeframe in days
REPOS_FILE = os.getenv("REPOS_FILE", "repositories.txt")

# Validate environment variables
if not GITLAB_URL:
    logger.error("GITLAB_URL is not set.")
    exit(1)
logger.info(f"GITLAB_URL: {GITLAB_URL}")

if not PRIVATE_TOKEN:
    logger.error("PRIVATE_TOKEN is not set.")
    exit(1)

if not os.path.isfile(REPOS_FILE):
    logger.error(f"{REPOS_FILE} not found.")
    exit(1)

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Stop GitLab pipelines running within a specified timeframe."
    )
    parser.add_argument(
        "-t",
        "--timeframe",
        type=int,
        help="Timeframe in days to consider pipelines for stopping. If not provided, value from .env will be used or user will be prompted."
    )
    parser.add_argument(
        "-b",
        "--branch-name-filter",
        type=str,
        nargs='*',
        help="List of branch names to filter pipelines. Leave empty to consider all branches."
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output to list all stopped pipelines for each repository."
    )
    return parser.parse_args()

def get_timeframe_from_input_or_env(args_timeframe):
    if args_timeframe is not None:
        logger.info(f"Using timeframe from user input: {args_timeframe} days.")
        return args_timeframe

    if DEFAULT_TIMEFRAME is not None:
        logger.info(f"Using default timeframe from environment variables: {DEFAULT_TIMEFRAME} days.")
        return int(DEFAULT_TIMEFRAME)

    while True:
        try:
            user_input = int(input("Enter the timeframe in days to consider pipelines for stopping: "))
            logger.info(f"Using timeframe from user input: {user_input} days.")
            return user_input
        except ValueError:
            print("Invalid input. Please enter a valid number of days.")

def load_repositories(file_path):
    with open(file_path, "r") as f:
        repositories = [
            line.strip().replace(f"{GITLAB_URL.rstrip('/')}/", "").replace(".git", "")
            for line in f
            if line.strip()
        ]
    logger.info(f"Loaded {len(repositories)} repositories from {file_path}.")
    return repositories

def initialize_gitlab_client(url, token):
    try:
        gl = gitlab.Gitlab(url, private_token=token, ssl_verify=False)
        gl.auth()
        logger.info("Connected and authenticated to GitLab instance.")
        return gl
    except Exception as e:
        logger.error(f"Failed to connect or authenticate to GitLab: {e}")
        exit(1)

def stop_pipelines(gl, timeframe, branch_name_filter, repositories):
    cutoff_time = datetime.utcnow() - timedelta(days=timeframe)
    logger.info(f"Stopping pipelines created between {cutoff_time} and now.")

    stopped_pipelines = {}

    for repo_path in repositories:
        logger.info(f"Checking repository: {repo_path}")

        try:
            project = gl.projects.get(repo_path)
            # Fetch pipelines only within the specified timeframe
            pipelines = project.pipelines.list(
                updated_after=cutoff_time.isoformat(),
                updated_before=datetime.utcnow().isoformat(),
                as_list=True
            )
            detected_count = 0
            stopped_count = 0
            skipped_count = 0
            stopped_pipelines[repo_path] = {"detected": 0, "stopped": 0, "skipped": 0, "pipelines": []}

            for pipeline in pipelines:
                detected_count += 1

                # Skip pipelines that do not match the branch filter
                if branch_name_filter and pipeline.ref not in branch_name_filter:
                    skipped_count += 1
                    continue

                # Process pipelines that are in 'running' or 'pending' status
                if pipeline.status in ['running', 'pending']:
                    try:
                        pipeline.cancel()
                        logger.info(f"Stopped pipeline {pipeline.id} on branch {pipeline.ref}.")
                        stopped_pipelines[repo_path]["pipelines"].append(pipeline)
                        stopped_count += 1
                    except Exception as e:
                        logger.error(f"Failed to stop pipeline {pipeline.id}: {e}")
                else:
                    # Skip pipelines that are not eligible for stopping
                    skipped_count += 1

            stopped_pipelines[repo_path].update(
                {"detected": detected_count, "stopped": stopped_count, "skipped": skipped_count}
            )

        except Exception as e:
            logger.error(f"Error fetching pipelines for repository {repo_path}: {e}")

    return stopped_pipelines

def generate_summary(stopped_pipelines, verbose=False):
    logger.info("REPORT")
    logger.info("-=-=-=-=-=")

    total_detected = 0
    total_stopped = 0
    total_skipped = 0

    for repo, data in stopped_pipelines.items():
        logger.info(f"{repo}:")
        logger.info(f"Total pipelines detected: {data['detected']}")
        logger.info(f"Total pipelines stopped: {data['stopped']}")
        logger.info(f"Total pipelines skipped: {data['skipped']}")

        if verbose and data['stopped'] > 0:
            logger.info(f"Stopped pipelines for {repo}:")
            for pipeline in data['pipelines']:
                logger.info(
                    f"  Pipeline ID: {pipeline.id}, Branch: {pipeline.ref}, URL: {pipeline.web_url}"
                )

        logger.info("-=-=-=-=-=")

        total_detected += data['detected']
        total_stopped += data['stopped']
        total_skipped += data['skipped']

    logger.info("SUMMARY")
    logger.info(f"\n\n")
    logger.info(f"-=-=-=-=")
    logger.info(f"Total pipelines stopped: {total_stopped}/{total_detected}")
    logger.info(f"Total pipelines skipped: {total_skipped}/{total_detected}")
    logger.info(f"-=-=-=-=")
    logger.info(f"\n\n")

def main():
    args = parse_arguments()
    timeframe = get_timeframe_from_input_or_env(args.timeframe)
    branch_name_filter = args.branch_name_filter

    repositories = load_repositories(REPOS_FILE)
    gl = initialize_gitlab_client(GITLAB_URL, PRIVATE_TOKEN)
    stopped_pipelines = stop_pipelines(gl, timeframe, branch_name_filter, repositories)
    generate_summary(stopped_pipelines, verbose=args.verbose)

if __name__ == "__main__":
    main()
