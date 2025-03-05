import gitlab
import os
import logging
import threading
from dotenv import load_dotenv
from time import sleep
from datetime import datetime
import sys
import warnings

# Suppress InsecureRequestWarning if SSL verification is disabled
from urllib3.exceptions import InsecureRequestWarning
warnings.simplefilter('ignore', InsecureRequestWarning)

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
THRESHOLD = int(os.getenv("THRESHOLD", 3))  # Threshold for job failure count

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
    """
    Load repository URLs from file and convert them to project paths.
    E.g., "https://gitlab.com/namespace/project.git" -> "namespace/project"
    """
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
    """
    Initialize and authenticate a GitLab client using the provided URL and token.
    """
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
    """
    Monitor the latest pipeline for the given repository.
    Retry failed or canceled jobs (tracked by job name) up to THRESHOLD times.
    """
    success = False
    failed_pipelines = []
    # Track failures by job name
    job_failures_by_name = {}  # e.g., {"upload-model": <failure_count>}
    retries = 0

    logger.info(f"Starting monitoring for repository: {repo_path}")

    try:
        project = gl.projects.get(repo_path)
        # Get the latest pipeline
        pipelines = project.pipelines.list(per_page=1, order_by='id', sort='desc', get_all=False)
        if not pipelines:
            logger.warning(f"No pipelines found for repository {repo_path}. Marking as failed.")
            return {
                "repo": repo_path,
                "success": False,
                "failed_pipelines": ["No pipeline found"],
                "last_pipeline_url": None,
                "retries": 0
            }

        pipeline = pipelines[0]
        logger.info(f"Latest pipeline for {repo_path} is ID {pipeline.id}")

        while True:
            pipeline.refresh()  # Refresh the pipeline status
            jobs = pipeline.jobs.list(all=True)  # Partial job objects

            if pipeline.status == "success":
                logger.info(f"Pipeline {pipeline.id} for repository {repo_path} succeeded!")
                success = True
                break

            failed_any_job = False

            for partial_job in jobs:
                try:
                    # Retrieve the full job object
                    full_job = project.jobs.get(partial_job.id)
                except Exception as e:
                    logger.error(f"Could not retrieve full job object for job {partial_job.id}: {e}")
                    failed_any_job = True
                    break

                full_job.refresh()

                if full_job.status in ["failed", "canceled"]:
                    # Increment counter by job name
                    job_name = full_job.name
                    job_failures_by_name.setdefault(job_name, 0)
                    
                    if job_failures_by_name[job_name] < THRESHOLD:
                        job_failures_by_name[job_name] += 1
                        retries += 1

                        logger.error(
                            f"Job '{job_name}' for pipeline {pipeline.id} failed "
                            f"{job_failures_by_name[job_name]} time(s). Retrying..."
                        )
                        try:
                            full_job.retry()
                            sleep(5)
                        except Exception as e:
                            logger.error(f"Failed to retry job '{job_name}': {e}")
                            failed_any_job = True
                            break
                    else:
                        logger.error(
                            f"Job '{job_name}' for pipeline {pipeline.id} failed more than "
                            f"{THRESHOLD} times. Marking pipeline as failed."
                        )
                        failed_pipelines.append(
                            f"Pipeline {pipeline.id} failed due to job '{job_name}' "
                            f"exceeding {THRESHOLD} failures."
                        )
                        failed_any_job = True
                        break  # Stop checking other jobs; pipeline is effectively failed

            if failed_any_job:
                # We either hit a threshold or an unrecoverable error
                break

            # If pipeline is running/pending/canceled/failed but we haven't exceeded threshold
            if pipeline.status not in ["success", "failed", "canceled"]:
                logger.info(
                    f"Pipeline {pipeline.id} status is {pipeline.status}. Checking again in 5 seconds..."
                )
                sleep(5)
            else:
                # If pipeline is 'failed' or 'canceled' but no job exceeded threshold,
                # we continue checking in case there's a new job or a previously failed job
                pass

        # Prepare the result for the summary
        if success:
            return {
                "repo": repo_path,
                "success": True,
                "failed_pipelines": [],
                "last_pipeline_url": f"{GITLAB_URL}/{repo_path}/pipelines/{pipeline.id}",
                "retries": retries
            }
        else:
            return {
                "repo": repo_path,
                "success": False,
                "failed_pipelines": failed_pipelines if failed_pipelines else [f"Pipeline {pipeline.id} did not succeed"],
                "last_pipeline_url": None,
                "retries": retries
            }

    except Exception as e:
        logger.error(f"Error monitoring repository {repo_path}: {e}")
        return {
            "repo": repo_path,
            "success": False,
            "failed_pipelines": [f"Exception: {str(e)}"],
            "last_pipeline_url": None,
            "retries": 0
        }

# Thread class for repository monitoring
class MonitorThread(threading.Thread):
    """
    A thread class to monitor pipelines for a single repository.
    """
    def __init__(self, repo_path, gl):
        super().__init__()
        self.repo_path = repo_path
        self.gl = gl
        self.result = None

    def run(self):
        self.result = monitor_repository(self.repo_path, self.gl)

# Generate summary report
def generate_summary(results):
    """
    Generate a summary report of all monitored repositories.
    Includes sub-summaries and a list of failed pipelines.
    """
    logger.info("\nSUMMARY REPORT")
    logger.info("-" * 50)

    total_repos = len(results)
    passed_repos = 0
    failed_repos = 0
    failed_pipelines_list = []

    # Show sub-summary for each repo
    for result in results:
        logger.info(f"\nRepository: {result['repo']}")
        if result["success"]:
            passed_repos += 1
            logger.info(f"  - Status: PASSED")
            logger.info(f"  - Pipeline URL: {result['last_pipeline_url']}")
        else:
            failed_repos += 1
            logger.error(f"  - Status: FAILED")
            for fp in result["failed_pipelines"]:
                failed_pipelines_list.append(f"{result['repo']} - {fp}")

        logger.info(f"  - Total Job Retries: {result['retries']}")
        logger.info("-" * 50)

    # Show failed pipelines
    if failed_pipelines_list:
        logger.error("\nFAILED PIPELINES:")
        for failed_pipeline in failed_pipelines_list:
            logger.error(f"  - {failed_pipeline}")

    logger.info("-" * 50)
    logger.info(f"Total Repositories Monitored: {total_repos}")
    logger.info(f"Passed: {passed_repos}/{total_repos}")
    logger.info(f"Failed: {failed_repos}/{total_repos}")
    logger.info("-" * 50)

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
