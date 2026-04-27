FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    GRADES_DB_PATH=/data/grades.db

WORKDIR /app

# Dependencias del sistema mínimas: build-essential para python-Levenshtein
# y libs que reportlab usa para fuentes/imágenes.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app.py database.py processor.py ./

# /data persistirá la BD; /work para archivos de trabajo (uploads/exports)
RUN mkdir -p /data /work

EXPOSE 8501

# headless=true: evita que Streamlit intente abrir un navegador en el contenedor
# address=0.0.0.0: necesario para que sea accesible desde el host
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
