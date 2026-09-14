FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY run.py .

# Git-Commit-Hash des gebauten Stands, fuer die Versionsanzeige in der
# Fusszeile (siehe app/templating.py) - wird beim Image-Build per
# --build-arg gesetzt (siehe .github/workflows/docker-publish.yml).
ARG GIT_SHA=dev
ENV APP_VERSION=${GIT_SHA}

ENV DATA_DIR=/data
VOLUME ["/data"]

EXPOSE 5000

CMD ["python", "run.py"]
