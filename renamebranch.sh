#!/bin/bash

# Function to display help information
show_help() {
  echo "Usage: $0 -o OLD_BRANCH_NAME -n NEW_BRANCH_NAME [-r REMOTE_NAME]"
  echo ""
  echo "Options:"
  echo "  -o OLD_BRANCH_NAME   Specify the old branch name."
  echo "  -n NEW_BRANCH_NAME   Specify the new branch name."
  echo "  -r REMOTE_NAME       Specify the remote name (default: origin)."
  echo "  -h                   Show this help message."
}

# Default remote name
REMOTE_NAME="origin"

# Parse command-line arguments
while getopts "ho:n:r:" opt; do
  case ${opt} in
    h )
      show_help
      exit 0
      ;;
    o )
      OLD_BRANCH_NAME=$OPTARG
      ;;
    n )
      NEW_BRANCH_NAME=$OPTARG
      ;;
    r )
      REMOTE_NAME=$OPTARG
      ;;
    \? )
      show_help
      exit 1
      ;;
  esac
done

# Check if required arguments are provided
if [ -z "$OLD_BRANCH_NAME" ] || [ -z "$NEW_BRANCH_NAME" ]; then
  echo "Error: Both old branch name and new branch name must be specified."
  show_help
  exit 1
fi

# Function to rename the local branch
rename_local_branch() {
  echo "Renaming local branch $OLD_BRANCH_NAME to $NEW_BRANCH_NAME..."
  git branch -m "$OLD_BRANCH_NAME" "$NEW_BRANCH_NAME"
  if [ $? -ne 0 ]; then
    echo "Error: Failed to rename the local branch."
    exit 1
  fi
}

# Function to push the new branch to the remote and set upstream
set_upstream() {
  echo "Pushing new branch $NEW_BRANCH_NAME and setting upstream..."
  git push --set-upstream "$REMOTE_NAME" "$NEW_BRANCH_NAME"
  if [ $? -ne 0 ]; then
    echo "Error: Failed to push the new branch and set upstream."
    exit 1
  fi
}

# Function to delete the old branch from the remote
delete_remote_branch() {
  echo "Deleting remote branch $OLD_BRANCH_NAME..."
  git push "$REMOTE_NAME" --delete "$OLD_BRANCH_NAME"
  if [ $? -ne 0 ]; then
    echo "Error: Failed to delete the remote branch."
    exit 1
  fi
}

# Execute the verification steps
rename_local_branch
set_upstream

# After both operations succeed, delete the old branch
delete_remote_branch

echo "Branch rename and cleanup completed successfully."
