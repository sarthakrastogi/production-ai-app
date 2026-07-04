from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API keys
    JWT_SECRET: str = "change-me-in-prod"
    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_TRACING_V2: str = "true"
    PAGEINDEX_API_KEY: str = ""

    # Service URLs
    GPTCACHE_URL: str = "http://gptcache:8001"
    RIVAL_URL: str = "http://rival-service:8002"
    MONGODB_URI: str = "mongodb://mongodb:27017"
    POSTGRES_DSN: str = "postgresql://postgres:postgres@postgres:5432/support_bot"

    # Tuning
    MAX_INPUT_CHARS: int = 4000
    MAX_SESSION_TURNS: int = 10
    FAITHFULNESS_THRESHOLD: float = 0.7
    COMPLETENESS_THRESHOLD: float = 0.6

    # Model selection
    LOW_COMPLEXITY_MODEL: str = "gemini-3.5-flash"
    HIGH_COMPLEXITY_MODEL: str = "gemini-3.1-pro"  # swap to "gpt-4o" if preferred

    class Config:
        env_file = ".env"


settings = Settings()
