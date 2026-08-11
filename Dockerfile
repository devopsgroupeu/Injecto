# Use a slim Python image for a smaller footprint
FROM python:3.13-slim

# The release version, passed in by the publish workflow. It is not just a
# label: it is written into the package below so /health and the OpenAPI docs
# report the version that is actually running. The default marks a local build.
ARG INJECTO_VERSION=0.0.0-dev

# Label the image with metadata
# This helps with image identification and compliance
LABEL org.opencontainers.image.title="injecto"
LABEL org.opencontainers.image.description="A Python tool that automatically replaces placeholders in code or configuration files with values from a YAML file"
LABEL org.opencontainers.image.version="${INJECTO_VERSION}"
LABEL org.opencontainers.image.source="https://github.com/devopsgroupeu/Injecto"
LABEL org.opencontainers.image.authors="Andrej Rabek <andrej.rabek@devopsgroup.sk>"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# Set the working directory inside the container
WORKDIR /app

# Install git for repository cloning and terraform for formatting
RUN apt-get update && \
    apt-get install -y --no-install-recommends git wget unzip && \
    wget -qO /tmp/terraform.zip "https://releases.hashicorp.com/terraform/1.11.4/terraform_1.11.4_linux_$(dpkg --print-architecture).zip" && \
    unzip -o /tmp/terraform.zip -d /usr/local/bin && \
    rm /tmp/terraform.zip && \
    apt-get purge -y wget unzip && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user and group for security
# Running containers as non-root is a best practice.
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Copy only the requirements file first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
# --no-cache-dir reduces image size
# --system installs packages system-wide (good for simple containers)
# Optionally use a virtual environment if preferred
RUN pip install --no-cache-dir -r requirements.txt

# Copy the source code directory into the container's working directory
COPY injecto/ ./injecto/

# Stamp the release version into the package. The publish workflow builds from
# the commit that TRIGGERED the release, which is one commit older than
# semantic-release's own `chore(release)` commit - so without this the image
# would always report the previous version.
RUN echo "__version__ = \"${INJECTO_VERSION}\"" > ./injecto/version.py

# Change ownership of the app directory to the non-root user
# This is important if the entrypoint needs to write files (though our script writes outside /app)
RUN chown -R appuser:appgroup /app
# Switch to the non-root user
USER appuser

# Expose port for API mode
EXPOSE 8000

# Define the entrypoint for the container.
# This makes the container behave like an executable for the script.
# Arguments passed to `docker run` will be appended to this command.
ENTRYPOINT ["python", "-m", "injecto.main"]
