# Injecto

[![LinkedIn](https://img.shields.io/badge/linkedin-%230077B5.svg?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/company/devopsgroup8/)

![GitHub License](https://img.shields.io/github/license/devopsgroupeu/Injecto)
![GitHub Forks](https://img.shields.io/github/forks/devopsgroupeu/Injecto)
![GitHub Stars](https://img.shields.io/github/stars/devopsgroupeu/Injecto)
![GitHub Watchers](https://img.shields.io/github/watchers/devopsgroupeu/Injecto)
![GitHub Issues](https://img.shields.io/github/issues/devopsgroupeu/Injecto)
![GitHub Last Commit](https://img.shields.io/github/last-commit/devopsgroupeu/Injecto)

A Python tool that automatically replaces placeholders in code or configuration files with values from a YAML file.

## ⚙️ Usage

### Local

#### With local source of template files

```sh
python3 src/main.py \
    --input-dir ~/my-local-templates/ \
    --output-dir ./output \
    --data-files ~/data/00_base.yaml ~/data/10_override.yaml
```

#### With git repository as source of template files

```sh
python3 src/main.py \
    --source git \
    --repo-url https://github.com/devopsgroupeu/openprime-infra-templates.git \
    --branch main \
    --input-dir templates/ \    # location of templates in repository
    --output-dir ./output \
    --data-files ~/data/00_base.yaml  ~/data/10_override.yaml
```

### Docker

```sh
docker run --rm \
    -v ~/my-local-templates:/templates \
    -v ~/data:/data \
    -v "$(pwd)/output":/output \
    ghcr.io/devopsgroupeu/injecto:latest \
    --input-dir /templates \
    --output-dir /output \
    --data-files /data/00_base.yaml /data/10_override.yaml
```

## 📜 License

```plain
Copyright 2025 DevOpsGroup

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

## 🤝 Contributing

We welcome contributions from everyone!
Please see our [Contributing Guidelines](CONTRIBUTING.md) to get started.

## 📜 Code of Conduct

Help us keep this community welcoming and respectful.
Read our [Code of Conduct](CODE_OF_CONDUCT.md) to understand the standards we uphold.

## 🗂️ Changelog

For a detailed history of changes, updates, and releases, please check out our [Changelog](CHANGELOG.md).
