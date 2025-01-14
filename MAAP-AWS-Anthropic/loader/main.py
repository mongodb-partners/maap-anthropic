import json
import traceback
from typing import List
import asyncio
import humanize
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile
from langchain_mongodb import MongoDBAtlasVectorSearch
from typing_extensions import Annotated
import uvicorn
import loader
import utils
import uvicorn
from logger import AsyncRemoteLogger

# Create an instance of the logger
logger = AsyncRemoteLogger(
    service_url="http://logger:8181", app_name="MAAP-AWS-Anthropic-Loader"
)

load_dotenv()

app = FastAPI(
    title="MAAP - MongoDB AI Applications Program",
    version="1.0",
    description="MongoDB AI Applications Program",
)


@app.post("/upload")
async def upload(
    files: Annotated[List[UploadFile], File(description="Multiple files upload.")] = [],
    json_input_params: str = Form(
        description="Pass all input pamaraters as a Json string."
    ),
):
    inputs = {}
    try:
        inputs = json.loads(json_input_params)
        for key, value in inputs.items():
            logger.print(key, " = ", value)

        new_files =  utils.UploadFiles(files)
        logger.print(str(new_files))

        vector_store =  utils.MongoDBAtlasVectorSearch_Obj(inputs)

        try:
            documents = loader.LoadFiles(new_files, inputs["userId"])
            MongoDBAtlasVectorSearch.add_documents(vector_store, documents)
        except Exception as e:
            logger.error(e)
            return {
                "message": "There was an error uploading the file(s)"
                + str(traceback.TracebackException.from_exception(e).stack.format())
            }

        WebPagesToIngest = []
        WebPagesToIngest = inputs["WebPagesToIngest"]
        try:
            logger.print(str(WebPagesToIngest))
            documents = loader.LoadWeb(WebPagesToIngest, inputs["userId"])
            MongoDBAtlasVectorSearch.add_documents(vector_store, documents)
        except Exception as e:
            logger.error(e)
            return {
                "message": "There was an error uploading the webpage(s)"
                + str(traceback.TracebackException.from_exception(e).stack.format())
            }
        msg = [
            " ".join([file.filename, humanize.naturalsize(file.size)]) for file in files
        ]
        # asyncio.sleep(5) # wait for search index build
        return {"message": f"Successfully uploaded {msg}"}
    except Exception as error:
        logger.error(str(error))
        logger.print(str(error))
        return {
            "message": str(
                traceback.TracebackException.from_exception(error).stack.format()
            )
        }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
