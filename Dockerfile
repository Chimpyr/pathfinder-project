FROM python:3.11-slim

LABEL maintainer="ScenicPathFinder"
LABEL description="Multi-purpose image for Flask API and Celery worker"

WORKDIR /app

# Install system dependencies for geospatial libraries
# osmium-tool is used to pre-extract bbox regions from large PBFs
# (pyrosm loads full PBF into memory before clipping, causing OOM on large files)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgeos-dev \
    libproj-dev \
    libgdal-dev \
    libffi-dev \
    curl \
    osmium-tool \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .

# Install Python dependencies
# WORKAROUND: pyrosm depends on pyrobuf which is incompatible with setuptools>=71
# (AttributeError: 'PyrobufDistribution' has no attribute 'dry_run')
# Solution: Force older setuptools via PIP_CONSTRAINT for build isolation environments
# See: https://github.com/appnexus/pyrobuf (unmaintained since 2020)
# Future: Consider migrating to pyosmium or QuackOSM if pyrosm becomes unusable
RUN echo 'setuptools<70' > /tmp/constraints.txt && \
    pip install --no-cache-dir --upgrade pip && \
    PIP_CONSTRAINT=/tmp/constraints.txt pip install --no-cache-dir pyrosm && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose Flask port, documentation only
EXPOSE 5000

# Default: run Flask API
# Override with celery command for worker container
CMD ["python", "run.py"]
