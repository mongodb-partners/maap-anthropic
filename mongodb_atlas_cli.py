import time
import requests
import json
from requests.auth import HTTPDigestAuth
import click
from dotenv import load_dotenv, set_key
import os
import urllib.parse
# Constants for MongoDB Atlas API
BASE_URL = "https://cloud.mongodb.com/api/atlas/v2/groups"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/vnd.atlas.2024-05-30+json",
}

# Load environment variables from .env file
load_dotenv()

API_PUBLIC_KEY = os.getenv("API_PUBLIC_KEY")
API_PRIVATE_KEY = os.getenv("API_PRIVATE_KEY")
GROUP_ID = os.getenv("GROUP_ID")


@click.group()
def cli():
    """MongoDB Atlas Cluster Management CLI."""
    pass


@click.command()
@click.argument("cluster_name")
def create_cluster(cluster_name):
    """
    Create a MongoDB Atlas cluster.
    """
    url = f"{BASE_URL}/{GROUP_ID}/clusters"

    # Cluster configuration body
    body = {
        "clusterType": "REPLICASET",
        "name": cluster_name,
        "replicationSpecs": [
            {
                "regionConfigs": [
                    {
                        "analyticsAutoScaling": {
                            "autoIndexing": {"enabled": False},
                            "compute": {"enabled": False},
                            "diskGB": {"enabled": True},
                        },
                        "analyticsSpecs": {
                            "diskSizeGB": 10,
                            "instanceSize": "M10",
                            "nodeCount": 0,
                        },
                        "autoScaling": {
                            "autoIndexing": {"enabled": False},
                            "compute": {"enabled": False},
                            "diskGB": {"enabled": True},
                        },
                        "electableSpecs": {
                            "diskSizeGB": 10,
                            "instanceSize": "M10",
                            "nodeCount": 3,
                        },
                        "priority": 7,
                        "providerName": "AWS",
                        "readOnlySpecs": {
                            "diskSizeGB": 10,
                            "instanceSize": "M10",
                            "nodeCount": 0,
                        },
                        "regionName": "US_EAST_1",
                    }
                ],
                "zoneName": "Zone 1",
            }
        ],
    }

    response = requests.post(
        url,
        headers=HEADERS,
        auth=HTTPDigestAuth(API_PUBLIC_KEY, API_PRIVATE_KEY),
        data=json.dumps(body),
    )

    if response.status_code == 201:
        click.echo(f"Cluster {cluster_name} creation started...")
    else:
        click.echo(
            f"Failed to create cluster {cluster_name}. Error: {response.status_code}, {response.text}"
        )

    return response.json()


@click.command()
@click.argument("cluster_name")
def check_cluster_status(cluster_name):
    """
    Check the status of a MongoDB Atlas cluster.
    """
    url = f"{BASE_URL}/{GROUP_ID}/clusters/{cluster_name}/status"

    response = requests.get(
        url, headers=HEADERS, auth=HTTPDigestAuth(API_PUBLIC_KEY, API_PRIVATE_KEY)
    )

    if response.status_code == 200:
        click.echo(f"Cluster status: {response.json()['changeStatus']}")
    else:
        click.echo(
            f"Failed to retrieve status for cluster {cluster_name}. Error: {response.status_code}, {response.text}"
        )

    return response.status_code


@click.command()
@click.argument("username")
@click.argument("password")
def create_user(username, password):
    """
    Create a MongoDB Atlas database user.
    """
    url = f"{BASE_URL}/{GROUP_ID}/databaseUsers"

    # User configuration body
    body = {
        "databaseName": "admin",
        "groupId": GROUP_ID,
        "password": password,
        "username": username,
        "roles": [{"databaseName": "admin", "roleName": "atlasAdmin"}],
    }

    response = requests.post(
        url,
        headers=HEADERS,
        auth=HTTPDigestAuth(API_PUBLIC_KEY, API_PRIVATE_KEY),
        data=json.dumps(body),
    )

    if response.status_code == 201:
        click.echo(f"User {username} created successfully!")
    elif response.status_code == 409:
        click.echo(f"User {username} already exists.")
    else:
        click.echo(
            f"Failed to create user {username}. Error: {response.status_code}, {response.text}"
        )


