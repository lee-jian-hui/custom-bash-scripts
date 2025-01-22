import gitlab
import os
import logging
import argparse
import time
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("script.log", mode="a")
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
GITLAB_URL = os.getenv("GITLAB_URL")
PRIVATE_TOKEN = os.getenv("PRIVATE_TOKEN")
REPOS_FILE = os.getenv("REPOS_FILE", "repositories.txt")
SUMMARY_REPORT_FILENAME = f"{__name__}_summary.txt"

# Validate environment variables
if not GITLAB_URL:
    logger.error("GITLAB_URL is not set.")
    exit(1)
logger.info(f"GITLAB_URL: {GITLAB_URL}")

if not PRIVATE_TOKEN:
    logger.error("PRIVATE_TOKEN is not set.")
    exit(1)

if not os.path.isfile(REPOS_FILE):
    logger.error(f"{REPOS_FILE} not found!")
    exit(1)

import argparse

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Trigger and monitor GitLab pipelines for multiple repositories."
    )
    
    # Loop flag
    parser.add_argument(
        "-loop",
        "--loop",
        action="store_true",
        help="Continuously monitor the triggered pipelines until completion."
    )
    
    # Branch argument (now required)
    parser.add_argument(
        "-b",
        "--branch",
        type=str,
        required=True,  # Makes the branch argument mandatory
        help="Target branch to run pipelines on."
    )
    
    # Interval argument with default value
    parser.add_argument(
        "-i",
        "--interval",
        type=int,
        default=60,
        help="Interval in seconds between pipeline status checks (default: 60)."
    )
    
    # Timeout argument with default value
    parser.add_argument(
        "-t",
        "--timeout",
        type=int,
        default=3600,
        help="Maximum time in seconds to wait for pipelines to complete (default: 3600)."
    )
    
    return parser.parse_args()


def load_repositories(file_path):
    with open(file_path, "r") as f:
        repositories = [line.strip() for line in f if line.strip()]
    logger.info(f"Loaded {len(repositories)} repositories from {file_path}.")
    return repositories

def initialize_gitlab_client(url, token):
    try:
        gl = gitlab.Gitlab(url, private_token=token, ssl_verify=False)
        gl.auth()  # Authenticate to ensure the token is valid
        logger.info("Connected and authenticated to GitLab instance.")
        return gl
    except Exception as e:
        logger.error(f"Failed to connect or authenticate to GitLab: {e}")
        exit(1)

def trigger_pipelines(gl, repositories, target_branch):
    failed_repos = []
    successful_repos = []
    for repo_url in repositories:
        try:
            # Extract project path
            project_path = repo_url.replace(GITLAB_URL.rstrip('/') + "/", "").replace(".git", "")
            logger.info(f"Processing repository: {project_path}")

            # Get the project
            try:
                project = gl.projects.get(project_path)
            except gitlab.exceptions.GitlabGetError as e:
                logger.error(f"Failed to get project '{project_path}': {e}")
                failed_repos.append({"repo_url": repo_url, "error": f"Project not found or access denied: {e}"})
                continue

            # Trigger the pipeline
            try:
                pipeline = project.pipelines.create({'ref': target_branch})
                logger.info(f"Successfully triggered pipeline ID {pipeline.id} on branch '{target_branch}' for repository '{project_path}'.")
                successful_repos.append({"repo_url": repo_url, "pipeline_id": pipeline.id, "project": project})
            except gitlab.exceptions.GitlabCreateError as e:
                # Handle cases where pipeline creation failed
                error_message = e.error_message
                logger.error(f"Failed to trigger pipeline for '{project_path}': {error_message}")
                failed_repos.append({"repo_url": repo_url, "error": error_message})
        except Exception as e:
            error_message = str(e)
            failed_repos.append({"repo_url": repo_url, "error": error_message})
            logger.error(f"An unexpected error occurred for repository '{repo_url}': {error_message}")
    return successful_repos, failed_repos

def monitor_pipelines(successful_repos, interval, timeout):
    start_time = time.time()
    pending_pipelines = {repo['pipeline_id']: repo for repo in successful_repos}
    completed_pipelines = []
    failed_pipelines = []

    logger.info("Starting pipeline monitoring...")

    while pending_pipelines:
        current_time = time.time()
        elapsed_time = current_time - start_time
        if elapsed_time > timeout:
            logger.warning("Timeout reached while monitoring pipelines.")
            break

        logger.info(f"Checking status of {len(pending_pipelines)} pipelines...")
        to_remove = []
        for pipeline_id, repo in pending_pipelines.items():
            project = repo['project']
            try:
                pipeline = project.pipelines.get(pipeline_id)
                if pipeline.status in ['success', 'failed', 'canceled', 'skipped', 'manual']:
                    # For manual jobs, check if they've been run
                    if pipeline.status == 'manual':
                        # You might need to handle manual jobs differently based on your pipeline setup
                        logger.info(f"Pipeline {pipeline_id} is in 'manual' status. Awaiting manual intervention.")
                        continue  # Or implement logic to trigger manual jobs if possible
                    else:
                        logger.info(f"Pipeline {pipeline_id} completed with status: {pipeline.status}.")
                        if pipeline.status == 'success':
                            completed_pipelines.append(repo)
                        else:
                            failed_pipelines.append(repo)
                        to_remove.append(pipeline_id)
                else:
                    logger.info(f"Pipeline {pipeline_id} is still running with status: {pipeline.status}.")
            except gitlab.exceptions.GitlabGetError as e:
                logger.error(f"Failed to get status for pipeline {pipeline_id}: {e}")
                failed_pipelines.append(repo)
                to_remove.append(pipeline_id)

        # Remove completed or failed pipelines from pending
        for pid in to_remove:
            pending_pipelines.pop(pid, None)

        if not pending_pipelines:
            break

        logger.info(f"Waiting for {interval} seconds before next check...")
        time.sleep(interval)

    return completed_pipelines, failed_pipelines, pending_pipelines

