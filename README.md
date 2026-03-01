# D&D Campaign Manager

A FastAPI-based web application for managing Dungeons & Dragons campaigns and characters. This application allows Dungeon Masters and players to create, manage, and share character sheets, campaigns, and player information with an intuitive web interface.

## Features

- 🎭 Character sheet management
- 🏰 Campaign creation and management
- 👥 Player management
- 🔗 Shareable character links
- 🌍 Multi-language support (English, Russian)
- 🔐 User authentication and authorization
- 📊 Character statistics and skills tracking

## Prerequisites

Before you begin, ensure you have the following installed:

- **Docker** (version 20.10+)
- **Docker Compose** (version 1.29+)
- **Python** 3.12+ (for local development)
- **Git**

## Quick Start

### Using Docker Compose

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd dnd-app-backend
   ```

2. **Start the application**
   ```bash
   docker compose up --build
   ```

3. **Access the application**
   - Open your browser and navigate to `http://localhost:8080`
   - Default DM credentials: `username: dm`, `password: pswd`

The application will automatically run database migrations on startup.

## Docker Commands

### Run Container Locally

Build and run the Docker image locally:

```bash
docker build -t dnd-app-manager:local .
docker run -p 8080:8080 \
  -e POSTGRES_HOST=host.docker.internal \
  -e POSTGRES_PORT=5432 \
  -e POSTGRES_DB=dnd_campaigns \
  -e POSTGRES_USER=dnd_user \
  -e POSTGRES_PASSWORD=your_password \
  -e SESSION_SECRET_KEY=your_secret_key \
  dnd-app-manager:local
```

Or use Docker Compose for a complete setup with PostgreSQL:

```bash
docker compose up --build
```

### Run Database Migrations

Migrations are automatically applied on container startup via the `start.sh` script. To manually run or check migrations:

```bash
# Check current migration status
docker exec -it dnd_app alembic current

# Create a new migration
docker exec -it dnd_app alembic revision --autogenerate -m "description"

# Upgrade to a specific migration
docker exec -it dnd_app alembic upgrade <revision>

# Downgrade to a specific migration
docker exec -it dnd_app alembic downgrade -1
```

### Build and Push to Docker Hub

Build multi-platform images and push to Docker Hub:

```bash
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    -t aglyzavr/dnd-app-manager:latest \
    --push \
    .
```

For a specific version tag:

```bash
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    -t aglyzavr/dnd-app-manager:v1.0.0 \
    --push \
    .
```

## Local Development

### Setup Python Environment

1. **Create a virtual environment**
   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application locally**
   ```bash
   python -m app.main
   ```

### Database Setup

Ensure PostgreSQL is running and accessible. Update the database connection settings in `app/config.py` or via environment variables.

## Configuration

### Environment Variables

Key environment variables for configuration:

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_PORT` | Application server port | `8080` |
| `APP_ENV` | Environment (development/production) | `development` |
| `POSTGRES_HOST` | PostgreSQL host | `localhost` |
| `POSTGRES_PORT` | PostgreSQL port | `5432` |
| `POSTGRES_DB` | Database name | `dnd_campaigns` |
| `POSTGRES_USER` | Database user | `dnd_user` |
| `POSTGRES_PASSWORD` | Database password | (required) |
| `SESSION_SECRET_KEY` | Secret key for session management | (required) |
| `SESSION_DURATION_DAYS` | Session validity period | `30` |
| `DM_SEED_USERNAME` | Default DM username | `dm` |
| `DM_SEED_PASSWORD` | Default DM password | `pswd` |

## Project Structure

```
dnd-app-backend/
├── app/
│   ├── handlers/          # API route handlers
│   ├── models/            # Database models
│   ├── repositories/      # Database access layer
│   ├── schemas/           # Pydantic schemas for validation
│   ├── services/          # Business logic
│   ├── middleware/        # Custom middleware
│   ├── locales/           # Internationalization files
│   ├── static/            # CSS, JS, images
│   ├── templates/         # HTML templates
│   ├── config.py          # Configuration settings
│   ├── database.py        # Database connection
│   ├── i18n.py            # i18n setup
│   └── main.py            # Application entry point
├── alembic/               # Database migrations
├── docker-compose.yml     # Docker Compose configuration
├── Dockerfile             # Docker image definition
├── requirements.txt       # Python dependencies
├── start.sh              # Container startup script
└── README.md             # This file
```

## Technologies

- **FastAPI** - Modern Python web framework
- **SQLAlchemy** - ORM for database operations
- **Alembic** - Database migration tool
- **PostgreSQL** - Relational database
- **Pydantic** - Data validation
- **Jinja2** - Template engine
- **Docker** - Containerization

## Contributing

1. Create a feature branch (`git checkout -b feature/amazing-feature`)
2. Commit your changes (`git commit -m 'Add amazing feature'`)
3. Push to the branch (`git push origin feature/amazing-feature`)
4. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues, questions, or suggestions, please open an issue in the repository.