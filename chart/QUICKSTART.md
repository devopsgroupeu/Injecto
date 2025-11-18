# Injecto Helm Chart - Quick Start Guide

Get Injecto up and running in your Kubernetes cluster in under 5 minutes!

## Prerequisites Check

```bash
# Verify Kubernetes cluster access
kubectl cluster-info

# Verify Helm installation
helm version

# Verify you're in the right context
kubectl config current-context
```

## Installation Steps

### Step 1: Install Injecto

```bash
# Navigate to the Injecto directory
cd /path/to/Injecto

# Install the chart
helm install injecto ./chart --create-namespace --namespace injecto
```

Expected output:
```
NAME: injecto
LAST DEPLOYED: [timestamp]
NAMESPACE: injecto
STATUS: deployed
REVISION: 1
```

### Step 2: Verify Deployment

```bash
# Check if pod is running
kubectl get pods -n injecto

# Expected output:
# NAME                        READY   STATUS    RESTARTS   AGE
# injecto-xxxxxxxxxx-xxxxx    1/1     Running   0          30s
```

### Step 3: Access Injecto API

```bash
# Port forward to access locally
kubectl port-forward -n injecto svc/injecto 8000:8000

# In another terminal, test the API
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

## Quick API Test

### Example 1: Process a Git Repository

```bash
curl -X POST http://localhost:8000/process \
  -H "Content-Type: application/json" \
  -d '{
    "source": "git",
    "repo_url": "https://github.com/devopsgroupeu/openprime-infra-templates.git",
    "branch": "main",
    "input_dir": "templates/",
    "data": {
      "environment": "development",
      "region": "us-east-1",
      "eks": {
        "cluster": {
          "name": "my-test-cluster",
          "version": "1.28"
        }
      }
    }
  }'
```

### Example 2: Upload and Process Files

```bash
# Create a sample template file
cat > sample-template.yaml <<EOF
# @param environment
env: development

# @param cluster.name
cluster_name: default

# @section features.monitoring begin
monitoring:
  enabled: true
# @section features.monitoring end
EOF

# Create configuration data
cat > config-data.yaml <<EOF
environment: production
cluster:
  name: prod-cluster-1
features:
  monitoring: true
EOF

# Process the files
curl -X POST http://localhost:8000/process-upload \
  -F "files=@sample-template.yaml" \
  -F "config_files=@config-data.yaml" \
  -o result.zip

# Extract and view results
unzip -q result.zip
cat sample-template.yaml
```

## Common Customizations

### Custom Image Version

```bash
helm install injecto ./chart \
  --namespace injecto \
  --create-namespace \
  --set image.tag=0.3.0
```

### Enable Debug Mode

```bash
helm install injecto ./chart \
  --namespace injecto \
  --create-namespace \
  --set injecto.api.debug=true
```

### Enable Ingress

```bash
helm install injecto ./chart \
  --namespace injecto \
  --create-namespace \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=injecto.example.com \
  --set ingress.hosts[0].paths[0].path=/ \
  --set ingress.hosts[0].paths[0].pathType=Prefix
```

### Enable Autoscaling

```bash
helm install injecto ./chart \
  --namespace injecto \
  --create-namespace \
  --set autoscaling.enabled=true \
  --set autoscaling.minReplicas=2 \
  --set autoscaling.maxReplicas=5
```

## Uninstall

```bash
# Remove the Helm release
helm uninstall injecto --namespace injecto

# Delete the namespace
kubectl delete namespace injecto
```

## Next Steps

- **Full Documentation**: See [README.md](README.md)
- **Installation Guide**: See [INSTALLATION.md](INSTALLATION.md)
- **Configuration Options**: See [values.yaml](values.yaml)
- **API Documentation**: Visit https://github.com/devopsgroupeu/Injecto

## Troubleshooting

### Pod Not Starting?

```bash
# Check pod status
kubectl describe pod -n injecto -l app.kubernetes.io/name=injecto

# Check logs
kubectl logs -n injecto -l app.kubernetes.io/name=injecto
```

### Cannot Access API?

```bash
# Verify service is running
kubectl get svc -n injecto

# Check if port-forward is active
lsof -i :8000
```

### Image Pull Errors?

```bash
# For private registries, create a secret:
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=YOUR_USERNAME \
  --docker-password=YOUR_TOKEN \
  --namespace injecto

# Then upgrade the release:
helm upgrade injecto ./chart \
  --namespace injecto \
  --set imagePullSecrets[0].name=ghcr-secret
```

## Support

Need help?
- GitHub Issues: https://github.com/devopsgroupeu/Injecto/issues
- LinkedIn: https://www.linkedin.com/company/devopsgroup8/

---

**Congratulations!** 🎉 You now have Injecto running in your Kubernetes cluster!
