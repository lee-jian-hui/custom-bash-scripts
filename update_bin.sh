#!/bin/bash

# Directory to copy scripts to
BIN_DIR="/usr/bin/"

# List all scripts in the current directory
for script in *.sh; do
  # Skip the update_bin.sh script
  if [ "$script" == "update_bin.sh" ]; then
    continue
  fi

  # Check if the file exists and is a regular file
  if [ -f "$script" ]; then
    echo "Copying $script to $BIN_DIR..."
    sudo cp "$script" "$BIN_DIR"
    sudo chmod +x "$BIN_DIR/$script"
  fi
done

echo "All scripts have been copied to $BIN_DIR and made executable, except update_bin.sh."