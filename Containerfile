FROM registry.access.redhat.com/ubi9/python-311:9.5

# Set working directory
WORKDIR /app

# Copy required files
COPY exporter.py /app/

# Install required Python packages
RUN pip install --no-cache-dir openai prometheus_client requests

# Expose port for Prometheus metrics
EXPOSE 8000

# Set the command to run the exporter
CMD ["python", "exporter.py"]