FROM docker.repos.balad.ir/ubuntu:20.04

WORKDIR /scraper
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get install -y ucspi-tcp redis-server git redir tmux python3-pip virtualenv vim

ADD requirements.txt .

RUN pip3 install -r requirements.txt

ADD . .