FROM python:3.10-slim

COPY ./requirements.txt /code/requirements.txt
COPY ./app/mongodb_atlas_retriever_tools.py /code/app/mongodb_atlas_retriever_tools.py
COPY ./app/models.py /code/app/models.py
COPY ./app/server.py /code/app/server.py
COPY ./app/logger.py /code/app/logger.py
COPY ./app/.env /code/app/.env
COPY pyproject.toml /code/pyproject.toml

RUN apt-get clean && \
    apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y git


EXPOSE 8000

WORKDIR /code

RUN pip install -r requirements.txt

ENTRYPOINT [ "langchain", "serve","--host=0.0.0.0","--port=8000" ]