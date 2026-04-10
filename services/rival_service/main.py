"""
Rival AI attack detection microservice.

Runs as a standalone FastAPI app. Loads BhairavaAttackDetector once at
startup via lifespan, then serves fast inference requests.

Deploy this separately from the main app — it needs its own memory budget
(~1.5–2GB for the model) and should be independently scalable.
"""
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from rival_ai.detectors import BhairavaAttackDetector

_detector: BhairavaAttackDetector | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _detector
    _detector = BhairavaAttackDetector.from_pretrained()
    print("Bhairava-0.4B loaded and ready")
    yield
    _detector = None


app = FastAPI(title="Rival Attack Detection Service", lifespan=lifespan)


class DetectRequest(BaseModel):
    query: str


class DetectResponse(BaseModel):
    is_attack: bool
    confidence: float


@app.post("/detect", response_model=DetectResponse)
async def detect(req: DetectRequest):
    if _detector is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    result = _detector.detect_attack(req.query)
    return DetectResponse(
        is_attack=bool(result["is_attack"]),
        confidence=float(result["confidence"]),
    )


@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": _detector is not None}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
