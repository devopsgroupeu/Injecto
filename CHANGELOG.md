# Changelog

All notable changes to this project will be documented in this file.

## [0.13.6](https://github.com/devopsgroupeu/Injecto/compare/v0.13.5...v0.13.6) (2026-10-30)

### 🐛 Bug Fixes

* **docker:** verify the Terraform download and pin the base image by digest (OP-191) ([#38](https://github.com/devopsgroupeu/Injecto/issues/38)) ([7ec264a](https://github.com/devopsgroupeu/Injecto/commit/7ec264a3c78d9df7e56e4e6c011b460672095a63))

## [0.13.5](https://github.com/devopsgroupeu/Injecto/compare/v0.13.4...v0.13.5) (2026-10-30)

### 🐛 Bug Fixes

* bound the templates cache, request bodies and the result ZIP (OP-259) ([#37](https://github.com/devopsgroupeu/Injecto/issues/37)) ([46df22a](https://github.com/devopsgroupeu/Injecto/commit/46df22afdbcbd9645c5fa61db5da56953344a668))

## [0.13.4](https://github.com/devopsgroupeu/Injecto/compare/v0.13.3...v0.13.4) (2026-10-29)

### 🐛 Bug Fixes

* **auth:** refuse to start or serve without a service token unless explicitly disabled (OP-260) ([#33](https://github.com/devopsgroupeu/Injecto/issues/33)) ([1a45933](https://github.com/devopsgroupeu/Injecto/commit/1a45933bcfd72397b26a7daa256ad2a8905d3e13))

## [0.13.3](https://github.com/devopsgroupeu/Injecto/compare/v0.13.2...v0.13.3) (2026-10-29)

### 🐛 Bug Fixes

* harden request inputs against HCL injection, path traversal and allowlist bypass (OP-259) ([#32](https://github.com/devopsgroupeu/Injecto/issues/32)) ([3749fbd](https://github.com/devopsgroupeu/Injecto/commit/3749fbdb1c1d5980c47639037d6804418c739ec6))

## [0.13.2](https://github.com/devopsgroupeu/Injecto/compare/v0.13.1...v0.13.2) (2026-10-29)

### 🐛 Bug Fixes

* **api:** run blocking processing handlers in the threadpool so they cannot stall the event loop (OP-264) ([#34](https://github.com/devopsgroupeu/Injecto/issues/34)) ([c6e95ed](https://github.com/devopsgroupeu/Injecto/commit/c6e95edeb426bdd863760125ab3a97824024d62a))

## [0.13.1](https://github.com/devopsgroupeu/Injecto/compare/v0.13.0...v0.13.1) (2026-10-29)

### 🐛 Bug Fixes

* **deps:** bump python-multipart to 0.0.32 (OP-191) ([#35](https://github.com/devopsgroupeu/Injecto/issues/35)) ([f9ca068](https://github.com/devopsgroupeu/Injecto/commit/f9ca068f889a4839b2217b9ee3371f20fee96d65))

## [0.13.0](https://github.com/devopsgroupeu/Injecto/compare/v0.12.0...v0.13.0) (2026-10-28)

### 🚀 Features

* **metrics:** expose red metrics on a dedicated port (OP-176) ([#31](https://github.com/devopsgroupeu/Injecto/issues/31)) ([837f067](https://github.com/devopsgroupeu/Injecto/commit/837f0671202cf37d51d261376ee4c95356706b2c))

## [0.12.0](https://github.com/devopsgroupeu/Injecto/compare/v0.11.0...v0.12.0) (2026-09-14)

### 🚀 Features

* cache templates repo with shallow clone ([#24](https://github.com/devopsgroupeu/Injecto/issues/24)) ([68e779a](https://github.com/devopsgroupeu/Injecto/commit/68e779af7094c0de898ef1472575c31282dd601e))

### 📚 Documentation

* state the decorator grammar and catalog extraction in the README ([#30](https://github.com/devopsgroupeu/Injecto/issues/30)) ([de40404](https://github.com/devopsgroupeu/Injecto/commit/de4040449f8a31c77a24e830d1d588de0c4ae8ee))

## [0.11.0](https://github.com/devopsgroupeu/Injecto/compare/v0.10.0...v0.11.0) (2026-09-01)

### 🚀 Features

* **catalog:** carry field validation patterns from the templates into the catalog ([9095eb0](https://github.com/devopsgroupeu/Injecto/commit/9095eb055824704e574aa9fda1922fba85d37cd5))

## [0.10.0](https://github.com/devopsgroupeu/Injecto/compare/v0.9.1...v0.10.0) (2026-08-31)

### 🚀 Features

* **catalog:** let section markers declare a label and a default ([7e969a4](https://github.com/devopsgroupeu/Injecto/commit/7e969a481baa52ed97db7ef7d68fc9b6bcd2e897))

### 🐛 Bug Fixes

* **catalog:** coerce module available to a boolean the wizard can act on ([37488b2](https://github.com/devopsgroupeu/Injecto/commit/37488b21a70d4ff14fccd9b43a45aa931e5531f1))

## [0.9.1](https://github.com/devopsgroupeu/Injecto/compare/v0.9.0...v0.9.1) (2026-08-31)

### 🐛 Bug Fixes

* **catalog:** emit nested section toggles and parse structured defaults ([7e1de51](https://github.com/devopsgroupeu/Injecto/commit/7e1de51a755727dfca6e27a04cfac6488642cbd0))

## [0.9.0](https://github.com/devopsgroupeu/Injecto/compare/v0.8.0...v0.9.0) (2026-08-31)

### 🚀 Features

* **catalog:** use one vocabulary for the catalog and the wizard ([f914baa](https://github.com/devopsgroupeu/Injecto/commit/f914baaadd879144fe810dc4bbdf5c451e26da45))

## [0.8.0](https://github.com/devopsgroupeu/Injecto/compare/v0.7.0...v0.8.0) (2026-08-20)

### 🚀 Features

* **processing:** add opt-in TRIM_DECORATOR_ATTRS to keep wizard metadata out of generated output (OP-226) ([#25](https://github.com/devopsgroupeu/Injecto/issues/25)) ([22c4c9b](https://github.com/devopsgroupeu/Injecto/commit/22c4c9b509c8cc66bddd6693f749967f60c7fd12))

## [0.7.0](https://github.com/devopsgroupeu/Injecto/compare/v0.6.0...v0.7.0) (2026-08-19)

### 🚀 Features

* **catalog:** serve the catalog over an authenticated, sha-cached GET /catalog (OP-204) ([#23](https://github.com/devopsgroupeu/Injecto/issues/23)) ([8008b00](https://github.com/devopsgroupeu/Injecto/commit/8008b0051896bca7d2fc2059111432c5f54da1ec))

## [0.6.0](https://github.com/devopsgroupeu/Injecto/compare/v0.5.1...v0.6.0) (2026-08-19)

### 🚀 Features

* **catalog:** extract the wizard service catalog from decorated templates (OP-204) ([#22](https://github.com/devopsgroupeu/Injecto/issues/22)) ([03e5c0f](https://github.com/devopsgroupeu/Injecto/commit/03e5c0f5d75c95b7e0b40e6da392211078891132))

## [0.5.1](https://github.com/devopsgroupeu/Injecto/compare/v0.5.0...v0.5.1) (2026-08-11)

### 🐛 Bug Fixes

* **packaging:** run Injecto as a real package and report the running version ([#21](https://github.com/devopsgroupeu/Injecto/issues/21)) ([48eea58](https://github.com/devopsgroupeu/Injecto/commit/48eea58a119d0f0545b4845ef17ba69253d5d39d))

## [0.5.0](https://github.com/devopsgroupeu/Injecto/compare/v0.4.5...v0.5.0) (2026-08-10)

### 🚀 Features

* fail generation when files are dropped, with a machine-readable 422 (OP-214) ([#20](https://github.com/devopsgroupeu/Injecto/issues/20)) ([c371b14](https://github.com/devopsgroupeu/Injecto/commit/c371b14f1e2487f37e6f41ba7965e71b68134f19))

## [0.4.5](https://github.com/devopsgroupeu/Injecto/compare/v0.4.4...v0.4.5) (2026-08-10)

### 🐛 Bug Fixes

* escape HCL string values and restrict git clone transports (OP-175) ([#19](https://github.com/devopsgroupeu/Injecto/issues/19)) ([8971643](https://github.com/devopsgroupeu/Injecto/commit/89716437a6d5c4ff28ae7c2970b6de89d0fa5520))

## [0.4.4](https://github.com/devopsgroupeu/Injecto/compare/v0.4.3...v0.4.4) (2026-08-10)

### 🐛 Bug Fixes

* reject upload filenames that escape the input directory (OP-192) ([#18](https://github.com/devopsgroupeu/Injecto/issues/18)) ([cb1c3e3](https://github.com/devopsgroupeu/Injecto/commit/cb1c3e3f2f4fc86b4fcf237c371ee8df030e6c9c))

## [0.4.3](https://github.com/devopsgroupeu/Injecto/compare/v0.4.2...v0.4.3) (2026-08-10)

### 🐛 Bug Fixes

* refuse to substitute [@param](https://github.com/param) values that open a multi-line block (OP-221) ([#17](https://github.com/devopsgroupeu/Injecto/issues/17)) ([9d86126](https://github.com/devopsgroupeu/Injecto/commit/9d86126df3b789f0a6b67b240c09bd395777400b))

## [0.4.2](https://github.com/devopsgroupeu/Injecto/compare/v0.4.1...v0.4.2) (2026-08-10)

### ♻️ Code Refactoring

* extract the shared git generate pipeline behind both git endpoints ([430064d](https://github.com/devopsgroupeu/Injecto/commit/430064d069a8488c474864218cee820edea73c81))

## [0.4.1](https://github.com/devopsgroupeu/Injecto/compare/v0.4.0...v0.4.1) (2026-08-10)

### 🐛 Bug Fixes

* run terraform fmt in the CLI path, not only the API ([#14](https://github.com/devopsgroupeu/Injecto/issues/14)) ([1a660eb](https://github.com/devopsgroupeu/Injecto/commit/1a660eb7cdee57abff93f6e37d6164a7b7ffe112))

## [0.4.0](https://github.com/devopsgroupeu/Injecto/compare/v0.3.3...v0.4.0) (2026-07-07)

### 🚀 Features

* **logging:** unified JSON logs with cross-service request-id correlation ([#12](https://github.com/devopsgroupeu/Injecto/issues/12)) ([2e0c0ea](https://github.com/devopsgroupeu/Injecto/commit/2e0c0ea154de4e512f8922eddc5742913cf214c8))

## [0.3.3](https://github.com/devopsgroupeu/Injecto/compare/v0.3.2...v0.3.3) (2026-07-07)

### 🏗️ Build System

* adopt semantic-release pipeline and enable CI (unified versioning) ([#11](https://github.com/devopsgroupeu/Injecto/issues/11)) ([931dd30](https://github.com/devopsgroupeu/Injecto/commit/931dd30361a38c6df7d8e86c605b69a1ecb133bd))

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
