import json
import mimetypes
import os
import re
from images import ARCHITECTURE, PLUS
import gradio as gr
import requests
from dotenv import load_dotenv
from gradio import Markdown as m
from langserve import RemoteRunnable
import asyncio
from fastapi import FastAPI
import uvicorn
from logger import AsyncRemoteLogger

# Create an instance of the logger
logger = AsyncRemoteLogger(
    service_url="http://logger:8181", app_name="MAAP-AWS-Anthropic-UI"
)

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")

app = FastAPI(
    title="MAAP - MongoDB AI Applications Program",
    version="1.0",
    description="MongoDB AI Applications Program",
)

# Claude models dictionary
claude_models = {
    "Claude 3.5 Sonnet (US, v2)": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "Claude 3.5 Sonnet": "anthropic.claude-3-5-sonnet-20240620-v1:0",
    "Claude 3.5 Haiku (US)": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    "Claude 3 Haiku": "anthropic.claude-3-haiku-20240307-v1:0",
    "Claude 3 Sonnet": "anthropic.claude-3-sonnet-20240229-v1:0",
    "Claude 3 Opus (US)": "us.anthropic.claude-3-opus-20240229-v1:0",
    "Claude 2.1": "anthropic.claude-v2:1",
    "Claude 2": "anthropic.claude-v2",
    "Claude 1 Instant": "anthropic.claude-instant-v1",
}


async def process_request(message, history, userId, dataSource, tools, llm_model):
    try:
        await logger.aprint(userId, dataSource, tools, llm_model)
        url = "http://main:8000/rag"
        await logger.aprint(message, history)
        if message and len(message) > 0:
            query = message["text"].strip()
            urls = extract_urls(query)
            await logger.aprint(urls)
            num_files = len(message["files"])
            strTempResponse = ""
            if num_files > 0 or len(urls) > 0:
                strTempResponse = ""
                for i in re.split(
                    r"(\s)",
                    "Initiating upload and content vectorization. \nPlease wait....",
                ):
                    strTempResponse += i
                    await asyncio.sleep(0.025)
                    yield strTempResponse

                uploadResult = ingest_data(userId, urls, message["files"])
                if uploadResult:
                    for i in re.split(
                        r"(\s)",
                        "\nFile(s)/URL(s) uploaded  and ingested successfully. \nGiving time for Indexes to Update....",
                    ):
                        strTempResponse += i
                        await asyncio.sleep(0.025)
                        yield strTempResponse
                    await asyncio.sleep(5)
                else:
                    for i in re.split(
                        r"(\s)", "\nFile(s)/URL(s) upload exited with error...."
                    ):
                        strTempResponse += i
                        await asyncio.sleep(0.025)
                        yield strTempResponse

            if len(query) > 0:
                input = json.dumps(
                    {"query": query, "userId": userId, "dataSource": dataSource}
                )
                prompt = {
                    "input": f"{input}",
                    "chat_history": [],
                    "tools": tools,
                    "llm_model": claude_models[llm_model],
                }
                strResponse = ""
                llm = RemoteRunnable(url, cookies={"user_id": userId})
                async for msg in llm.astream(
                    prompt, {"configurable": {"conversation_id": userId}}
                ):
                    strResponse += str(msg) if msg is not None else ""
                    yield strResponse
            else:
                yield "Hi, how may I help you?"
        else:
            yield "Hi, how may I help you?"
    except Exception as error:
        await logger.aerror(error)
        yield "There was an error.\n" + str(error)


def extract_urls(string):
    regex = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
    url = re.findall(regex, string)
    return [x[0] for x in url]


