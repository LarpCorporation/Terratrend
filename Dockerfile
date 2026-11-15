FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for NetCDF4, HDF5 and health check curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libnetcdf-dev \
    libhdf5-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Environment configuration
ENV HOST=0.0.0.0
ENV PORT=8517

EXPOSE 8517

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/catalog || exit 1

CMD ["python", "backend/server.py"]
