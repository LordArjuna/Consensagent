import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import get_settings
from app.services.snowflake import SnowflakeService
from app.services.llm import LLMService
from app.services.embeddings import EmbeddingService
from app.pipeline.schema_cache import SchemaCache
from app.pipeline.conversation import ConversationManager
from app.pipeline import orchestrator

logger = logging.getLogger(__name__)

snowflake_service = SnowflakeService()
llm_service = LLMService()
embedding_service = EmbeddingService()
schema_cache = SchemaCache()
conversation_manager = ConversationManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    logging.basicConfig(level=settings.log_level.upper())

    snowflake_service.connect(settings)
    llm_service.configure(settings)
    embedding_service.load(settings)

    schema_cache.build(snowflake_service, embedding_service)

    yield

    snowflake_service.close()


app = FastAPI(title="Census Chat API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    response: str
    session_id: str
    sql_query: Optional[str] = None
    tables_used: List[str] = []


@app.get("/health")
def health_check():
    sf_ok = snowflake_service.test_connection()
    llm_ok = llm_service.test_connection()
    emb_ok = embedding_service.test_connection()

    status = "healthy" if all([sf_ok, llm_ok, emb_ok]) else "degraded"

    return {
        "status": status,
        "snowflake": "connected" if sf_ok else "disconnected",
        "gemini": "connected" if llm_ok else "disconnected",
        "embeddings": "loaded" if emb_ok else "not loaded",
        "schema_tables": len(schema_cache.get_all_tables()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    settings = get_settings()

    try:
        result = orchestrator.run(
            message=request.message,
            session_id=request.session_id,
            schema_cache=schema_cache,
            conversation_manager=conversation_manager,
            llm_service=llm_service,
            embedding_service=embedding_service,
            snowflake_service=snowflake_service,
            database=settings.snowflake_database,
            schema=settings.snowflake_schema,
        )
    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Pipeline error: {e}")

    return ChatResponse(
        response=result.response,
        session_id=request.session_id,
        sql_query=result.sql_query,
        tables_used=result.tables_used,
    )


@app.post("/clear-session")
def clear_session(session_id: str = "default"):
    conversation_manager.clear(session_id)
    return {"status": "cleared", "session_id": session_id}
