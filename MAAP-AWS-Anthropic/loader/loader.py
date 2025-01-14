from langchain_unstructured import UnstructuredLoader
from unstructured.cleaners.core import clean_extra_whitespace
from typing import List
from langchain_core.documents import Document
from logger import AsyncRemoteLogger

# Create an instance of the logger
logger = AsyncRemoteLogger(
    service_url="http://logger:8181", app_name="MAAP-AWS-Anthropic-Loader"
)


def LoadFiles(file_names: List[str], userId) -> List[Document]:
    loader = UnstructuredLoader(
        file_path=file_names,
        post_processors=[clean_extra_whitespace],
        chunking_strategy="basic",
        max_characters=10000,
        include_orig_elements=False,
        strategy="hi_res",
    )

    docs = loader.load()

    logger.print("Number of LangChain documents in Files:", len(docs))

    for doc in docs:
        doc.metadata["userId"] = userId

        logger.print(str(doc))
        logger.print(str(doc.metadata))
        logger.print(
            "Length of text in the file document:", len(doc.page_content)
        )
    # asyncio.sleep(5) # wait for search index build
    return docs


def LoadWeb(urls: List[str], userId) -> List[Document]:
    docs = []
    logger.print(str(urls))
    if len(urls) > 0:
        for url in urls:
            loader = UnstructuredLoader(
                web_url=url,
                post_processors=[clean_extra_whitespace],
                chunking_strategy="basic",
                max_characters=10000,
                include_orig_elements=False,
                strategy="hi_res",
            )

            docs.extend(loader.load())

        logger.print("Number of LangChain documents in Web Urls:", len(docs))

        for doc in docs:
            doc.metadata["userId"] = userId
            logger.print(str(doc))
            logger.print(str(doc.metadata))
            logger.print(
                "Length of text in the web document:", len(doc.page_content)
            )
    # asyncio.sleep(5) # wait for search index build
    return docs
