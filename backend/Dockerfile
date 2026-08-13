# Image de l'API. Volontairement minimale : ni pypdf, ni ruff, ni pytest, qui
# ne servent qu'a l'ingestion et a l'outillage (voir requirements-dev.txt).
# Le CV n'entre jamais ici : il vit dans data/, hors du contexte de build.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Utilisateur non privilegie.
RUN useradd --create-home --uid 10001 api && chown -R api:api /srv
USER api

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
