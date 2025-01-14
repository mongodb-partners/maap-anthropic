from langchain_core.tools import tool
import os
import pymongo
from typing import List

import boto3
from langchain.retrievers.merger_retriever import MergerRetriever
from langchain_aws import BedrockEmbeddings
from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain_mongodb.retrievers import (
    MongoDBAtlasFullTextSearchRetriever,
    MongoDBAtlasHybridSearchRetriever,
)
from dotenv import load_dotenv
from app.logger import AsyncRemoteLogger

# Create an instance of the logger
logger = AsyncRemoteLogger(
    service_url="http://logger:8181", app_name="MAAP-AWS-Anthropic-Main"
)

load_dotenv()
# Setup AWS and Bedrock client
def get_bedrock_client():
    return boto3.client("bedrock-runtime", region_name="us-east-1")


def create_embeddings(client):
    return BedrockEmbeddings(model_id="amazon.titan-embed-text-v1", client=client)


# Initialize everything
bedrock_client = get_bedrock_client()
bedrock_embeddings = create_embeddings(bedrock_client)
MONGODB_URI = os.getenv("MONGODB_URI")

# Connect to the MongoDB database
mongoDBClient = pymongo.MongoClient(host=MONGODB_URI, serverSelectionTimeoutMS=80000)
logger.info("Connected to MongoDB...")

