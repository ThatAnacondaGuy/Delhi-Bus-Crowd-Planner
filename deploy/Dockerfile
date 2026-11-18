FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/app/data

# Hugging Face Spaces run the container as uid 1000
RUN useradd --create-home --uid 1000 user
WORKDIR /app

COPY requirements.lock ./
RUN pip install -r requirements.lock

COPY --chown=user:user src ./src
COPY --chown=user:user frontend ./frontend
COPY --chown=user:user data /app/data
RUN chown user:user /app

USER user
EXPOSE 7860
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "7860"]
