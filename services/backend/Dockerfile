FROM python:3.9
WORKDIR /app

# Python dependencies
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Application source
COPY src/ .

# Note: Chrome Extension source is mounted via docker-compose.yaml
# at /app/extension for dynamic ZIP generation

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