class MongoDBAtlasRetrieverTools:
    """
    A class that provides various tools for interacting with a MongoDB database
    to retrieve place information and perform searches.

    This class includes methods for retrieving place names by country, place
    information by name, and the best time to visit places, as well as
    performing vector, full-text, and hybrid searches. Each method connects
    to a MongoDB Atlas database and uses specific query techniques to fetch
    relevant information based on the provided input.

    Tools provided by this class:
        - `mongodb_place_lookup_by_country`: Retrieves a list of places matching a given country name.
        - `mongodb_place_lookup_by_name`: Retrieves details of a place based on its name.
        - `mongodb_place_lookup_by_best_time_to_visit`: Retrieves the best time to visit a place based on its name or country.
        - `mongodb_vector_search`: Performs a vector-based search to find documents similar to the given query.
        - `mongodb_fulltext_search`: Executes a full-text search to find documents matching the provided criteria.
        - `mongodb_hybrid_search`: Conducts a hybrid search combining both full-text and vector search techniques.

    Author:
        Mohammad Daoud Farooqi
    """

    @tool
    def mongodb_place_lookup_by_country(query_str: str) -> str:
        """
        Retrieve places by country name from the MongoDB database.

        This function connects to the MongoDB Atlas database and searches for place names
        that match the provided country name query. The search is case-insensitive and
        utilizes a regex match. The function returns a list of matching place names.

        Args:
            query_str (str): The country name to search for. It may include partial matches.

        Returns:
            str: A string representation of the list of place names that match the country query.
        """

        database = mongoDBClient["travel_agency"]
        collection = database["trip_recommendation"]
        res = ""
        res = collection.aggregate(
            [
                {"$match": {"Country": {"$regex": query_str, "$options": "i"}}},
                {"$project": {"Place Name": 1,"_id": 0}},
            ]
        )
        places = []
        for place in res:
            places.append(place["Place Name"])
        return str(places)

    @tool
    def mongodb_place_lookup_by_name(query_str: str) -> str:
        """
        Retrieve place information by place name from the MongoDB database.

        This function connects to the MongoDB Atlas database and searches for a place
        using the provided name query. The search checks both the place name and country,
        using case-insensitive regex matching. The function returns the first matching
        document without the ID field.

        Args:
            query_str (str): The place name to search for. It may include partial matches.

        Returns:
            str: A string representation of the first matching document's details without the ID field.
        """

        database = mongoDBClient["travel_agency"]
        collection = database["trip_recommendation"]
        res = ""
        filter = {
            "$or": [
                {"Place Name": {"$regex": query_str, "$options": "i"}},
                {"Country": {"$regex": query_str, "$options": "i"}},
            ]
        }
        project = {"_id": 0,"details_embedding":0}

        res = collection.find_one(filter=filter, projection=project)
        return str(res)

    @tool
    def mongodb_place_lookup_by_best_time_to_visit(query_str: str) -> str:
        """
        Retrieve place information by the best time to visit from the MongoDB database.

        This function connects to the MongoDB Atlas database and searches for the best time
        to visit places using the provided query string. The search is performed on both
        place names and countries using case-insensitive regex matching. The function returns
        the best time to visit for the first matching document.

        Args:
            query_str (str): The place name or country to search for. It may include partial matches.

        Returns:
            str: A string representation of the best time to visit for the first matching document.
        """

        database = mongoDBClient["travel_agency"]
        collection = database["trip_recommendation"]

        res = ""
        filter = {
            "$or": [
                {"Place Name": {"$regex": query_str, "$options": "i"}},
                {"Country": {"$regex": query_str, "$options": "i"}},
            ]
        }
        project = {"Best Time To Visit": 1, "_id": 0}

        res = collection.find_one(filter=filter, projection=project)
        return str(res)

    @tool
    def mongodb_vector_search(query: str, userId: str, dataSource: List) -> str:
        """
        Performs a vector search using MongoDB Atlas, retrieving documents based on the semantic similarity of
        their embeddings to the given query.

        This function leverages MongoDB Atlas' vector search capabilities to find documents whose embeddings
        are similar to the query. It supports searching across multiple data sources, including user-specific
        data, and retrieves documents based on the cosine similarity of their vector representations.

        Args:
            query (str): The search query string to perform the vector search.
            userId (str): The ID of the user to filter results by user-specific data.
            dataSource (List): A list of data sources (collections) from which to search, such as
                            "Trip Recommendations" or "User Uploaded Data."

        Returns:
            str: A list of document contents retrieved by the vector search, with each document's content
                represented as a string.

        Example:
            >>> mongodb_vector_search("tropical vacation", "user789", ["Trip Recommendations"])
            ['Document 1 content', 'Document 2 content']
        """

        database = mongoDBClient["travel_agency"]
        collection = database["trip_recommendation"]

        vector_store = MongoDBAtlasVectorSearch(
            text_key="About Place",
            embedding_key="details_embedding",
            index_name="vector_index",
            embedding=bedrock_embeddings,
            collection=collection,
        )

        database_doc = mongoDBClient["maap_data_loader"]
        collection_doc = database_doc["document"]
        vector_store_documents = MongoDBAtlasVectorSearch(
            text_key="document_text",
            embedding_key="document_embedding",
            index_name="document_vector_index",
            embedding=bedrock_embeddings,
            collection=collection_doc,
        )

        retriever_travels = vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={"score_threshold": 0.9, "k": 10},
        )

        retriever_user_docs = vector_store_documents.as_retriever(
            search_type="similarity",
            search_kwargs={"score_threshold": 0.9, "k": 10},
        )

        if len(userId) > 0:
            retriever_user_docs = vector_store_documents.as_retriever(
                search_type="similarity",
                search_kwargs={
                    "score_threshold": 0.9,
                    "k": 10,
                    "pre_filter": {"userId": userId},
                },
            )

        retrievers = None
        if len(dataSource) > 0:  # ["Trip Recommendations", "User Uploaded Data"]
            if len(dataSource) == 1:
                if dataSource[0] == "Trip Recommendations":
                    retrievers = retriever_travels
                else:
                    retrievers = retriever_user_docs
            elif len(dataSource) > 1:
                retrievers = MergerRetriever(
                    retrievers=[retriever_user_docs, retriever_travels]
                )
        else:
            return ""

        documents = retrievers.invoke(query)
        return [doc.page_content for doc in documents]

    @tool
    def mongodb_fulltext_search(query: str, userId: str, dataSource: List) -> str:
        """
        Performs a full-text search using MongoDB Atlas and returns the content of the retrieved documents.

        This function uses the MongoDB Atlas Full Text Search functionality to retrieve relevant documents from
        specified collections based on a search query. It can search across multiple data sources such as trip
        recommendations and user-uploaded data, filtering results as needed by the user's ID.

        The search is performed on the specified data sources using the provided search query and returns the
        contents of the matching documents.

        Args:
            query (str): The full-text search query string containing the search criteria.
            userId (str): The ID of the user for filtering documents based on the user's specific data.
            dataSource (List): A list of data sources (collections) from which to search, such as
                            "Trip Recommendations" or "User Uploaded Data".

        Returns:
            str: A list of document contents that match the search query, with each document's content
                represented as a string.

        Example:
            >>> mongodb_fulltext_search("beach vacation", "user123", ["Trip Recommendations"])
            ['Document 1 content', 'Document 2 content']
        """

        database = mongoDBClient["travel_agency"]
        collection = database["trip_recommendation"]

        database_doc = mongoDBClient["maap_data_loader"]
        collection_doc = database_doc["document"]

        retriever_travels = MongoDBAtlasFullTextSearchRetriever(
            collection=collection,
            search_index_name="travel_text_search_index",
            search_field="About Place",
            top_k=10,
        )

        retriever_user_docs = MongoDBAtlasFullTextSearchRetriever(
            collection=collection_doc,
            search_index_name="document_text_search_index",
            search_field="document_text",
            top_k=10,
        )

        # inputs = json.loads(query)
        if len(userId) > 0:
            retriever_user_docs = MongoDBAtlasFullTextSearchRetriever(
                collection=collection_doc,
                search_index_name="document_text_search_index",
                search_field="document_text",
                top_k=10,
                filter={"userId": userId},
            )

        retrievers = None
        if len(dataSource) > 0:  # ["Trip Recommendations", "User Uploaded Data"]
            if len(dataSource) == 1:
                if dataSource[0] == "Trip Recommendations":
                    retrievers = retriever_travels
                else:
                    retrievers = retriever_user_docs
            elif len(dataSource) > 1:
                retrievers = MergerRetriever(
                    retrievers=[retriever_user_docs, retriever_travels]
                )
        else:
            return ""

        documents = retrievers.invoke(query)
        return [doc.page_content for doc in documents]

    @tool
    def mongodb_hybrid_search(query: str, userId: str, dataSource: List) -> str:
        """
        Performs a hybrid search using MongoDB Atlas, combining both full-text and vector-based searches to
        retrieve relevant documents from multiple data sources.

        This function uses MongoDB Atlas' Full Text Search and Vector Search capabilities to search for documents
        that match the query string across different collections. The search can be tailored to individual users
        based on the userId, and it supports retrieving data from multiple collections such as "Trip Recommendations"
        and "User Uploaded Data."

        Args:
            query (str): The search query string to perform the hybrid search.
            userId (str): The ID of the user to filter results by user-specific data.
            dataSource (List): A list of data sources (collections) from which to search, such as
                            "Trip Recommendations" or "User Uploaded Data."

        Returns:
            str: A list of document contents retrieved by the hybrid search, with each document's content
                represented as a string.

        Example:
            >>> mongodb_hybrid_search("luxury beach resort", "user456", ["Trip Recommendations", "User Uploaded Data"])
            ['Document 1 content', 'Document 2 content']
        """

        database = mongoDBClient["travel_agency"]
        collection = database["trip_recommendation"]

        database_doc = mongoDBClient["maap_data_loader"]
        collection_doc = database_doc["document"]

        retriever_travels = MongoDBAtlasFullTextSearchRetriever(
            collection=collection,
            search_index_name="travel_text_search_index",
            search_field="About Place",
            top_k=10,
        )

        retriever_user_docs = MongoDBAtlasFullTextSearchRetriever(
            collection=collection_doc,
            search_index_name="document_text_search_index",
            search_field="document_text",
            top_k=10,
        )

        vector_store_travels = MongoDBAtlasVectorSearch(
            text_key="About Place",
            embedding_key="details_embedding",
            index_name="vector_index",
            embedding=bedrock_embeddings,
            collection=collection,
        )

        database_doc = mongoDBClient["maap_data_loader"]
        collection_doc = database_doc["document"]
        vector_store_documents = MongoDBAtlasVectorSearch(
            text_key="document_text",
            embedding_key="document_embedding",
            index_name="document_vector_index",
            embedding=bedrock_embeddings,
            collection=collection_doc,
        )

        retriever_travels = MongoDBAtlasHybridSearchRetriever(
            vectorstore=vector_store_travels,
            search_index_name="travel_text_search_index",
            top_k=10,
        )

        retriever_user_docs = MongoDBAtlasHybridSearchRetriever(
            vectorstore=vector_store_documents,
            search_index_name="document_text_search_index",
            top_k=10,
        )

        if len(userId) > 0:
            retriever_user_docs = MongoDBAtlasHybridSearchRetriever(
                vectorstore=vector_store_documents,
                search_index_name="document_text_search_index",
                pre_filter={"userId": userId},
                top_k=10,
            )

        retrievers = None
        if len(dataSource) > 0:  # ["Trip Recommendations", "User Uploaded Data"]
            if len(dataSource) == 1:
                if dataSource[0] == "Trip Recommendations":
                    retrievers = retriever_travels
                else:
                    retrievers = retriever_user_docs
            elif len(dataSource) > 1:
                retrievers = MergerRetriever(
                    retrievers=[retriever_user_docs, retriever_travels]
                )
        else:
            return ""

        documents = retrievers.invoke(query)
        return [doc.page_content for doc in documents]
