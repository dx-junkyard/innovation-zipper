FROM python:3.9-slim

# Install System Dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    mecab \
    libmecab-dev \
    mecab-ipadic-utf8 \
    git \
    curl \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Add Rust to PATH
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /app

# Install Python Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy Application Code
COPY . .

# Download spaCy model at build time
RUN python -m spacy download ja_core_news_sm

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
