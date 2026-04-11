# Census Chat

An interactive chat agent that answers natural language questions about the US population, grounded in US Census data from Snowflake.

## Architecture

```
Streamlit (frontend) → FastAPI (backend) → Gemini LLM + Snowflake + Local Embeddings
```

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Snowflake trial account with US Census Marketplace dataset
- Google Gemini API key (free tier)

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env with your Snowflake and Gemini credentials
```

### 2. Run with Docker Compose

```bash
docker-compose up --build
```

- **Frontend**: http://localhost:8501
- **Backend API**: http://localhost:8000
- **Health check**: http://localhost:8000/health

### 3. Run locally (development)

Backend:
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit with your credentials
uvicorn app.main:app --reload --port 8000
```

Frontend:
```bash
cd frontend
pip install -r requirements.txt
BACKEND_URL=http://localhost:8000 streamlit run app.py
```

### 4. Run tests

```bash
cd backend
pytest tests/ -v
```

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI routes
│   │   ├── config.py          # Environment settings
│   │   ├── services/          # Snowflake, LLM, Embeddings
│   │   └── pipeline/          # Agentic text-to-SQL pipeline
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app.py                 # Streamlit chat UI
│   ├── requirements.txt
│   └── Dockerfile
├── docker-compose.yml
└── .env.example
```
