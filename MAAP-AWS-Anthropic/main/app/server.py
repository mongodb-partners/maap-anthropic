import json
import os
import pprint
import re
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Literal, Union

import boto3
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from langchain.agents import AgentExecutor
from langchain.agents.format_scratchpad.openai_tools import (
    format_to_openai_tool_messages,
)
from langchain.agents.output_parsers.openai_tools import OpenAIToolsAgentOutputParser
from langchain_aws import ChatBedrock
from langchain_core import __version__
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import ConfigurableFieldSpec, RunnableLambda
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_mongodb.chat_message_histories import MongoDBChatMessageHistory
from langserve import add_routes
from pydantic import BaseModel
import asyncio
from app.models import ModelKwargs
from app.mongodb_atlas_retriever_tools import MongoDBAtlasRetrieverTools
import uvicorn
from app.logger import AsyncRemoteLogger

# Create an instance of the logger
logger = AsyncRemoteLogger(
    service_url="http://logger:8181", app_name="MAAP-AWS-Anthropic-Main"
)
# Load environment variables from a .env file
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="MAAP - MongoDB AI Applications Program",
    version="1.0",
    description="MongoDB AI Applications Program",
)


# Redirect root URL to API documentation
@app.get("/")
async def redirect_root_to_docs():
    await logger.aprint("Redirecting to API documentation.")
    return RedirectResponse("/docs")


# Define the chat prompt template
prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a highly capable, friendly, and knowledgeable assistant with access to various tools to extract information from MongoDB databases about any data."
            "Engage with the user in a conversational manner and aim to provide accurate and helpful responses to their questions. Respond well to greetings."
            "Utilize the all the available tools effectively to gather information, and refer to the chat history as needed. If the chat history shows that you did not have information earlier that does not mean you do not have it now. Uses the tools again and find the information."
            "Your final response should be in detail and written in clear, human-readable text, free from any extra special characters. "
            "At the end of your response, briefly list the tools you used to arrive at your answer.",
        ),
        # Please note the ordering of the fields in the prompt!
        # The correct ordering is:
        # 1. history - the past messages between the user and the agent
        # 2. user - the user's current input
        # 3. agent_scratchpad - the agent's working space for thinking and
        #    invoking tools to respond to the user's input.
        # If you change the ordering, the agent will not work correctly since
        # the messages will be shown to the underlying LLM in the wrong order.
        MessagesPlaceholder(variable_name="chat_history"),
        ("user", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ]
)


# Function to trim the prompt to a reasonable length
def prompt_trimmer(messages: ChatPromptTemplate):
    """Trims the prompt to a reasonable length."""
    # Keep the system message (if present) and the last 10 messages
    trimmed_messages = []
    system_message = None

    for message in messages.messages:
        # Check if the message is a system message
        if hasattr(message, "role") and message.role == "system":
            system_message = message

    # Filter non-system messages
    non_system_messages = [
        msg
        for msg in messages.messages
        if not hasattr(msg, "role") or msg.role != "system"
    ]
    last_10_messages = non_system_messages[-10:]

    # Combine the system message and last 10 non-system messages
    if system_message:
        trimmed_messages.append(system_message)
    trimmed_messages.extend(last_10_messages)

    # Update the messages object
    messages.messages = trimmed_messages
    logger.print("Prompt trimming completed.")
    return messages


# MongoDB URI from environment variables
MONGODB_URI = os.getenv("MONGODB_URI")
logger.print("MongoDB URI loaded.")
####
# Define the minimum required version as (0, 1, 0)
# Earlier versions did not allow specifying custom config fields in
# RunnableWithMessageHistory.
# Define the minimum required version of langchain-core
MIN_VERSION_LANGCHAIN_CORE = (0, 1, 0)

# Get the current version of langchain-core
LANGCHAIN_CORE_VERSION = tuple(map(int, __version__.split(".")))

# Check if the current version meets the minimum required version
if LANGCHAIN_CORE_VERSION < MIN_VERSION_LANGCHAIN_CORE:
    error_message = (
        f"Minimum required version of langchain-core is {MIN_VERSION_LANGCHAIN_CORE}, "
        f"but found {LANGCHAIN_CORE_VERSION}"
    )
    logger.error(error_message)
    raise RuntimeError(error_message)


# Function to check if a value is a valid identifier
def _is_valid_identifier(value: str) -> bool:
    """Check if the value is a valid identifier."""
    # Use a regular expression to match emails
    # valid_characters = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\\\.[a-zA-Z]{2,}$')
    # return bool(valid_characters.match(value))
    return True


