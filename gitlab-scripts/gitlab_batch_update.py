import gitlab
import os
import shutil
import logging
from git import Repo
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

load_dotenv()
# Configuration
GITLAB_URL = os.getenv("GITLAB_URL")
PRIVATE_TOKEN = os.getenv("PRIVATE_TOKEN")
REPOS_FILE = os.getenv("REPOS_FILE", "repositories.txt")
TEMP_FILE = os.getenv("TEMP_FILE", "temp.txt")
TARGET_FILE = os.getenv("TARGET_FILE", "path/to/target/file")

# Validate environment variables
if not GITLAB_URL:
    logger.error(f"GITLAB_URL: {GITLAB_URL} is not set.")
    exit(1)
logger.info(f"GITLAB_URL: {GITLAB_URL}")

if not PRIVATE_TOKEN:
    logger.error("PRIVATE_TOKEN is not set.")
    exit(1)

# DEFAULT INPUTS
DEFAULT_BRANCH_NAME = f'feature/batch_update_{os.path.basename(TARGET_FILE).replace(".", "_")}'
DEFAULT_COMMIT_MSG = f"feat: batch update on {os.path.basename(TARGET_FILE)}"

# Get user input
branch_name = input(f"Enter the name of the new branch to create (off development branch) [default: '{DEFAULT_BRANCH_NAME}'] : ").strip() or DEFAULT_BRANCH_NAME
commit_message = input(f"Enter the commit message for the changes [default: 'feat: batch update on {os.path.basename(TARGET_FILE)}']: ").strip() or DEFAULT_COMMIT_MSG

# Check if required files exist
if not os.path.isfile(REPOS_FILE):
    logger.error(f"{REPOS_FILE} not found!")
    exit(1)

if not os.path.isfile(TEMP_FILE):
    logger.error(f"{TEMP_FILE} not found!")
    exit(1)

# Read repositories
with open(REPOS_FILE, "r") as f:
    repositories = [line.strip() for line in f if line.strip()]
logger.info(f"Loaded {len(repositories)} repositories from {REPOS_FILE}.")

# Initialize GitLab client
try:
    gl = gitlab.Gitlab(GITLAB_URL, private_token=PRIVATE_TOKEN, ssl_verify=False)
    logger.info("Connected to GitLab instance.")
except Exception as e:
    logger.error(f"Failed to connect to GitLab: {e}")
    exit(1)

# Lists to track progress
failed_repos = []
no_changes_repos = []
successful_pushes = 0

# Loop through repositories
for repo_url in repositories:
    repo_dir = None
    try:
        # Extract project details
        project_path = repo_url.replace(GITLAB_URL + "/", "").replace(".git", "")
        logger.info(f"Processing repository: {project_path}")
        project = gl.projects.get(project_path)

        # Clone the repository
        repo_dir = os.path.basename(project_path)
        if os.path.exists(repo_dir):
            logger.info(f"Removing existing directory: {repo_dir}")
            shutil.rmtree(repo_dir)
        logger.info(f"Cloning repository: {repo_url}")
        Repo.clone_from(repo_url, repo_dir)

        # Work inside the repository
        repo = Repo(repo_dir)
        logger.info("Checking out 'development' branch.")
        repo.git.checkout("development")
        logger.info(f"Creating and switching to new branch: {branch_name}.")
        repo.git.checkout("-b", branch_name)

        # Update the target file
        target_file_path = os.path.join(repo_dir, TARGET_FILE)
        if os.path.exists(target_file_path):
            with open(TEMP_FILE, "r") as temp_file:
                new_content = temp_file.read()
            with open(target_file_path, "r") as target_file:
                current_content = target_file.read()

            if new_content != current_content:
                logger.info(f"Updating file: {TARGET_FILE}")
                with open(target_file_path, "w") as target_file:
                    target_file.write(new_content)
            else:
                logger.info(f"No changes detected in {TARGET_FILE}, skipping update.")
                no_changes_repos.append({"repo_url": repo_url, "reason": "No changes made to target file."})
                continue
        else:
            raise FileNotFoundError(f"{TARGET_FILE} not found in {repo_url}")

        # Commit and push changes
        logger.info("Staging changes.")
        repo.git.add(TARGET_FILE)
        logger.info(f"Committing changes with message: '{commit_message}'.")
        try:
            repo.git.commit(m=commit_message)
            logger.info("Pushing changes to remote repository.")
            repo.git.push("--set-upstream", "origin", branch_name)
            successful_pushes += 1
            logger.info(f"Changes pushed successfully for {repo_url}.")
        except Exception as push_error:
            if "nothing to commit" in str(push_error):
                no_changes_repos.append({"repo_url": repo_url, "reason": "No changes to commit."})
                logger.warning(f"No changes to commit for repository: {repo_url}")
            else:
                raise push_error
    except Exception as e:
        error_message = str(e)
        failed_repos.append({"repo_url": repo_url, "error": error_message})
        logger.error(f"Failed to process repository {repo_url}: {error_message}")
    finally:
        # Clean up
        if repo_dir and os.path.exists(repo_dir):
            logger.info(f"Cleaning up directory: {repo_dir}")
            shutil.rmtree(repo_dir)

# Generate summary report
if failed_repos or no_changes_repos:
    logger.info("\n--- Summary Report ---")
    logger.info(f"Total Successful Pushes: {successful_pushes}")
    logger.info(f"Total Failed Repositories: {len(failed_repos)}")
    logger.info(f"Total Repositories with No Changes: {len(no_changes_repos)}")

    if failed_repos:
        logger.info("\n--- Failed Repositories ---")
        for failed_repo in failed_repos:
            logger.info(f"Repository: {failed_repo['repo_url']} | Error: {failed_repo['error']}")
    if no_changes_repos:
        logger.info("\n--- Repositories with No Changes ---")
        for no_change_repo in no_changes_repos:
            logger.info(f"Repository: {no_change_repo['repo_url']} | Reason: {no_change_repo['reason']}")

    # Optionally, write to a file
    with open("summary_report.txt", "w") as report_file:
        report_file.write(f"--- Summary Report ---\n")
        report_file.write(f"Total Successful Pushes: {successful_pushes}\n")
        report_file.write(f"Total Failed Repositories: {len(failed_repos)}\n")
        report_file.write(f"Total Repositories with No Changes: {len(no_changes_repos)}\n\n")

        if failed_repos:
            report_file.write("--- Failed Repositories ---\n")
            for failed_repo in failed_repos:
                report_file.write(f"Repository: {failed_repo['repo_url']} | Error: {failed_repo['error']}\n")
        if no_changes_repos:
            report_file.write("\n--- Repositories with No Changes ---\n")
            for no_change_repo in no_changes_repos:
                report_file.write(f"Repository: {no_change_repo['repo_url']} | Reason: {no_change_repo['reason']}\n")
else:
    logger.info("All repositories processed successfully.")

logger.info("Processing completed for all repositories.")
