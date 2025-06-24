# Use official Python base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system build dependencies and required libraries
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    gnupg \
    dirmngr && \
    apt-key update

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libdbus-1-dev \
    libglib2.0-dev \
    meson \
    ninja-build \
    pkg-config \
    libssl-dev \
    libffi-dev \
    curl && \
    rm -rf /var/lib/apt/lists/*


# Upgrade pip, setuptools, and wheel
RUN pip install --upgrade pip setuptools wheel

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application source code
COPY . .

# Expose port (Cloud Run default)
EXPOSE 8080

# Command to start the app
CMD ["python", "src/web_interface.py"]
