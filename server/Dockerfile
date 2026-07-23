# Bild für den Such-API-Dienst (FastAPI + serverseitige Einbettung).
FROM python:3.11-slim

# Kleine System-Abhängigkeiten für sentence-transformers/torch
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Einbettungsmodell schon beim Bau herunterladen, damit der erste Start
# nicht minutenlang lädt (und der Container offline lauffähig ist).
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('intfloat/multilingual-e5-base')"

COPY api.py import_shamela.py .

EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
