FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src:/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Docling тянет torch: с PyPI по умолчанию ставится CUDA-сборка (+ гигабайты nvidia-*).
# CPU-колёса с download.pytorch.org заметно меньше и не требуют GPU-драйверов в образе.
RUN pip install --upgrade pip && \
    pip install --no-cache-dir \
        torch torchvision \
        --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir --upgrade-strategy only-if-needed -r requirements.txt

COPY . .

# По умолчанию как в compose — v2; переопределение: docker run ... python main.py
CMD ["python", "hay_v2_bot/main.py"]