def ingest_data(userId, urls, new_files):
    url = "http://loader:8001/upload"

    inputs = {
        "userId": userId,
        "MongoDB_URI": MONGODB_URI,
        "MongoDB_text_key": "document_text",
        "MongoDB_embedding_key": "document_embedding",
        "MongoDB_index_name": "document_vector_index",
        "MongoDB_database_name": "maap_data_loader",
        "MongoDB_collection_name": "document",
        "WebPagesToIngest": urls,
    }

    payload = {"json_input_params": json.dumps(inputs)}
    files = []

    for file in new_files:

        file_name, file_ext = os.path.splitext(file)
        file_name = os.path.basename(file)
        mime_type, encoding = mimetypes.guess_type(file)
        file_types = [
            ".bmp",
            ".csv",
            ".doc",
            ".docx",
            ".eml",
            ".epub",
            ".heic",
            ".html",
            ".jpeg",
            ".png",
            ".md",
            ".msg",
            ".odt",
            ".org",
            ".p7s",
            ".pdf",
            ".png",
            ".ppt",
            ".pptx",
            ".rst",
            ".rtf",
            ".tiff",
            ".txt",
            ".tsv",
            ".xls",
            ".xlsx",
            ".xml",
            ".vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".vnd.openxmlformats-officedocument.presentationml.presentation",
        ]
        if file_ext in file_types:
            files.append(("files", (file_name, open(file, "rb"), mime_type)))
    headers = {}
    # print(files)
    response = requests.request("POST", url, headers=headers, data=payload, files=files)

    logger.print(response.text)
    if "Successfully uploaded" in response.text:
        return True
    else:
        return False


def print_like_dislike(x: gr.LikeData):
    logger.print(x.index, x.value, x.liked)
    return


head = """
<link rel="shortcut icon" href="https://ok5static.oktacdn.com/bc/image/fileStoreRecord?id=fs0jq9i9e0E4EFpjn297" type="image/x-icon">
"""
mdblogo_svg = "https://ok5static.oktacdn.com/fs/bco/1/fs0jq9i9coLeryBSy297"
anthropiclogo_svg = (
    "https://upload.wikimedia.org/wikipedia/commons/7/78/Anthropic_logo.svg"
)

custom_css = """
           
            .message-row img {
                margin: 0px !important;
            }

            .avatar-container img {
            padding: 0px !important;
            }

            footer {visibility: hidden}; 
        """

