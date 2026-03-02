FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir setuptools && pip install --no-cache-dir -r requirements.txt

COPY . .

# Build Census surname lookup (downloads ~12MB, produces app/data/census_surnames.pkl).
# Skips automatically if the file already exists (volume-mount case in dev).
RUN python scripts/build_census_data.py

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