# Function to create a session factory for retrieving chat histories
def create_session_factory(
    base_dir: Union[str, Path],
) -> Callable[[str], BaseChatMessageHistory]:
    """Create a factory that can retrieve chat histories.

    The chat histories are keyed by user ID and conversation ID.

    Args:
        base_dir: Base directory to use for storing the chat histories.

    Returns:
        A factory that can retrieve chat histories keyed by user ID and conversation ID.
    """

    def get_chat_history(
        user_id: str, conversation_id: str
    ) -> MongoDBChatMessageHistory:
        """Get a chat history from a user id and conversation id."""
        if not _is_valid_identifier(user_id):
            raise ValueError(
                f"User ID {user_id} is not in a valid format. "
                "User ID must only contain alphanumeric characters, "
                "hyphens, and underscores."
                "Please include a valid cookie in the request headers called 'user-id'."
            )
        if not _is_valid_identifier(conversation_id):
            raise ValueError(
                f"Conversation ID {conversation_id} is not in a valid format. "
                "Conversation ID must only contain alphanumeric characters, "
                "hyphens, and underscores. Please provide a valid conversation id "
                "via config. For example, "
                "chain.invoke(.., {'configurable': {'conversation_id': '123'}})"
            )

        DBNAME = "maap_data_loader"
        COLLECTION_NAME = "chat_history"
        SESSION_ID_KEY = "SessionId"
        SESSION_ID = str(user_id)
        HISTORY_KEY = "History"
        logger.print(
            f"Creating chat history for user_id: {user_id}, conversation_id: {conversation_id}."
        )
        return MongoDBChatMessageHistory(
            connection_string=MONGODB_URI,
            session_id=SESSION_ID,
            database_name=DBNAME,
            collection_name=COLLECTION_NAME,
            session_id_key=SESSION_ID_KEY,
            history_key=HISTORY_KEY,
            history_size=20,
        )

    return get_chat_history


# Function to update the config per request
def _per_request_config_modifier(
    config: Dict[str, Any], request: Request
) -> Dict[str, Any]:
    """Update the config"""
    logger.print("Modifying per-request configuration.")
    config = config.copy()
    configurable = config.get("configurable", {})
    # Look for a cookie named "user_id"
    user_id = request.cookies.get("user_id", None)

    if user_id is None:
        raise HTTPException(
            status_code=400,
            detail="No user id found. Please set a cookie named 'user_id'.",
        )

    configurable["user_id"] = user_id
    config["configurable"] = configurable
    return config


# Define tool mappings
TOOL_MAPPING = {
    "Lookup by Name": MongoDBAtlasRetrieverTools.mongodb_place_lookup_by_name,
    "Lookup by Country": MongoDBAtlasRetrieverTools.mongodb_place_lookup_by_country,
    "Lookup by Best Time to Visit": MongoDBAtlasRetrieverTools.mongodb_place_lookup_by_best_time_to_visit,
    "MongoDB Vector Search": MongoDBAtlasRetrieverTools.mongodb_vector_search,
    "MongoDB FullText Search": MongoDBAtlasRetrieverTools.mongodb_fulltext_search,
    "MongoDB Hybrid Search": MongoDBAtlasRetrieverTools.mongodb_hybrid_search,
}

# Define known tools
KnownTool = Literal[
    "Lookup by Name",
    "Lookup by Country",
    "Lookup by Best Time to Visit",
    "MongoDB Vector Search",
    "MongoDB FullText Search",
    "MongoDB Hybrid Search",
]


# Define input schema
class Input(BaseModel):
    input: str
    chat_history: List
    tools: List[KnownTool]
    llm_model: str


# Function to format response
def format_response(response_str):
    try:
        message = json.loads(response_str)[0]
        if "text" in message:
            return str(message["text"]).replace("None", "")
    except Exception:
        return response_str


# Function to format text
def format_text(response_str):
    message = pprint.pformat(response_str)
    return message


# Function to format start text
def format_start_text(response_str):
    response_str = response_str["chat_history"]
    if len(response_str) > 0:
        return "Starting agent with provided inputs and available conversation history.\n\nThinking....\n"
    return "Starting agent with provided inputs.\n\nThinking....\n"


