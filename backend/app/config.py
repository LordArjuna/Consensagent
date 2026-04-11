from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Snowflake
    snowflake_account: str = ""
    snowflake_user: str = ""
    snowflake_password: str = ""
    snowflake_database: str = "US_CENSUS"
    snowflake_schema: str = "PUBLIC"
    snowflake_warehouse: str = "COMPUTE_WH"

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # Embeddings
    embedding_model_name: str = "all-MiniLM-L6-v2"

    # Pipeline
    max_retries: int = 3
    query_timeout_seconds: int = 30
    schema_retrieval_top_k: int = 5

    # App
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    log_level: str = "info"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
