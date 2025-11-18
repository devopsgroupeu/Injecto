# Changelog

All notable changes to the Injecto Helm chart will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-01-18

### Added
- Initial Helm chart release for Injecto
- Kubernetes Deployment with configurable replicas
- ClusterIP Service with port 8000
- ServiceAccount with configurable automount
- ConfigMap for Injecto configuration
- Ingress support with TLS configuration
- HorizontalPodAutoscaler for autoscaling (disabled by default)
- Liveness and readiness probes using `/health` endpoint
- Security contexts (non-root user, read-only filesystem)
- Resource limits and requests
- Support for imagePullSecrets
- Comprehensive values.yaml with all configuration options
- Template helpers for common functions
- NOTES.txt for post-installation guidance
- Complete README.md with usage examples
- INSTALLATION.md with detailed installation scenarios
- .helmignore for chart packaging

### Security
- Non-root container execution (UID 1000)
- Read-only root filesystem with temporary directory mount
- Dropped all capabilities
- Disabled privilege escalation
- Pod security context with fsGroup

### Configuration
- Injecto API mode enabled by default
- Configurable API host, port, and debug mode
- Support for additional command-line arguments
- Environment variable injection support
- Volume mount support for custom use cases
- Node selector, tolerations, and affinity rules

### Testing
- Passes `helm lint` validation
- Successfully renders 144 lines of Kubernetes manifests
- Template dry-run tested
- Command arguments properly formatted

## Release Information

- **Chart Version**: 0.2.0
- **App Version**: 0.2.0-alpha.2
- **Image**: ghcr.io/devopsgroupeu/injecto:0.2.0-alpha.2
- **Kubernetes Compatibility**: 1.19+
- **Helm Version**: 3.0+

## Future Enhancements

Planned for future releases:
- ServiceMonitor for Prometheus integration
- PodDisruptionBudget for high availability
- NetworkPolicy for network isolation
- Secrets management for sensitive configuration
- Support for multiple API endpoints/services
- Custom metrics for autoscaling
- Integration with external secret stores (Vault, AWS Secrets Manager)
- Support for Git repository authentication
