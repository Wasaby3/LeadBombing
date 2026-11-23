# LeadBombing: веб-приложение + Chrome в виртуальном дисплее (Xvfb) для поиска в 2GIS.
FROM python:3.13-slim-bookworm

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg xvfb xauth fonts-liberation fonts-dejavu-core \
 && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
 && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list \
 && apt-get update && apt-get install -y --no-install-recommends google-chrome-stable \
 && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1001 app
WORKDIR /app
COPY setup.py setup.cfg MANIFEST.in README.md ./
COPY leadbombing ./leadbombing
RUN pip install --no-cache-dir .

USER app
ENV PYTHONUNBUFFERED=1 HOME=/home/app
