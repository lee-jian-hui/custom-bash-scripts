""" 
make run SCRIPT=run_pipelines.py ARGS="-b feature/batch_update_config_yml"
"""
# Modified Script
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
SUMMARY_REPORT_FILENAME = f"pipeline_runs_summary.txt"

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

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Trigger and monitor GitLab pipelines for multiple repositories."
    )
    
    parser.add_argument(
        "-loop",
        "--loop",
        action="store_true",
        help="Continuously monitor the triggered pipelines until completion."
    )
    parser.add_argument(
        "-b",
        "--branch",
        type=str,
        required=True,
        help="Target branch to run pipelines on."
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=int,
        default=60,
        help="Interval in seconds between pipeline status checks (default: 60)."
    )
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
        gl.auth()
        logger.info("Connected and authenticated to GitLab instance.")
        return gl
    except Exception as e:
        logger.error(f"Failed to connect or authenticate to GitLab: {e}")
        exit(1)

def trigger_pipelines(gl, repositories, target_branch):
    failed_repos = []
    successful_repos = []
    pipeline_urls = []

    for repo_url in repositories:
        try:
            project_path = repo_url.replace(GITLAB_URL.rstrip('/') + "/", "").replace(".git", "")
            logger.info(f"Processing repository: {project_path}")

            try:
                project = gl.projects.get(project_path)
            except gitlab.exceptions.GitlabGetError as e:
                logger.error(f"Failed to get project '{project_path}': {e}")
                failed_repos.append({"repo_url": repo_url, "error": f"Project not found or access denied: {e}"})
                continue

            try:
                pipeline = project.pipelines.create({'ref': target_branch})
                pipeline_url = pipeline.web_url
                pipeline_urls.append(pipeline_url)
                logger.info(f"Successfully triggered pipeline ID {pipeline.id} on branch '{target_branch}' for repository '{project_path}'. Pipeline URL: {pipeline_url}")
                successful_repos.append({"repo_url": repo_url, "pipeline_id": pipeline.id, "pipeline_url": pipeline_url, "project": project})
            except gitlab.exceptions.GitlabCreateError as e:
                error_message = e.error_message
                logger.error(f"Failed to trigger pipeline for '{project_path}': {error_message}")
                failed_repos.append({"repo_url": repo_url, "error": error_message})
        except Exception as e:
            error_message = str(e)
            failed_repos.append({"repo_url": repo_url, "error": error_message})
            logger.error(f"An unexpected error occurred for repository '{repo_url}': {error_message}")

    return successful_repos, failed_repos, pipeline_urls

def generate_summary(successful_repos, failed_repos, pipeline_urls, completed_pipelines, failed_pipelines, pending_pipelines):
    logger.info("\n--- Summary Report ---")
    logger.info(f"Total Repositories Processed: {len(successful_repos) + len(failed_repos)}")
    logger.info(f"Total Successful Pipeline Triggers: {len(successful_repos)}")
    logger.info(f"Total Failed Pipeline Triggers: {len(failed_repos)}")

    if pipeline_urls:
        logger.info("\n--- Triggered Pipeline URLs ---")
        for url in pipeline_urls:
            logger.info(f"Pipeline URL: {url}")

    if failed_repos:
        logger.info("\n--- Failed Pipeline Triggers ---")
        for failed_repo in failed_repos:
            logger.info(f"Repository: {failed_repo['repo_url']} | Error: {failed_repo['error']}")

    with open(SUMMARY_REPORT_FILENAME, "w") as report_file:
        report_file.write(f"--- Summary Report ---\n")
        report_file.write(f"Total Repositories Processed: {len(successful_repos) + len(failed_repos)}\n")
        report_file.write(f"Total Successful Pipeline Triggers: {len(successful_repos)}\n")
        report_file.write(f"Total Failed Pipeline Triggers: {len(failed_repos)}\n")

        if pipeline_urls:
            report_file.write("\n--- Triggered Pipeline URLs ---\n")
            for url in pipeline_urls:
                report_file.write(f"{url}\n")

        if failed_repos:
            report_file.write("\n--- Failed Pipeline Triggers ---\n")
            for failed_repo in failed_repos:
                report_file.write(f"Repository: {failed_repo['repo_url']} | Error: {failed_repo['error']}\n")

def main():
    args = parse_arguments()
    target_branch = args.branch

    repositories = load_repositories(REPOS_FILE)
    gl = initialize_gitlab_client(GITLAB_URL, PRIVATE_TOKEN)

    successful_repos, failed_repos, pipeline_urls = trigger_pipelines(gl, repositories, target_branch)

    completed_pipelines = []
    failed_pipelines = []
    pending_pipelines = {}

    generate_summary(successful_repos, failed_repos, pipeline_urls, completed_pipelines, failed_pipelines, pending_pipelines)

    logger.info("Pipeline processing completed for all repositories.")

if __name__ == "__main__":
    main()
