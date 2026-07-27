from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, reviews
from app.core.config import settings
from app.db.database import Base, engine


Base.metadata.create_all(bind=engine)
app = FastAPI(title=settings.app_name, version="1.0.0", description="Human-reviewed contract and compliance intelligence. Not legal advice.")
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(health.router)
app.include_router(reviews.router)


@app.get("/")
def root():
    return {"application": settings.app_name, "docs": "/docs", "notice": "This tool assists reviewers and does not provide legal advice."}
