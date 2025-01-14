#!/bin/ksh

# Define variables for the commands
PYTHON_SCRIPT="mongodb_atlas_cli.py"
ENV_FILE=".env"

# Function to check Python environment and dependencies
check_env() {
    if ! command -v python3 > /dev/null; then
        echo "Python3 is not installed. Please install Python3 to proceed."
        exit 1
    fi

    # Check if a virtual environment is activated
    if [ -z "$VIRTUAL_ENV" ]; then
        # Check if the 'venv' directory exists
        if [ -d "venv" ]; then
            echo "Virtual environment 'venv' found. Activating it..."
            # Activate the existing virtual environment
            source venv/bin/activate || {
                echo "Failed to activate existing virtual environment."
                exit 1
            }
        else
            echo "No virtual environment found. Creating a new virtual environment..."

            # Create a new virtual environment
            python3 -m venv venv || {
                echo "Failed to create virtual environment."
                exit 1
            }

            # Activate the new virtual environment
            source venv/bin/activate || {
                echo "Failed to activate virtual environment."
                exit 1
            }
            echo "Virtual environment created and activated."
        fi
    fi

    # Check if required libraries are installed inside the virtual environment
    if ! python3 -m pip show click > /dev/null 2>&1; then
        echo "Click library not found. Installing dependencies..."
        python3 -m pip install click==8.1.3 python-dotenv==1.0.0 requests==2.31.0 || {
            echo "Failed to install dependencies. Please install them manually."
            exit 1
        }
    fi
}

# Function to deploy a cluster and update the .env file
deploy_cluster() {
    echo "Deploying MongoDB Atlas Cluster..."
    python3 "$PYTHON_SCRIPT" create -c "$1" -u "$2" -p "$3"
}

# Function to purge (delete) a cluster
purge_cluster() {
    echo "Deleting MongoDB Atlas Cluster..."
    python3 "$PYTHON_SCRIPT" delete -c "$1"
}

# Main script logic
case $1 in
    deploy)
        if [ $# -ne 4 ]; then
            echo "Usage: $0 deploy <cluster_name> <username> <password>"
            exit 1
        fi
        check_env
        deploy_cluster "$2" "$3" "$4"
        ;;
    delete)
        if [ $# -ne 2 ]; then
            echo "Usage: $0 delete <cluster_name>"
            exit 1
        fi
        check_env
        purge_cluster "$2"
        ;;
    *)
        echo "Usage: $0 <deploy|delete> [arguments...]"
        echo "deploy: Deploy a MongoDB Atlas Cluster"
        echo "       $0 deploy <cluster_name> <username> <password>"
        echo "delete: Delete a MongoDB Atlas Cluster"
        echo "       $0 delete <cluster_name>"
        exit 1
        ;;
esac
