# AppPilot Agent

Docker Compose deployment agent for AppPilot platform.

## Features

- Docker Compose application deployment
- Multi-container application support
- Automatic port assignment
- Template-based deployments
- JWT authentication
- Health monitoring

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run agent
python agent_compose_support.py
```

## Configuration

Set environment variables:
- `API_SERVER_URL` - AppPilot API server URL
- `AGENT_ID` - Unique agent identifier
- `JWT_TOKEN` - Authentication token

## Docker

```bash
# Build image
docker build -t apppilot-agent .

# Run container
docker run -d --name apppilot-agent apppilot-agent
```

## License

MIT License
