import gitlab
import os
import logging
import threading
from dotenv import load_dotenv
from time import sleep
from datetime import datetime
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("monitor_pipelines.log", mode="a")
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
GITLAB_URL = os.getenv("GITLAB_URL")
PRIVATE_TOKEN = os.getenv("PRIVATE_TOKEN")
REPOS_FILE = os.getenv("REPOS_FILE", "repositories.txt")
THRESHOLD = int(os.getenv("THRESHOLD", 3))  # Threshold for pipeline failure count

# Validate environment variables
if not GITLAB_URL:
    logger.error("GITLAB_URL is not set.")
    exit(1)

if not PRIVATE_TOKEN:
    logger.error("PRIVATE_TOKEN is not set.")
    exit(1)

if not os.path.isfile(REPOS_FILE):
    logger.error(f"{REPOS_FILE} not found.")
    exit(1)

# Load repositories from file
def load_repositories(file_path):
    """Load repository URLs from file and convert them to project paths."""
    with open(file_path, "r") as f:
        repositories = [
            line.strip().replace(f"{GITLAB_URL.rstrip('/')}/", "").replace(".git", "")
            for line in f
            if line.strip()
        ]
    logger.info(f"Loaded {len(repositories)} repositories from {file_path}.")
    return repositories

# Initialize GitLab client
def initialize_gitlab_client(url, token):
    """Initialize and authenticate GitLab client."""
    try:
        gl = gitlab.Gitlab(url, private_token=token, ssl_verify=False)
        gl.auth()
        logger.info("Connected and authenticated to GitLab instance.")
        return gl
    except Exception as e:
        logger.error(f"Failed to connect or authenticate to GitLab: {e}")
        exit(1)

# Monitor pipeline for each repository
def monitor_repository(repo_path, gl):
    """Monitor the latest pipeline for the repository."""
    failure_count = 0
    success = False
    repo_name = repo_path.split("/")[-1]

    while failure_count < THRESHOLD:
        try:
            project = gl.projects.get(repo_path)
            pipeline = project.pipelines.list(limit=1)[0]  # Get latest pipeline
            
            logger.info(f"Monitoring repository: {repo_path}, latest pipeline ID: {pipeline.id}, Status: {pipeline.status}")

            if pipeline.status == 'success':
                logger.info(f"Pipeline {pipeline.id} for repository {repo_path} succeeded!")
                success = True
                break
            elif pipeline.status in ['failed', 'canceled']:
                failure_count += 1
                logger.error(f"Pipeline {pipeline.id} for repository {repo_path} failed, retrying... (Failure count: {failure_count})")
            else:
                # If the pipeline is running or pending, wait before retrying
                logger.info(f"Pipeline {pipeline.id} is {pipeline.status}, retrying in 10 seconds...")
                sleep(10)
        
        except Exception as e:
            logger.error(f"Error monitoring repository {repo_path}: {e}")
            break

    return {
        "repo": repo_path,
        "success": success,
        "failure_count": failure_count,
        "last_pipeline_url": f"{GITLAB_URL}/{repo_path}/pipelines/{pipeline.id}" if success else None
    }

# Thread class for repository monitoring
class MonitorThread(threading.Thread):
    def __init__(self, repo_path, gl):
        super().__init__()
        self.repo_path = repo_path
        self.gl = gl
        self.result = None

    def run(self):
        self.result = monitor_repository(self.repo_path, self.gl)

# Generate summary report
def generate_summary(results):
    logger.info("SUMMARY REPORT")
    logger.info("-" * 20)

    total_repos = len(results)
    passed_repos = 0
    failed_repos = 0

    for result in results:
        logger.info(f"Repository: {result['repo']}")
        if result["success"]:
            passed_repos += 1
            logger.info(f"  Passed: {result['last_pipeline_url']}")
        else:
            failed_repos += 1
            logger.error(f"  Failed (after {result['failure_count']} failures)")

    logger.info("-" * 20)
    logger.info(f"Total Repositories: {total_repos}")
    logger.info(f"Passed: {passed_repos}/{total_repos}")
    logger.info(f"Failed: {failed_repos}/{total_repos}")
    logger.info("-" * 20)

# Main function to start monitoring
def main():
    # Load repositories and initialize GitLab client
    repositories = load_repositories(REPOS_FILE)
    gl = initialize_gitlab_client(GITLAB_URL, PRIVATE_TOKEN)

    # Create and start threads for each repository
    threads = []
    results = []

    for repo in repositories:
        thread = MonitorThread(repo, gl)
        threads.append(thread)
        thread.start()

    # Wait for all threads to finish and collect results
    for thread in threads:
        thread.join()
        results.append(thread.result)

    # Generate summary report
    generate_summary(results)

if __name__ == "__main__":
    main()
