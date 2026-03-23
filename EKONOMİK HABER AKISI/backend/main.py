import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from news_fetcher import fetch_news
from analyzer import analyze_news, run_correlation_engine, get_top_news_analysis
from config import ANALYSTS, NEWS_SOURCES

app = FastAPI(title="Ekonomik Haber Akısı API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    title: str
    content: str


class ManualAnalyzeRequest(BaseModel):
    text: str


class CorrelationRequest(BaseModel):
    indicator: str
    direction: str
    portfolio: list[str] = []


@app.get("/api/news")
async def get_news(limit: int = 50):
    try:
        news = await fetch_news(limit)
        return {"success": True, "data": news, "count": len(news)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    try:
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise HTTPException(status_code=400, detail="ANTHROPIC_API_KEY ayarlanmamış")
        result = await analyze_news(req.title, req.content)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze/manual")
async def analyze_manual(req: ManualAnalyzeRequest):
    try:
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise HTTPException(status_code=400, detail="ANTHROPIC_API_KEY ayarlanmamış")
        lines = req.text.strip().split("\n")
        title = lines[0][:200] if lines else req.text[:200]
        content = req.text
        result = await analyze_news(title, content)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analysts")
async def get_analysts():
    return {"success": True, "data": ANALYSTS}


@app.get("/api/sources")
async def get_sources():
    return {"success": True, "data": NEWS_SOURCES}


@app.get("/api/health")
async def health():
    api_key_set = bool(os.getenv("ANTHROPIC_API_KEY"))
    return {
        "status": "ok",
        "api_key_configured": api_key_set
    }


@app.post("/api/correlation")
async def correlation(req: CorrelationRequest):
    try:
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise HTTPException(status_code=400, detail="ANTHROPIC_API_KEY ayarlanmamış")
        result = await run_correlation_engine(req.indicator, req.direction, req.portfolio)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/top-news")
async def get_top_news():
    try:
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise HTTPException(status_code=400, detail="ANTHROPIC_API_KEY ayarlanmamış")
        news = await fetch_news(20)
        if not news:
            raise HTTPException(status_code=404, detail="Haber bulunamadı")
        result = await get_top_news_analysis(news)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