# Custom stream function to stream content
async def custom_stream(user_inputs: Input) -> AsyncIterator[str]:
    """A custom runnable that can stream content.

    Args:
        input: The input to the agent. See the Input model for more details.

    Yields:
        strings that are streamed to the client.
    """
    await logger.aprint(
        f"Initializing custom stream with input: {str(user_inputs)}"
    )
    # Create an LLM instance dynamically based on the provided model ID
    dynamic_llm = ChatBedrock(
        client=boto3.client(
            service_name="bedrock-runtime",
            region_name="us-east-1",
        ),
        model_id=user_inputs["llm_model"],  # Use the dynamically provided model ID
    )
    dynamic_llm.model_kwargs = ModelKwargs().__dict__
    await logger.aprint(
        f"LLM instance created with model ID: {user_inputs['llm_model']}"
    )

    # Function to create an agent with custom tools
    def _create_agent_with_tools(requested_tools: List[KnownTool]) -> AgentExecutor:
        """Create an agent with custom tools."""
        tools = []
        logger.print(f"Creating agent with tools: {requested_tools}")
        for requested_tool in requested_tools:
            if requested_tool not in TOOL_MAPPING:
                raise ValueError(f"Unknown tool: {requested_tool}")
            tools.append(TOOL_MAPPING[requested_tool])

        if tools:
            llm_with_tools = dynamic_llm.bind_tools(
                [convert_to_openai_tool(tool) for tool in tools]
            )
        else:
            llm_with_tools = dynamic_llm

        agent = (
            {
                "input": lambda x: x["input"],
                "agent_scratchpad": lambda x: format_to_openai_tool_messages(
                    x["intermediate_steps"]
                ),
                "chat_history": lambda x: x["chat_history"],
            }
            | prompt
            | prompt_trimmer
            | llm_with_tools
            | OpenAIToolsAgentOutputParser()
        )
        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,  # , max_iterations=3
        ).with_config({"run_name": "agent"})
        return agent_executor

    # Create agent executor with tools
    agent_executor = _create_agent_with_tools(user_inputs["tools"])
    async for event in agent_executor.astream_events(
        {
            "input": user_inputs["input"],
            "chat_history": user_inputs["chat_history"],
        },
        version="v1",
    ):
        final_response = ""
        kind = event["event"]
        if kind == "on_chain_start":
            await logger.aprint("Chain started.")
            if (
                event["name"] == "agent"
            ):  # matches `.with_config({"run_name": "Agent"})` in agent_executor
                for i in re.split(
                    r"(\s)", format_start_text(event["data"].get("input"))
                ):
                    yield i
                    await asyncio.sleep(0.025)
        if kind == "on_chat_model_stream":
            content = event["data"]["chunk"].content
            if content:
                data = ""
                try:
                    data = format_response(json.dumps(eval(str(content))))
                except Exception:
                    data = content
                final_response += str(data or "")
        elif kind == "on_tool_start":
            yield (
                f"\nUsing Tool: {event['name']} "
                f"with inputs: {format_text(event['data'].get('input'))}\n"
            )
        elif kind == "on_tool_end":
            yield (
                f"\nTool {event['name']} "
                f"provided output: {format_text(event['data'].get('output'))}\n"
            )
        elif kind == "on_chain_end":
            await logger.aprint("Chain ended.")
        elif kind == "on_error":
            await logger.aerror(f"Error encountered: {event['error']}")

        yield final_response


# Shared configuration for history fields
HISTORY_FIELDS_CONFIG = [
    ConfigurableFieldSpec(
        id="user_id",
        annotation=str,
        name="User ID",
        description="Unique identifier for the user.",
        default="",  # Default value can be adjusted if needed
        is_shared=True,
    ),
    ConfigurableFieldSpec(
        id="conversation_id",
        annotation=str,
        name="Conversation ID",
        description="Unique identifier for the conversation.",
        default="",  # Default value can be adjusted if needed
        is_shared=True,
    ),
]


# Function to create a chain with history
def create_chain_with_history(
    stream_function: Callable, session_factory: Callable, input_type: Input
) -> RunnableWithMessageHistory:
    """
    Creates a chain with message history support.

    Args:
        stream_function: A callable function for custom streaming.
        session_factory: A callable to create session factory for managing chat histories.
        input_type: The type of input expected by the chain.

    Returns:
        An instance of RunnableWithMessageHistory configured with the provided settings.
    """
    return RunnableWithMessageHistory(
        RunnableLambda(stream_function),  # Custom streaming logic
        session_factory("chat_histories"),  # Factory to manage history sessions
        input_messages_key="input",  # Key for input messages
        history_messages_key="chat_history",  # Key for historical messages
        history_factory_config=HISTORY_FIELDS_CONFIG,  # Configuration for history fields
    ).with_types(input_type=input_type)


# Create a chain instance
chain_with_history = create_chain_with_history(
    custom_stream, create_session_factory, Input
)


# Add routes to the FastAPI app
add_routes(
    app,
    chain_with_history,
    per_req_config_modifier=_per_request_config_modifier,
    path="/rag",
    # Disable playground and batch
    # 1) Playground we're passing information via headers, which is not supported via
    #    the playground right now.
    # 2) Disable batch to avoid users being confused. Batch will work fine
    #    as long as users invoke it with multiple configs appropriately, but
    #    without validation users are likely going to forget to do that.
    #    In addition, there's likely little sense in support batch for a chatbot.
    disabled_endpoints=["playground", "batch"],
)


# Run the FastAPI app with Uvicorn
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
