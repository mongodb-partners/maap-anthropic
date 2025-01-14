FROM downloads.unstructured.io/unstructured-io/unstructured:latest

COPY ./requirements.txt /code/requirements.txt
COPY ./main.py /code/main.py
COPY ./loader.py /code/loader.py
COPY ./utils.py /code/utils.py
COPY ./logger.py /code/logger.py
COPY ./.env /code/.env

USER root
# Set up working directory
WORKDIR /code

# Create directories with correct permissions
RUN mkdir -p logs files && \
    chown -R notebook-user:notebook-user logs files && \
    chmod 755 logs files
USER notebook-user

RUN pip install -r requirements.txt

EXPOSE 8001
ENTRYPOINT [ "python3", "main.py" ]