# Dockerfile.ui の apt-get 部分に graphviz を追加
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
# Added graphviz for visualization
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg graphviz \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ .

# Run Streamlit
CMD ["streamlit", "run", "app/ui/ui.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
