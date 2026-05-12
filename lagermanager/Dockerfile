FROM python:3.12-slim

ARG SUPERCRONIC_VERSION=0.2.33

RUN apt-get update && apt-get install -y \
    gcc \
    freetds-dev \
    freetds-bin \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL \
    "https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
    -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic

RUN git config --global --add safe.directory /app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
