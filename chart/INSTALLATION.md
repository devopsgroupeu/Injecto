# Injecto Helm Chart - Installation Guide

## Quick Start

### Prerequisites

- Kubernetes cluster (1.19+)
- Helm 3.0+
- kubectl configured to access your cluster

### Basic Installation

```bash
# Install with default values
helm install injecto ./chart

# Install in a specific namespace
helm install injecto ./chart --namespace injecto --create-namespace

# Install with custom release name
helm install my-injecto ./chart
```

## Installation Examples

### 1. Development Environment

For local development or testing:

```bash
helm install injecto ./chart \
  --namespace dev \
  --create-namespace \
  --set injecto.api.debug=true \
  --set resources.limits.cpu=500m \
  --set resources.limits.memory=512Mi
```

### 2. Production Environment

For production deployment with autoscaling:

```bash
# Create production values file
cat <<EOF > production-values.yaml
replicaCount: 2

image:
  pullPolicy: Always

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
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
  hosts:
    - host: injecto.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: injecto-tls
      hosts:
        - injecto.example.com
EOF

# Install with production values
helm install injecto ./chart \
  --namespace production \
  --create-namespace \
  -f production-values.yaml
```

### 3. Installation with Private Container Registry

```bash
# Create image pull secret
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=<your-username> \
  --docker-password=<your-token> \
  --namespace injecto

# Install with custom image and pull secret
helm install injecto ./chart \
  --namespace injecto \
  --create-namespace \
  --set image.repository=ghcr.io/devopsgroupeu/injecto \
  --set image.tag=0.2.0-alpha.2 \
  --set imagePullSecrets[0].name=ghcr-secret
```

### 4. High Availability Setup

For mission-critical deployments:

```bash
cat <<EOF > ha-values.yaml
replicaCount: 3

resources:
  limits:
    cpu: 2000m
    memory: 2Gi
  requests:
    cpu: 1000m
    memory: 1Gi

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 10
  targetCPUUtilizationPercentage: 60
  targetMemoryUtilizationPercentage: 70

affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchExpressions:
              - key: app.kubernetes.io/name
                operator: In
                values:
                  - injecto
          topologyKey: kubernetes.io/hostname

podDisruptionBudget:
  enabled: true
  minAvailable: 2
EOF

helm install injecto ./chart \
  --namespace production \
  --create-namespace \
  -f ha-values.yaml
```

## Post-Installation

### Verify Installation

```bash
# Check pod status
kubectl get pods -l app.kubernetes.io/name=injecto

# Check service
kubectl get svc -l app.kubernetes.io/name=injecto

# View installation notes
helm get notes injecto

# Check deployment status
kubectl rollout status deployment/injecto
```

### Access the Service

#### Port Forward (ClusterIP)

```bash
kubectl port-forward svc/injecto 8000:8000
curl http://localhost:8000/health
```

#### Via Ingress

```bash
# Wait for ingress to be ready
kubectl get ingress injecto

# Test the endpoint
curl https://injecto.example.com/health
```

### Test the API

```bash
# Health check
curl http://localhost:8000/health

# Process Git repository (example)
curl -X POST http://localhost:8000/process \
  -H "Content-Type: application/json" \
  -d '{
    "source": "git",
    "repo_url": "https://github.com/devopsgroupeu/openprime-infra-templates.git",
    "input_dir": "templates/",
    "data": {
      "environment": "production",
      "region": "us-east-1"
    }
  }'
```

## Upgrading

### Upgrade to New Version

```bash
# Upgrade with new values
helm upgrade injecto ./chart -f new-values.yaml

# Upgrade with specific image version
helm upgrade injecto ./chart --set image.tag=0.3.0

# Force pod recreation
helm upgrade injecto ./chart --force
```

### Rollback

```bash
# Rollback to previous version
helm rollback injecto

# Rollback to specific revision
helm rollback injecto 2

# View rollout history
helm history injecto
```

## Uninstallation

### Remove the Chart

```bash
# Uninstall release
helm uninstall injecto

# Uninstall from specific namespace
helm uninstall injecto --namespace production

# Remove namespace
kubectl delete namespace injecto
```

### Clean Up Resources

```bash
# Remove persistent volumes (if any)
kubectl delete pvc --all -n injecto

# Remove secrets
kubectl delete secret ghcr-secret -n injecto
```

## Troubleshooting

### Common Issues

#### 1. Image Pull Errors

```bash
# Check image pull secret
kubectl get secret ghcr-secret -o yaml

# Describe pod to see error details
kubectl describe pod <pod-name>

# Verify image exists
docker pull ghcr.io/devopsgroupeu/injecto:0.2.0-alpha.2
```

#### 2. Pod Not Starting

```bash
# Check pod logs
kubectl logs <pod-name>

# Check events
kubectl get events --sort-by=.metadata.creationTimestamp

# Check resource constraints
kubectl describe pod <pod-name> | grep -A 5 "Limits\|Requests"
```

#### 3. Health Check Failures

```bash
# Check liveness probe
kubectl describe pod <pod-name> | grep -A 10 "Liveness"

# Check readiness probe
kubectl describe pod <pod-name> | grep -A 10 "Readiness"

# Test health endpoint directly
kubectl exec <pod-name> -- curl localhost:8000/health
```

#### 4. Ingress Not Working

```bash
# Check ingress status
kubectl describe ingress injecto

# Verify ingress controller is running
kubectl get pods -n ingress-nginx

# Check ingress logs
kubectl logs -n ingress-nginx <ingress-controller-pod>
```

## Configuration Reference

For detailed configuration options, see:
- [README.md](README.md) - Complete documentation
- [values.yaml](values.yaml) - All configurable parameters

## Support

- **Issues**: https://github.com/devopsgroupeu/Injecto/issues
- **Documentation**: https://github.com/devopsgroupeu/Injecto
- **LinkedIn**: https://www.linkedin.com/company/devopsgroup8/
