# Injecto Helm Chart

![Version: 0.2.0](https://img.shields.io/badge/Version-0.2.0-informational?style=flat-square)
![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square)
![AppVersion: 0.2.0-alpha.2](https://img.shields.io/badge/AppVersion-0.2.0--alpha.2-informational?style=flat-square)

A Helm chart for deploying Injecto - a Python tool that processes configuration files with YAML data injection using `@param` and `@section` directives.

## Description

Injecto is a configuration file processing tool that automatically replaces placeholders in code or configuration files with values from YAML files. It runs as a REST API service in Kubernetes, providing endpoints for processing configuration templates from Git repositories or uploaded files.

## Features

- 🔄 **Dynamic Configuration Processing**: Process templates with `@param` and `@section` directives
- 🌐 **REST API**: FastAPI-based service with health checks and multiple processing endpoints
- 🔒 **Security**: Non-root container execution, read-only filesystem, security contexts
- 📈 **Autoscaling**: Optional HorizontalPodAutoscaler for dynamic scaling
- 🚀 **Production-Ready**: Includes liveness/readiness probes, resource limits, and best practices
- 🔐 **Git Integration**: Process configuration files directly from Git repositories
- 📦 **File Upload Support**: Process uploaded configuration files and download results

## Prerequisites

- Kubernetes 1.19+
- Helm 3.0+
- (Optional) Ingress controller for external access
- (Optional) Metrics Server for HPA

## Installing the Chart

### From local chart directory

```bash
# Install with default values
helm install injecto ./chart

# Install with custom values
helm install injecto ./chart -f custom-values.yaml

# Install in a specific namespace
helm install injecto ./chart --namespace injecto --create-namespace
```

### From Helm repository (if published)

```bash
# Add the repository
helm repo add devopsgroup https://charts.devopsgroup.eu
helm repo update

# Install the chart
helm install injecto devopsgroup/injecto
```

## Uninstalling the Chart

```bash
helm uninstall injecto

# Uninstall from specific namespace
helm uninstall injecto --namespace injecto
```

## Configuration

### Basic Configuration

The following table lists the key configurable parameters of the Injecto chart and their default values.

#### Image Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `image.repository` | Container image repository | `ghcr.io/devopsgroupeu/injecto` |
| `image.pullPolicy` | Image pull policy | `IfNotPresent` |
| `image.tag` | Image tag (overrides appVersion) | `""` |
| `imagePullSecrets` | Image pull secrets for private registries | `[]` |

#### Deployment Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `replicaCount` | Number of replicas | `1` |
| `nameOverride` | Override chart name | `""` |
| `fullnameOverride` | Override full release name | `""` |

#### Service Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `service.type` | Service type | `ClusterIP` |
| `service.port` | Service port | `8000` |
| `service.targetPort` | Container target port | `8000` |
| `service.annotations` | Service annotations | `{}` |

#### Ingress Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ingress.enabled` | Enable ingress | `false` |
| `ingress.className` | Ingress class name | `""` |
| `ingress.annotations` | Ingress annotations | `{}` |
| `ingress.hosts` | Ingress hosts configuration | See [values.yaml](values.yaml) |
| `ingress.tls` | Ingress TLS configuration | `[]` |

#### Resource Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `resources.limits.cpu` | CPU limit | `500m` |
| `resources.limits.memory` | Memory limit | `512Mi` |
| `resources.requests.cpu` | CPU request | `250m` |
| `resources.requests.memory` | Memory request | `256Mi` |

#### Autoscaling Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `autoscaling.enabled` | Enable HPA | `false` |
| `autoscaling.minReplicas` | Minimum replicas | `1` |
| `autoscaling.maxReplicas` | Maximum replicas | `10` |
| `autoscaling.targetCPUUtilizationPercentage` | Target CPU utilization | `80` |
| `autoscaling.targetMemoryUtilizationPercentage` | Target memory utilization | `nil` |

#### Probe Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `livenessProbe.enabled` | Enable liveness probe | `true` |
| `livenessProbe.httpGet.path` | Liveness probe path | `/health` |
| `readinessProbe.enabled` | Enable readiness probe | `true` |
| `readinessProbe.httpGet.path` | Readiness probe path | `/health` |

#### Security Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `podSecurityContext.runAsNonRoot` | Run as non-root | `true` |
| `podSecurityContext.runAsUser` | User ID | `1000` |
| `podSecurityContext.fsGroup` | Filesystem group | `1000` |
| `securityContext.readOnlyRootFilesystem` | Read-only root filesystem | `true` |
| `securityContext.allowPrivilegeEscalation` | Allow privilege escalation | `false` |

#### Injecto-Specific Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `injecto.api.enabled` | Enable API mode | `true` |
| `injecto.api.host` | API host | `0.0.0.0` |
| `injecto.api.port` | API port | `8000` |
| `injecto.api.debug` | Enable debug mode | `false` |
| `injecto.extraArgs` | Additional CLI arguments | `[]` |

### Example Configurations

#### Minimal Production Deployment

```yaml
# production-values.yaml
replicaCount: 2

resources:
  limits:
    cpu: 1000m
    memory: 1Gi
  requests:
    cpu: 500m
    memory: 512Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 5
  targetCPUUtilizationPercentage: 70

ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: injecto.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: injecto-tls
      hosts:
        - injecto.example.com
```

```bash
helm install injecto ./chart -f production-values.yaml
```

#### Development Deployment with Debug Mode

```yaml
# dev-values.yaml
replicaCount: 1

injecto:
  api:
    debug: true

resources:
  limits:
    cpu: 500m
    memory: 512Mi
  requests:
    cpu: 100m
    memory: 128Mi

ingress:
  enabled: false
```

```bash
helm install injecto ./chart -f dev-values.yaml --namespace dev
```

#### Deployment with Private Registry

```yaml
# private-registry-values.yaml
image:
  repository: myregistry.example.com/injecto
  tag: "custom-0.2.0"
  pullPolicy: Always

imagePullSecrets:
  - name: myregistry-secret
```

```bash
# Create registry secret first
kubectl create secret docker-registry myregistry-secret \
  --docker-server=myregistry.example.com \
  --docker-username=myuser \
  --docker-password=mypassword \
  --docker-email=myemail@example.com

# Install chart
helm install injecto ./chart -f private-registry-values.yaml
```

## Usage

### Accessing the API

#### Port Forward (ClusterIP)

```bash
kubectl port-forward svc/injecto 8000:8000
curl http://localhost:8000/health
```

#### NodePort

```bash
export NODE_PORT=$(kubectl get svc injecto -o jsonpath='{.spec.ports[0].nodePort}')
export NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[0].address}')
curl http://$NODE_IP:$NODE_PORT/health
```

#### Ingress

```bash
curl https://injecto.example.com/health
```

### API Endpoints

#### Health Check

```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

#### Process Git Repository

```bash
curl -X POST http://localhost:8000/process \
  -H "Content-Type: application/json" \
  -d '{
    "source": "git",
    "repo_url": "https://github.com/example/configs.git",
    "input_dir": "templates/",
    "data": {
      "database": {
        "host": "prod-db.example.com",
        "port": 5432
      },
      "features": {
        "caching": true
      }
    }
  }'
```

#### Process and Download from Git

```bash
curl -X POST http://localhost:8000/process-git-download \
  -H "Content-Type: application/json" \
  -d '{
    "source": "git",
    "repo_url": "https://github.com/example/configs.git",
    "input_dir": "templates/",
    "data": {
      "environment": "production",
      "replicas": 3
    }
  }' \
  -o processed_configs.zip
