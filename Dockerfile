# Use Python 3.10 slim image
FROM python:3.10-slim

# Install system dependencies, including shellcheck for static analysis
RUN apt-get update && apt-get install -y --no-install-recommends \
    shellcheck \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /app

# Copy requirement definition if exists, or install core dependencies directly
RUN pip install --no-cache-dir \
    google-genai==2.8.0 \
    pydantic==2.13.4 \
    python-dotenv==1.0.1

# Copy agent codebase
COPY . .

# Set entrypoint to run the improve.py agent script
ENTRYPOINT ["python", "improve.py"]
