<p align="center"><img src="ddlp.png" alt="" width="180"></p>

<p align="center">ddlp</p>

yt-dlp frontend for local use.

## Run locally

    pip install -r requirements.txt
    uvicorn main:app

Open http://localhost:8000

## Run with Docker

    docker build -t ddlp .
    docker run -d -p 8000:8000 ddlp

Open http://localhost:8000
