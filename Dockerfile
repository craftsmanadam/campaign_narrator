FROM python:3.14-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml poetry.lock ./
COPY app ./app

RUN pip install --no-cache-dir .

ENTRYPOINT ["campaignnarrator"]
