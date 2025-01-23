"""
sample usage:

make run SCRIPT=stop_pipeline_runs.py ARGS="-b 1"
make run SCRIPT=stop_pipeline_runs.py ARGS="--all"
make run SCRIPT=stop_pipeline_runs.py ARGS="-a 1"
"""

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
        description="Stop GitLab pipelines based on a specified time condition."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-a",
        "--after",
        type=str,
        help=(
            "Stop pipelines created AFTER (NOW - X days). "
            "Example: '--after 1' will stop pipelines updated after (NOW - 1 day). "
            "You may also pass an ISO8601 date/time instead."
        )
    )
    group.add_argument(
        "-b",
        "--before",
        type=str,
        help=(
            "Stop pipelines created BETWEEN (NOW - X days) and NOW. "
            "Example: '--before 1' will stop pipelines updated after (NOW - 1 day) and before NOW. "
            "You may also pass an ISO8601 date/time instead."
        )
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Stop all pipelines in the repository, ignoring the time filters."
    )
    parser.add_argument(
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

def load_repositories(file_path):
    with open(file_path, "r") as f:
        repositories = [
            line.strip().replace(f"{GITLAB_URL.rstrip('/')}/", "").replace(".git", "")
            for line in f
            if line.strip()
        ]
    logger.info(f"Loaded {len(repositories)} repositories from {file_path}.")
    return repositories

def initialize_gitlab_client(url, token) -> gitlab.Gitlab:
    try:
        gl = gitlab.Gitlab(url, private_token=token, ssl_verify=False)
        gl.auth()
        logger.info("Connected and authenticated to GitLab instance.")
        return gl
    except Exception as e:
        logger.error(f"Failed to connect or authenticate to GitLab: {e}")
        exit(1)

def stop_pipelines(
    gl: gitlab.Gitlab, 
    after: str, 
    before: str, 
    all_pipelines: bool, 
    branch_name_filter, 
    repositories
):
    """
    :param after:    e.g., '1' => stop pipelines updated after (NOW - 1 day)
    :param before:   e.g., '1' => stop pipelines updated between (NOW - 1 day) and NOW
    :param all_pipelines: ignore time filters if True
    """

    # Convert user input to the actual ISO date filters
    after_iso, before_iso = None, None
    reference_time_iso = None

    # NOTE: "after X days" => stop pipelines updated after (NOW - X days)
    # NOTE: "before X days" => stop pipelines before (NOW - X days), which is from (NOW - X days) until the beginning of time

    if after:  # e.g., user gave "--after 1" or an ISO date
        try:
            # Attempt to interpret 'after' as an integer or float
            days_float = float(after)
            # before_iso = datetime.utcnow().isoformat()
            reference_time_iso = (datetime.utcnow() - timedelta(days=days_float)).isoformat()
        except ValueError:
            # The user provided an ISO date/time string
            reference_time_iso = after
        after_iso = reference_time_iso

    if before:
        try:
            # Attempt to interpret 'before' as an integer or float
            days_float = float(before)
            # after_iso = (datetime.utcnow() - timedelta(days=days_float)).isoformat()
            reference_time_iso = (datetime.utcnow() - timedelta(days=days_float)).isoformat()
        except ValueError:
            # The user provided an ISO date/time string
            # In that scenario, let's assume we want updated_after=that date, updated_before=now
            # after_iso = before
            reference_time_iso = before
        before_iso = reference_time_iso




    logger.info(f"Stopping pipelines created AFTER: {after_iso}, BEFORE: {before_iso}")

    stopped_pipelines = {}

    for repo_path in repositories:
        logger.info(f"Checking repository: {repo_path}")

        try:
            project = gl.projects.get(repo_path)

            # If --all flag is passed, do not use time filters (fetch all pipelines)
            assert(all_pipelines or after or before)
            if all_pipelines:
                pipelines = project.pipelines.list(all=True)
            else:
                # Use updated_after & updated_before if they exist
                pipelines = project.pipelines.list(
                    updated_after=after_iso,
                    updated_before=before_iso,
                    all=True,
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

            # Update dictionary with final counts
            stopped_pipelines[repo_path].update(
                {
                    "detected": detected_count,
                    "stopped": stopped_count,
                    "skipped": skipped_count
                }
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
    logger.info(f"Total pipelines stopped: {total_stopped}/{total_detected}")
    logger.info(f"Total pipelines skipped: {total_skipped}/{total_detected}")
    logger.info("-=-=-=-=-=")

def main():
    args = parse_arguments()
    after = args.after
    before = args.before
    all_pipelines = args.all

    # Validate arguments
    if all_pipelines and (after or before):
        logger.error("The --all flag cannot be used with --after or --before.")
        exit(1)

    repositories = load_repositories(REPOS_FILE)
    gl = initialize_gitlab_client(GITLAB_URL, PRIVATE_TOKEN)
    stopped_pipelines_dict = stop_pipelines(gl, after, before, all_pipelines, args.branch_name_filter, repositories)
    generate_summary(stopped_pipelines_dict, verbose=args.verbose)

if __name__ == "__main__":
    main()
