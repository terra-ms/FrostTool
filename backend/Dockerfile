FROM python:3.11-slim

WORKDIR /app

# rasterio bundles GDAL but GDAL still depends on libexpat at runtime.
# libsqlite3-0 is needed by the bundled PROJ database.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libexpat1 \
    libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY crops.txt ./

ENV PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
