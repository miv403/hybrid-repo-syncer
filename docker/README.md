# Hybrid Syncer Container Environment

Standalone Ubuntu 24.04-based container environment with Java 21+ JRE, Python 3, PyYAML, Git, and patched Copybara pre-installed.

## Building the Image

Using Docker:

```bash
docker build -t hybrid-syncer:latest -f docker/Dockerfile .
```

Or using Docker Compose:

```bash
docker compose build
```

## Usage Examples

### Direct Execution via `docker run`

Mount your workspace root into `/app`:

```bash
# Print help
docker run --rm -v $(pwd):/app hybrid-syncer:latest --help

# Run sync using manifest
docker run --rm -v $(pwd):/app hybrid-syncer:latest --manifest sync-manifest.yaml
```

### Execution via `docker compose`

```bash
# Print help
docker compose run --rm syncer --help

# Run sync using manifest
docker compose run --rm syncer --manifest sync-manifest.yaml
```
