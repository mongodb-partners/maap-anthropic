FROM python:3.10-slim

COPY ./requirements.txt /code/requirements.txt
COPY ./main.py /code/main.py
COPY ./.env /code/.env

# Set up working directory
WORKDIR /code

RUN pip install -r requirements.txt

EXPOSE 8181
ENTRYPOINT [ "python3", "main.py" ]