import gitlab
import os
import shutil
import logging
from git import Repo
from dotenv import load_dotenv

# Configure logging
def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("gitlab_batch_update.log", mode="a")
        ]
    )
    return logging.getLogger(__name__)

logger = configure_logging()

# Load environment variables
def load_configuration():
    load_dotenv()
    config = {
        "GITLAB_URL": os.getenv("GITLAB_URL"),
        "PRIVATE_TOKEN": os.getenv("PRIVATE_TOKEN"),
        "REPOS_FILE": os.getenv("REPOS_FILE", "repositories.txt"),
        "TEMP_FILE": os.getenv("TEMP_FILE", "temp.txt"),
        "TARGET_FILE": os.getenv("TARGET_FILE", "path/to/target/file")
    }
    for key, value in config.items():
        if not value:
            logger.error(f"{key} is not set.")
            exit(1)
    logger.info(f"GITLAB_URL: {config['GITLAB_URL']}")
    return config

config = load_configuration()

# Get user input
def get_user_inputs(target_file):
    default_branch_name = f"feature/batch_update_{os.path.basename(target_file).replace('.', '_')}"
    default_commit_msg = f"feat: batch update on {os.path.basename(target_file)}"

    branch_name = input(
        f"Enter the name of the new branch to create (off development branch) [default: '{default_branch_name}'] : "
    ).strip() or default_branch_name

    commit_message = input(
        f"Enter the commit message for the changes [default: '{default_commit_msg}']: "
    ).strip() or default_commit_msg

    return branch_name, commit_message

branch_name, commit_message = get_user_inputs(config["TARGET_FILE"])

# Validate files
def validate_files(repos_file, temp_file):
    if not os.path.isfile(repos_file):
        logger.error(f"{repos_file} not found!")
        exit(1)

    if not os.path.isfile(temp_file):
        logger.error(f"{temp_file} not found!")
        exit(1)

validate_files(config["REPOS_FILE"], config["TEMP_FILE"])

# Read repositories
def load_repositories(repos_file):
    with open(repos_file, "r") as f:
        repositories = [line.strip() for line in f if line.strip()]
    logger.info(f"Loaded {len(repositories)} repositories from {repos_file}.")
    return repositories

repositories = load_repositories(config["REPOS_FILE"])

# Initialize GitLab client
def initialize_gitlab_client(gitlab_url, private_token):
    try:
        gl = gitlab.Gitlab(gitlab_url, private_token=private_token, ssl_verify=False)
        logger.info("Connected to GitLab instance.")
        return gl
    except Exception as e:
        logger.error(f"Failed to connect to GitLab: {e}")
        exit(1)

gl = initialize_gitlab_client(config["GITLAB_URL"], config["PRIVATE_TOKEN"])

# Process repository
def process_repository(gl, repo_url, branch_name, commit_message, target_file, temp_file):
    repo_dir = None
    try:
        project_path = repo_url.replace(config["GITLAB_URL"] + "/", "").replace(".git", "")
        logger.info(f"Processing repository: {project_path}")
        project = gl.projects.get(project_path)

        repo_dir = os.path.basename(project_path)
        if os.path.exists(repo_dir):
            logger.info(f"Removing existing directory: {repo_dir}")
            shutil.rmtree(repo_dir)

        logger.info(f"Cloning repository: {repo_url}")
        Repo.clone_from(repo_url, repo_dir)

        repo = Repo(repo_dir)
        logger.info("Checking out 'development' branch.")
        repo.git.checkout("development")

        logger.info(f"Creating and switching to new branch: {branch_name}.")
        repo.git.checkout("-b", branch_name)

        target_file_path = os.path.join(repo_dir, target_file)
        if os.path.exists(target_file_path):
            with open(temp_file, "r") as temp:
                new_content = temp.read()
            with open(target_file_path, "r") as target:
                current_content = target.read()

            if new_content != current_content:
                logger.info(f"Updating file: {target_file}")
                with open(target_file_path, "w") as target:
                    target.write(new_content)
                logger.info("Staging changes.")
                repo.git.add(target_file)
                logger.info(f"Committing changes with message: '{commit_message}'.")
                commit = repo.git.commit(m=commit_message)
                return "success", f"{repo_url}/-/commit/{commit}"
            else:
                logger.info(f"No changes detected in {target_file}, pushing branch anyway.")

        logger.info(f"Pushing branch '{branch_name}' to remote repository.")
        repo.git.push("--set-upstream", "origin", branch_name)
        return "no_changes", repo_url

    except Exception as e:
        logger.error(f"Failed to process repository {repo_url}: {e}")
        return "failure", repo_url

    finally:
        if repo_dir and os.path.exists(repo_dir):
            logger.info(f"Cleaning up directory: {repo_dir}")
            shutil.rmtree(repo_dir)

# Generate summary report
def generate_summary():
    logger.info("\n--- Summary Report ---")
    logger.info(f"Total Successful Pushes: {len(successful_pushes)}")
    logger.info(f"Total Repositories with No Changes but Pushed: {len(no_changes_pushed)}")
    logger.info(f"Total Failed Repositories: {len(failed_repos)}")

    if successful_pushes:
        logger.info("\n--- Successful Repositories ---")
        for repo in successful_pushes:
            logger.info(f"Repository: {repo}")

    if no_changes_pushed:
        logger.info("\n--- Repositories with No Changes but Pushed ---")
        for repo in no_changes_pushed:
            logger.info(f"Repository: {repo}")

    if failed_repos:
        logger.info("\n--- Failed Repositories ---")
        for repo in failed_repos:
            logger.info(f"Repository: {repo}")

    if commit_urls:
        logger.info("\n--- Commit URLs ---")
        for url in commit_urls:
            logger.info(url)


if __name__ == "__main__":
    # Main loop
    failed_repos = []
    no_changes_pushed = []
    successful_pushes = []
    commit_urls = []

    for repo_url in repositories:
        result, data = process_repository(
            gl, repo_url, branch_name, commit_message, config["TARGET_FILE"], config["TEMP_FILE"]
        )
        if result == "success":
            successful_pushes.append(data)
        elif result == "no_changes":
            no_changes_pushed.append(data)
        elif result == "failure":
            failed_repos.append(data)


    generate_summary()