with gr.Blocks(
    head=head,
    fill_height=True,
    fill_width=True,
    css=custom_css,
    title="MongoDB AI Applications Program (MAAP)",
    theme=gr.themes.Soft(primary_hue=gr.themes.colors.green),
) as demo:
    with gr.Row():
        m(
            f"""
<center>
    <div style="display: flex; justify-content: center; align-items: center;">
        <a href="https://www.mongodb.com/">
            <img src="{mdblogo_svg}" width="250px" style="margin-right: 20px"/>
        </a>
    <img src="{PLUS}" width="30px" style="margin-right: 20px;margin-left: 5px;margin-top: 10px;"/>
        <a href="https://www.anthropic.com/">
            <img src="{anthropiclogo_svg}" width="250px" style="margin-top: 10px;"/>
        </a>
    </div>
    <h1>MongoDB AI Applications Program (<a href="https://www.mongodb.com/services/consulting/ai-applications-program">MAAP</a>)</h1>
    <h3>An integrated end-to-end technology stack in the form of MAAP Framework.</h3>
</center>
"""
        )

    with gr.Accordion(label="--- Inputs ---", open=True) as AdditionalInputs:
        m(
            """<p>
    Enter a User ID to store and retrieve user-specific file data from MongoDB. 
    Select the relevant MongoDB Atlas data source(s) for Vector Search. 
    Upload files using the Attach (clip) button or provide URL(s) to extract information, which will be stored in the MongoDB Atlas Vector Database for performing contextually relevant searches. 
    Receive relevant query responses from <a href="https://www.anthropic.com/claude">Anthropic's Claude LLM</a>, using the data retrieved from MongoDB.
        </p>
        """
        )
        txtUserId = gr.Textbox(
            value="your.email@yourdomain.com", label="User Id", key="UserId"
        )
        chbkgDS = gr.CheckboxGroup(
            choices=["Trip Recommendations", "User Uploaded Data"],
            value=["Trip Recommendations", "User Uploaded Data"],
            label="MongoDB Datasources",
            info="Which collection(s) to look for relevant information?",
            key="db",
        )
        chbkgTools = gr.CheckboxGroup(
            choices=[
                "Lookup by Name",
                "Lookup by Country",
                "Lookup by Best Time to Visit",
                "MongoDB Vector Search",
                "MongoDB FullText Search",
                "MongoDB Hybrid Search",
            ],
            value=[
                "Lookup by Name",
                "Lookup by Country",
                "Lookup by Best Time to Visit",
                "MongoDB Vector Search",
                "MongoDB FullText Search",
                "MongoDB Hybrid Search",
            ],
            label="MongoDB Atlas Data Retrieval Tools",
            info="Which tools should the agent choose from to extract relevant information?",
            key="tools",
        )
        model_dropdown = gr.Dropdown(
        choices=list(claude_models.keys()),
        interactive=True,
        label="Anthropic's Claude LLM",
        info="Which Anthropic's Claude LLM from AWS Bedrock to use?",
        value="Claude 3.5 Sonnet (US, v2)"  # Default value
        )

    txtChatInput = gr.MultimodalTextbox(
        interactive=True,
        file_count="multiple",
        placeholder="Type your query and/or upload file(s) and interact with it...",
        label="User Query",
        show_label=True,
        render=False,
    )
    examples = [
        [
            "Recommend places to visit in India.",
            "your.email@yourdomain.com",
            ["Trip Recommendations"],
            [
                "Lookup by Name",
                "Lookup by Country",
                "Lookup by Best Time to Visit",
                "MongoDB Vector Search",
            ],
            "Claude 3.5 Sonnet (US, v2)"
        ],
        [
            "Explain https://www.mongodb.com/services/consulting/ai-applications-program",
            "your.email@yourdomain.com",
            ["User Uploaded Data"],
            [
                "MongoDB Hybrid Search",
                "MongoDB FullText Search",
                "MongoDB Vector Search",
            ],
            "Claude 3.5 Sonnet (US, v2)"
        ],
        [
            "Suggest top places to visit in India with lush green forests near Delhi.",
            "mohammaddaoud@mongodb.com",
            ["Trip Recommendations"],
            [
                "Lookup by Name",
                "Lookup by Country",
                "MongoDB Hybrid Search",
                "MongoDB FullText Search",
                "MongoDB Vector Search",
            ],
            "Claude 3.5 Sonnet (US, v2)"
        ],
        [
            "Explain how MongoDB helped Ceto AI in Pioneering predictive analytics in maritime logistics?",
            "mohammad.farooqi@mongodb.com",
            ["User Uploaded Data"],
            [
                "MongoDB Hybrid Search",
                "MongoDB FullText Search",
                "MongoDB Vector Search",
            ],
            "Claude 3.5 Sonnet (US, v2)"
        ],
    ]
    bot = gr.Chatbot(
        elem_id="chatbot",
        bubble_full_width=True,
        type="messages",
        autoscroll=True,
        # avatar_images=["/code/images/user.png", "/code/images/mongo.png"],
        avatar_images=[
            "https://ca.slack-edge.com/E01C4Q4H3CL-U04D0GXU2B1-g1a101208f57-192",
            "https://avatars.slack-edge.com/2021-11-01/2659084361479_b7c132367d18b6b7ffa0_512.png",
        ],
        show_copy_button=True,
        render=False,
        min_height="450px",
        label="Type your query and/or upload file(s) and interact with it...",
    )
    bot.like(print_like_dislike, None, None, like_user_message=False)

    CI = gr.ChatInterface(
        fn=process_request,
        chatbot=bot,
        # examples=examples,
        type="messages",
        title="",
        description="",
        multimodal=True,
        additional_inputs=[
            txtUserId,
            chbkgDS,
            chbkgTools,
            model_dropdown
        ],
        additional_inputs_accordion=AdditionalInputs,
        textbox=txtChatInput,
        fill_height=True,
        show_progress=False,
        concurrency_limit=None,
    )

    gr.Examples(
        examples,
        inputs=[
            txtChatInput,
            txtUserId,
            chbkgDS,
            chbkgTools,
            model_dropdown
        ],
        examples_per_page=2,
    )

    with gr.Accordion(label="--- Architecture ---", open=True) as AdditionalInputs:
        gr.HTML(f"""<img src="{ARCHITECTURE}" />""")
    with gr.Row():

        m(
            """
            <center><a href="https://www.mongodb.com/">MongoDB</a>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
            <a href="https://www.anthropic.com/">Anthropic</a>
            </center>
       """
        )


if __name__ == "__main__":
    app = gr.mount_gradio_app(app, demo, path="/",server_name = "0.0.0.0",
    server_port = 7860)
    uvicorn.run(app, host="0.0.0.0", port=7860)
