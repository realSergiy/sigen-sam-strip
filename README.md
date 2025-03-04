# SIGEN GALLERY BACKEND

Welcome to the sigen-gallery-backend! This is backend service using Python Flask. Can be run in Docker containers or locally on MPS (Apple Silicon Metal Performance Shaders) or CPU. However, running the backend service on MPS or CPU devices may result in significantly slower performance (FPS).

## **Prerequisites**

Before you begin, ensure you have the following installed on your system:

- Docker and Docker Compose (for containerized deployment)
- Python 3.12+ (for local development)

### **Installing Docker**

To install Docker, follow these steps:

1. Go to the [Docker website](https://www.docker.com/get-started)
2. Follow the installation instructions for your operating system.

## **Quick Start**

To get backend running quickly using Docker, you can use the following command:

```bash
docker compose up --build
```

This will build and start the backend:

- **Backend:** [http://localhost:7263/graphql](http://localhost:7263/graphql)

## **Running Locally**

### 1. Install UV

To install UV, follow these steps:

- Go to the [UV website](https://docs.astral.sh/uv/getting-started/installation/).
- Follow the installation instructions for your operating system.

### 2. Quick Setup

Run the automated setup:

```bash
make setup
```

This will:

- Create a virtual environment if it doesn't exist
- Install ffmpeg and required libraries if not already installed
- Install all project dependencies
- Prompt you to activate the environment

### 3. Activate the environment

```bash
source .venv/bin/activate
```

### 4. Configure VS Code to Recognize the Environment

- Press `Ctrl+Shift+P` to open the command palette
- Search for "Python: Select Interpreter"
- Choose the interpreter from your `.venv` folder

## **Using the Makefile**

```bash
# Install dependencies
make install

# Run development server locally
make dev

# Run tests
make test

# Format code with black and usort
make lint

# Build package
make build

# Download model checkpoints
make download-models

# Check for outdated dependencies
make outdated

# Update all dependencies
make update-deps
```

Options for the `MODEL_SIZE` argument are "tiny", "small", "base_plus" (default), and "large".

> [!WARNING]
> Running the backend service on MPS devices (Apple Silicon) can cause fatal crashes with the Gunicorn worker due to insufficient MPS memory. Try switching to CPU devices by setting the `SAM2_DEMO_FORCE_CPU_DEVICE=1` environment variable.

## **Tips**

- To rebuild the Docker containers (useful if you've made changes to the Dockerfile or dependencies):

  ```bash
  docker compose up --build
  ```

- Or run once in a **watch** mode:

  ```bash
  docker compose up -w
  ```

- To stop the Docker containers:

  ```bash
  docker compose down
  ```

- To fix separators in the Makefile:

  ```bash
  sed -i 's/^    /\t/g' ./Makefile
  ```

---

By following these instructions, you should have a fully functional development environment for the sigen-gallery-backend. Happy coding!