```

#### Upload and Process Files

```bash
curl -X POST http://localhost:8000/process-upload \
  -F "files=@template1.yaml" \
  -F "files=@template2.tf" \
  -F "config_files=@config.yaml" \
  -o result.zip
```

## Monitoring

### Health Checks

The chart includes built-in health checks:

- **Liveness Probe**: Checks if the container is alive (`/health` endpoint)
- **Readiness Probe**: Checks if the container is ready to serve traffic (`/health` endpoint)

### Metrics

To enable metrics collection (requires Prometheus):

```yaml
# metrics-values.yaml
podAnnotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "8000"
  prometheus.io/path: "/metrics"  # If you implement metrics endpoint
```

## Upgrading

### Upgrade to new version

```bash
helm upgrade injecto ./chart

# With new values
helm upgrade injecto ./chart -f new-values.yaml

# Force recreation of pods
helm upgrade injecto ./chart --force
```

### Rollback

```bash
# Rollback to previous release
helm rollback injecto

# Rollback to specific revision
helm rollback injecto 2
```

## Troubleshooting

### Check Pod Status

```bash
kubectl get pods -l app.kubernetes.io/name=injecto
kubectl describe pod <pod-name>
```

### View Logs

```bash
# All pods
kubectl logs -l app.kubernetes.io/name=injecto

# Specific pod
kubectl logs <pod-name>

# Follow logs
kubectl logs -f <pod-name>
```

### Debug Container

```bash
# Execute shell in running container
kubectl exec -it <pod-name> -- /bin/sh

# Check environment
kubectl exec <pod-name> -- env
```

### Common Issues

#### Image Pull Errors

```bash
# Verify image pull secret
kubectl get secret <secret-name> -o yaml

# Verify image exists
docker pull ghcr.io/devopsgroupeu/injecto:0.2.0-alpha.2
```

#### Pod Not Ready

```bash
# Check readiness probe
kubectl describe pod <pod-name> | grep -A 5 "Readiness"

# Check logs for startup errors
kubectl logs <pod-name>
```

## Values Reference

For a complete list of all configurable parameters, see [values.yaml](values.yaml).

## Development

### Testing the Chart

```bash
# Lint the chart
helm lint ./chart

# Template and check output
helm template injecto ./chart

# Dry-run installation
helm install injecto ./chart --dry-run --debug

# Install in test namespace
helm install injecto ./chart --namespace test --create-namespace
```

### Packaging the Chart

```bash
# Package the chart
helm package ./chart

# Generate index
helm repo index .
```

## Contributing

We welcome contributions! Please see the main [Injecto Contributing Guidelines](../CONTRIBUTING.md).

## License

Copyright 2025 DevOpsGroup

Licensed under the Apache License, Version 2.0. See [LICENSE](../LICENSE) for details.

## Support

- **GitHub Issues**: [https://github.com/devopsgroupeu/Injecto/issues](https://github.com/devopsgroupeu/Injecto/issues)
- **LinkedIn**: [DevOpsGroup](https://www.linkedin.com/company/devopsgroup8/)

## Links

- **Source Code**: [https://github.com/devopsgroupeu/Injecto](https://github.com/devopsgroupeu/Injecto)
- **Container Registry**: [ghcr.io/devopsgroupeu/injecto](https://ghcr.io/devopsgroupeu/injecto)
