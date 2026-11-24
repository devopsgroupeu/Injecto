# Use a slim Python image for a smaller footprint. Pinned by digest (the
# multi-arch index), so a rebuild uses exactly this image until it is bumped on
# purpose; the tag alone would follow whatever is pushed under it (OP-191).
FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

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

# No .pyc writes at runtime: the code is root-owned and the root filesystem can
# be read-only, so Python could not write them anyway.
ENV PYTHONDONTWRITEBYTECODE=1

# Set the working directory inside the container
WORKDIR /app

# Terraform for `terraform fmt`. The checksums are the linux lines of
# HashiCorp's terraform_<version>_SHA256SUMS, whose signature was verified
# against HashiCorp's release key when they were pinned. Pinning them here,
# rather than downloading SHA256SUMS next to the zip, means a tampered or
# swapped download fails the build instead of being checked against a file from
# the same host (OP-191). Bump all three together.
# 1.11.4 was built with Go 1.23 and old x/crypto, x/net and grpc, which Trivy
# reports as 57 fixable HIGH/CRITICAL findings in /usr/local/bin/terraform.
ARG TERRAFORM_VERSION=1.17.2
ARG TERRAFORM_SHA256_AMD64=e6f16b2f0b137ee5729caa8c4e79a3bae4ee261acd198a1fcfa8584a6296605b
ARG TERRAFORM_SHA256_ARM64=858e08c181a76b6b223e8c767a8e983922eebe2d062db949a2de66ce040c368c

# Install git for repository cloning and terraform for formatting.
# zlib1g: Debian security fix the pinned base digest does not carry yet.
#   CVE-2026-85091, fixed in 1:1.3.dfsg+really1.3.1-1+deb13u1.
#   Remove `--only-upgrade zlib1g` once Dependabot bumps the digest to a
#   rebuild that includes it.
RUN apt-get update && \
    apt-get install -y --no-install-recommends git wget unzip && \
    apt-get install -y --no-install-recommends --only-upgrade zlib1g && \
    arch="$(dpkg --print-architecture)" && \
    case "$arch" in \
      amd64) sha256="$TERRAFORM_SHA256_AMD64" ;; \
      arm64) sha256="$TERRAFORM_SHA256_ARM64" ;; \
      *) echo "No pinned Terraform checksum for $arch" >&2; exit 1 ;; \
    esac && \
    wget -qO /tmp/terraform.zip "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_${arch}.zip" && \
    echo "${sha256}  /tmp/terraform.zip" | sha256sum -c - && \
    unzip -o /tmp/terraform.zip -d /usr/local/bin && \
    rm /tmp/terraform.zip && \
    apt-get purge -y wget unzip && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Non-root user with a fixed UID/GID 1000, matching runAsUser/fsGroup in the
# chart (H97). Without --uid/--gid, --system picks a random UID below 1000.
RUN addgroup --system --gid 1000 appgroup \
 && adduser --system --uid 1000 --ingroup appgroup appuser

# Copy only the lock file first to leverage the Docker layer cache
COPY requirements.txt .

# Install the hash-pinned dependencies (generated from requirements.in with
# pip-compile --generate-hashes). --require-hashes fails the build if any
# downloaded file does not match the lock file.
# Then remove pip itself: it is not used at runtime, and its vendored copies of
# urllib3, msgpack and setuptools are what Trivy flags in the image.
RUN pip install --no-cache-dir --require-hashes -r requirements.txt \
 && pip uninstall -y pip

# Copy the source code. It stays root-owned (read-only for the app user), so a
# compromised process cannot rewrite it. The app writes only under /tmp.
COPY injecto/ ./injecto/

# Stamp the release version into the package. The publish workflow builds from
# the commit that TRIGGERED the release, which is one commit older than
# semantic-release's own `chore(release)` commit - so without this the image
# would always report the previous version.
RUN echo "__version__ = \"${INJECTO_VERSION}\"" > ./injecto/version.py

# Switch to the non-root user (numeric, so the kubelet can verify runAsNonRoot)
USER 1000:1000

# Expose port for API mode
EXPOSE 8000

# Prometheus metrics, served on their own port so they are never reachable
# through whatever ingress fronts the API port (see injecto/metrics.py)
EXPOSE 9090

# Define the entrypoint for the container.
# This makes the container behave like an executable for the script.
# Arguments passed to `docker run` will be appended to this command.
ENTRYPOINT ["python", "-m", "injecto.main"]
