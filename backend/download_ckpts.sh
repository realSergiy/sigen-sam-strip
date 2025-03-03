#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Set the checkpoints directory path inside the backend folder
CHECKPOINTS_DIR="$SCRIPT_DIR/checkpoints"

# Create checkpoints directory if it doesn't exist
mkdir -p "$CHECKPOINTS_DIR"

# Use either wget or curl to download the checkpoints
if command -v wget &> /dev/null; then
    CMD="wget -P $CHECKPOINTS_DIR"
elif command -v curl &> /dev/null; then
    # For curl, we need to change directory, download, then change back
    CMD="cd $CHECKPOINTS_DIR && curl -L -O"
else
    echo "Please install wget or curl to download the checkpoints."
    exit 1
fi

# Define the URLs for SAM 2.1 checkpoints
SAM2p1_BASE_URL="https://dl.fbaipublicfiles.com/segment_anything_2/092824"
sam2p1_hiera_t_url="${SAM2p1_BASE_URL}/sam2.1_hiera_tiny.pt"
sam2p1_hiera_s_url="${SAM2p1_BASE_URL}/sam2.1_hiera_small.pt"
sam2p1_hiera_b_plus_url="${SAM2p1_BASE_URL}/sam2.1_hiera_base_plus.pt"
sam2p1_hiera_l_url="${SAM2p1_BASE_URL}/sam2.1_hiera_large.pt"

# Function to download a checkpoint if it doesn't exist
download_checkpoint() {
    local url="$1"
    local filename=$(basename "$url")
    local filepath="$CHECKPOINTS_DIR/$filename"

    if [ ! -f "$filepath" ]; then
        echo "Downloading $filename checkpoint to $CHECKPOINTS_DIR directory..."
        $CMD "$url" || { echo "Failed to download checkpoint from $url"; exit 1; }
        echo "Successfully downloaded $filename to $CHECKPOINTS_DIR"
    else
        echo "$filename already exists in $CHECKPOINTS_DIR directory. Skipping download."
    fi
}

# Download SAM 2.1 checkpoints
download_checkpoint "$sam2p1_hiera_t_url"
download_checkpoint "$sam2p1_hiera_s_url"
download_checkpoint "$sam2p1_hiera_b_plus_url"
download_checkpoint "$sam2p1_hiera_l_url"

echo "All checkpoints are available in $CHECKPOINTS_DIR directory."
