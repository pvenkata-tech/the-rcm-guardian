FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY rcm_guardian ./rcm_guardian

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "rcm_guardian.app:app", "--host", "0.0.0.0", "--port", "8000"]
