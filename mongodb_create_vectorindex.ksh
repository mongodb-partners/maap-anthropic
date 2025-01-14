#!/bin/ksh

# Script to set up environment and run MongoDB index creation Python script

# Exit immediately if a command exits with a non-zero status
set -e

# Define environment variables
export SCRIPT_DIR=$(dirname "$0")  # Directory where the script is located
export VENV_DIR="${SCRIPT_DIR}/venv2"  # Virtual environment directory
export PYTHON_SCRIPT="${SCRIPT_DIR}/mongodb_create_vectorindex.py"  # Python script to run

# Check if Python script exists
if [[ ! -f "$PYTHON_SCRIPT" ]]; then
    echo "Error: Python script '${PYTHON_SCRIPT}' not found."
    exit 1
fi

# Create a virtual environment if it doesn't exist
if [[ ! -d "$VENV_DIR" ]]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "Virtual environment created at ${VENV_DIR}."
fi

# Activate the virtual environment
echo "Activating virtual environment..."
source "${VENV_DIR}/bin/activate"

# Install required Python packages
echo "Installing required Python packages..."
pip install --upgrade pip
pip install pymongo python-dotenv

# Execute the Python script
echo "Running the Python script..."
python "$PYTHON_SCRIPT"

# Deactivate the virtual environment
echo "Deactivating virtual environment..."
deactivate

echo "Script execution completed successfully."
