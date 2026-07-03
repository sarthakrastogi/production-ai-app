from pydantic_settings import BaseSettings


class EvalSettings(BaseSettings):
    APP_URL: str = "http://localhost:8000"
    JWT_SECRET: str = "change-me-in-prod"
    EVAL_TIMEOUT_MS: int = 30000
    FAITHFULNESS_THRESHOLD: float = 0.7
    COMPLETENESS_THRESHOLD: float = 0.6
    LATENCY_REGRESSION_THRESHOLD: float = 0.2  # 20% regression allowed
    COST_REGRESSION_THRESHOLD: float = 0.3  # 30% cost increase allowed
    BASELINE_FILE: str = "evals/baselines/latest.json"
    DATASET_FILE: str = "evals/datasets/golden.json"

    class Config:
        env_prefix = "EVAL_"
        env_file = ".env"


eval_settings = EvalSettings()
