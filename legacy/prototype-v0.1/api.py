from fastapi import FastAPI
from pydantic import BaseModel, Field
from ai_engine import SokokaliAI
from config import APP_NAME, APP_VERSION
from sports_engine import predict_match

app = FastAPI(title=APP_NAME, version=APP_VERSION)
bot = SokokaliAI()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class PredictionRequest(BaseModel):
    home_xg: float = Field(ge=0, le=10)
    away_xg: float = Field(ge=0, le=10)


@app.get("/health")
def health():
    return {"status": "ok", "service": APP_NAME}


@app.post("/chat")
def chat(request: ChatRequest):
    return {"reply": bot.respond(request.message)}


@app.post("/predict-demo")
def prediction(request: PredictionRequest):
    result = predict_match(request.home_xg, request.away_xg)
    return {"demo_only": True, "home_win": result.home_win, "draw": result.draw, "away_win": result.away_win}
