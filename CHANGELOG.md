# Changelog

## [0.3.0] - 2026-03-08
### Added
- Terraform fmt post-processing: automatically formats all `.tf` files after template processing
- Terraform 1.11.4 binary included in Docker image

### Changed
- Version is now defined in a single place (`src/version.py`) — API, health endpoint, and package metadata all read from it

## [0.2.1] - 2025-11-18
### Added
- Helm chart for Kubernetes deployment with comprehensive configuration options
- Kubernetes Deployment, Service, ServiceAccount, and optional Ingress resources
- HorizontalPodAutoscaler support for autoscaling
- Security contexts with non-root user and read-only filesystem
- Liveness and readiness probes using `/health` endpoint
- Complete Helm chart documentation (README.md, INSTALLATION.md, QUICKSTART.md)

### Fixed
- Log file path changed to `/tmp/injecto.log` for Kubernetes read-only filesystem compatibility

## [0.1.0] - 2025-08-06
### Added
- Initial public release
- Dockerfile for containerized usage
- GitHub Actions CI pipeline
- Project documentation and usage examples
- Instructions for docker
- docker-compose.yml file
