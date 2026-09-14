FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY run.py .

# Versionsangabe des gebauten Stands, fuer die Versionsanzeige in der
# Fusszeile (siehe app/templating.py) - ein Versions-Tag (z.B. "v1.0.0"),
# falls der gebaute Commit eins traegt, sonst die volle Commit-SHA. Wird
# beim Image-Build per --build-arg gesetzt (siehe
# .github/workflows/docker-publish.yml).
ARG APP_VERSION_REF=dev
ENV APP_VERSION=${APP_VERSION_REF}

ENV DATA_DIR=/data
VOLUME ["/data"]

EXPOSE 5000

CMD ["python", "run.py"]