def generate_summary(successful_repos, failed_repos, completed_pipelines, failed_pipelines, pending_pipelines):
    logger.info("\n--- Summary Report ---")
    logger.info(f"Total Repositories Processed: {len(successful_repos) + len(failed_repos)}")
    logger.info(f"Total Successful Pipeline Triggers: {len(successful_repos)}")
    logger.info(f"Total Failed Pipeline Triggers: {len(failed_repos)}")
    if completed_pipelines or failed_pipelines or pending_pipelines:
        logger.info(f"Total Pipelines Monitored: {len(completed_pipelines) + len(failed_pipelines) + len(pending_pipelines)}")
        logger.info(f"  - Completed Successfully: {len(completed_pipelines)}")
        logger.info(f"  - Completed with Failures: {len(failed_pipelines)}")
        logger.info(f"  - Still Pending: {len(pending_pipelines)}")

    if failed_repos:
        logger.info("\n--- Failed Pipeline Triggers ---")
        for failed_repo in failed_repos:
            logger.info(f"Repository: {failed_repo['repo_url']} | Error: {failed_repo['error']}")

    if completed_pipelines:
        logger.info("\n--- Successfully Completed Pipelines ---")
        for repo in completed_pipelines:
            logger.info(f"Repository: {repo['repo_url']} | Pipeline ID: {repo['pipeline_id']}")

    if failed_pipelines:
        logger.info("\n--- Pipelines Completed with Failures ---")
        for repo in failed_pipelines:
            logger.info(f"Repository: {repo['repo_url']} | Pipeline ID: {repo['pipeline_id']}")

    if pending_pipelines:
        logger.info("\n--- Pipelines Still Pending ---")
        for pid, repo in pending_pipelines.items():
            logger.info(f"Repository: {repo['repo_url']} | Pipeline ID: {pid}")

    # Optionally, write to a summary file
    with open(SUMMARY_REPORT_FILENAME, "w") as report_file:
        report_file.write(f"--- Summary Report ---\n")
        report_file.write(f"Total Repositories Processed: {len(successful_repos) + len(failed_repos)}\n")
        report_file.write(f"Total Successful Pipeline Triggers: {len(successful_repos)}\n")
        report_file.write(f"Total Failed Pipeline Triggers: {len(failed_repos)}\n")
        if completed_pipelines or failed_pipelines or pending_pipelines:
            report_file.write(f"Total Pipelines Monitored: {len(completed_pipelines) + len(failed_pipelines) + len(pending_pipelines)}\n")
            report_file.write(f"  - Completed Successfully: {len(completed_pipelines)}\n")
            report_file.write(f"  - Completed with Failures: {len(failed_pipelines)}\n")
            report_file.write(f"  - Still Pending: {len(pending_pipelines)}\n")

        if failed_repos:
            report_file.write("\n--- Failed Pipeline Triggers ---\n")
            for failed_repo in failed_repos:
                report_file.write(f"Repository: {failed_repo['repo_url']} | Error: {failed_repo['error']}\n")

        if completed_pipelines:
            report_file.write("\n--- Successfully Completed Pipelines ---\n")
            for repo in completed_pipelines:
                report_file.write(f"Repository: {repo['repo_url']} | Pipeline ID: {repo['pipeline_id']}\n")

        if failed_pipelines:
            report_file.write("\n--- Pipelines Completed with Failures ---\n")
            for repo in failed_pipelines:
                report_file.write(f"Repository: {repo['repo_url']} | Pipeline ID: {repo['pipeline_id']}\n")

        if pending_pipelines:
            report_file.write("\n--- Pipelines Still Pending ---\n")
            for pid, repo in pending_pipelines.items():
                report_file.write(f"Repository: {repo['repo_url']} | Pipeline ID: {pid}\n")

    logger.info("Summary report generated: summary_report.txt")

def main():
    args = parse_arguments()
    target_branch = args.branch
    loop = args.loop
    interval = args.interval
    timeout = args.timeout

    logger.info(f"Target Branch: {target_branch}")
    if loop:
        logger.info(f"Looping enabled. Pipelines will be monitored every {interval} seconds for up to {timeout} seconds.")

    repositories = load_repositories(REPOS_FILE)
    gl = initialize_gitlab_client(GITLAB_URL, PRIVATE_TOKEN)
    successful_repos, failed_repos = trigger_pipelines(gl, repositories, target_branch)

    completed_pipelines = []
    failed_pipelines = []
    pending_pipelines = {}

    if loop and successful_repos:
        completed_pipelines, failed_pipelines, pending_pipelines = monitor_pipelines(
            successful_repos, interval, timeout
        )

    generate_summary(successful_repos, failed_repos, completed_pipelines, failed_pipelines, pending_pipelines)

    logger.info("Pipeline processing completed for all repositories.")

if __name__ == "__main__":
    main()
