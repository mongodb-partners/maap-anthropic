import datetime
import os
import shutil
from typing import List

import boto3
import pymongo
from fastapi import UploadFile
from langchain_aws import BedrockEmbeddings
from langchain_mongodb import MongoDBAtlasVectorSearch

from logger import AsyncRemoteLogger

# Create an instance of the logger
logger = AsyncRemoteLogger(
    service_url="http://logger:8181", app_name="MAAP-AWS-Anthropic-Loader"
)


def UploadFiles(files: List[UploadFile]) -> List[str]:
    strDatetime = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    new_files = []
    for file in files:
        try:
            file_name = file.filename.replace(" ", "-")
            file_name = (
                os.getcwd()
                + "/files/"
                + os.path.basename(file_name).split(".")[0]
                + "_"
                + strDatetime
                + "."
                + os.path.basename(file_name).split(".")[1]
            )

            with open(file_name, "wb") as f:
                shutil.copyfileobj(file.file, f)
                new_files.append(file_name)
        except Exception as e:
            logger.error(e)
            return {"message": "There was an error uploading the file(s)" + str(e)}
        finally:
            file.file.close()
    return new_files


# Setup AWS client
def get_embeddings_client():
    embedding_model_id = "amazon.titan-embed-text-v1"
    bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")
    embeddings_client = BedrockEmbeddings(
        client=bedrock_runtime,
        model_id=embedding_model_id,
    )
    return embeddings_client


def MongoDBAtlasVectorSearch_Obj(inputs) -> MongoDBAtlasVectorSearch:
    embeddings_client = get_embeddings_client()
    # Connect to the MongoDB database
    mongoDBClient = pymongo.MongoClient(host=inputs["MongoDB_URI"],w="majority",readConcernLevel="majority")
    logger.info("Connected to MongoDB...")
    database = mongoDBClient[inputs["MongoDB_database_name"]]
    collection = database[inputs["MongoDB_collection_name"]]
    vector_store = MongoDBAtlasVectorSearch(
        text_key=inputs["MongoDB_text_key"],
        embedding_key=inputs["MongoDB_embedding_key"],
        index_name=inputs["MongoDB_index_name"],
        embedding=embeddings_client,
        collection=collection,
    )
    return vector_store
