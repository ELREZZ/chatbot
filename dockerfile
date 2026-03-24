FROM python:3.12.3-slim

# Set working directory
WORKDIR /app

# System deps (needed for some langchain loaders)
RUN apt-get update && apt-get install -y \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy files
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Expose port
EXPOSE 8000

# Run app
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]