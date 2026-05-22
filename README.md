<p align="center"><img src="ddlp.png" alt="" width="180"></p>

<p align="center">ddlp</p>

yt-dlp frontend for local use. made because i can never remember yt-dlp flags and got tired of begging claude to remind me.

## run locally

    git clone https://github.com/ufraaan/ddlp && cd ddlp
    pip install -r requirements.txt
    uvicorn main:app

open http://localhost:8000

## run with docker

    docker build -t ddlp .
    docker run -d -p 8000:8000 ddlp

open http://localhost:8000
