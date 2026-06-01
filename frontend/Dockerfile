FROM python:3.11-slim

WORKDIR /app

COPY frontend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY frontend/ ./frontend/

ENV PYTHONPATH=/app

EXPOSE 8050
CMD ["python", "-m", "frontend.app"]