@click.command()
@click.argument("cluster_name")
def get_connection_string(cluster_name):
    """
    Retrieve MongoDB Atlas cluster connection string.
    """
    url = f"{BASE_URL}/{GROUP_ID}/clusters/{cluster_name}"

    response = requests.get(
        url, headers=HEADERS, auth=HTTPDigestAuth(API_PUBLIC_KEY, API_PRIVATE_KEY)
    )

    if response.status_code == 200:
        cluster_details = response.json()
        if (
            "connectionStrings" in cluster_details
            and "standardSrv" in cluster_details["connectionStrings"]
        ):
            click.echo(f"Cluster {cluster_name} details retrieved successfully!")
            return f"{cluster_details['connectionStrings']['standardSrv']}"
        else:
            return None
    else:
        click.echo(
            f"Failed to retrieve cluster {cluster_name}. Error: {response.status_code}, {response.text}"
        )
        return


@click.command()
@click.argument("cluster_name")
def delete_cluster(cluster_name):
    """
    Delete a MongoDB Atlas cluster.
    """
    url = f"{BASE_URL}/{GROUP_ID}/clusters/{cluster_name}"

    response = requests.delete(
        url, headers=HEADERS, auth=HTTPDigestAuth(API_PUBLIC_KEY, API_PRIVATE_KEY)
    )

    if response.status_code == 202:
        click.echo(f"Cluster {cluster_name} deletion initiated successfully!")
    else:
        click.echo(
            f"Failed to delete cluster {cluster_name}. Error: {response.status_code}, {response.text}"
        )

    return response.status_code


cli.add_command(create_cluster)
cli.add_command(check_cluster_status)
cli.add_command(create_user)
cli.add_command(get_connection_string)


@click.command("create")
@click.option(
    "-c", "--cluster_name", type=str, help="name of the cluster to be deployed"
)
@click.option("-u", "--username", type=str, help="username of the database user")
@click.option("-p", "--password", type=str, help="password of the database user")
@click.pass_context
def deploy_cluster(ctx, cluster_name, username, password):
    try:
        # Load .env file if it exists
        env_file = ".env"
        if os.path.exists(env_file):
            load_dotenv(env_file)
        else:
            open(env_file, "w").close()  # Create an empty .env file if it doesn't exist

        # Create a MongoDB Atlas cluster
        ctx.invoke(create_cluster, cluster_name=cluster_name)

        # Check the status of the cluster
        max_retries = 5
        for attempt in range(max_retries):
            status = ctx.invoke(check_cluster_status, cluster_name=cluster_name)
            if status == 200:
                break
            time.sleep(10)
            click.echo(f"Retrying... ({attempt + 1}/{max_retries})")

        if status != 200:
            raise Exception(
                f"Failed to create cluster {cluster_name} after {max_retries} attempts."
            )

        # Create a MongoDB Atlas database user
        ctx.invoke(create_user, username=username, password=password)

        # Retrieve the connection string for the cluster
        conn_status = None
        while conn_status is None:
            conn_status = ctx.invoke(get_connection_string, cluster_name=cluster_name)
            if conn_status is None:
                click.echo(
                    "Connection string not available yet. Retrying in 60 seconds..."
                )
                time.sleep(60)

        if not conn_status:
            raise Exception("Failed to retrieve connection string.")
        else:
            click.echo(f"Connection string: {conn_status}")

            # Add or update the connection string in .env
            env_var_key = "MONGODB_URI"

            encoded_password = urllib.parse.quote_plus(password)
            part1,part2=conn_status.split("//")

            connection_string = f"{part1}//{username}:{encoded_password}@{part2}/?retryWrites=true&w=majority&appName={cluster_name}"

            set_key(env_file, env_var_key, connection_string)
            click.echo(
                f"Connection string added/updated in {env_file} as {env_var_key}."
            )

    except Exception as e:
        click.echo(f"An error occurred: {e}")


@click.command("delete")
@click.option("-c", "--cluster_name", type=str, help="name of the cluster to be purged")
@click.pass_context
def purge(ctx, cluster_name):
    ctx.invoke(delete_cluster, cluster_name=cluster_name)


@click.group()
def cluster_commands():
    pass


# Add the deploy and purge commands to the cluster_commands group
cluster_commands.add_command(deploy_cluster)
cluster_commands.add_command(purge)

if __name__ == "__main__":
    cluster_commands()
