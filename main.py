# main.py

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import router

app = FastAPI(
    title="Restaurant Scraper API",
    description="Scrapes Swiggy for restaurant menu data and infers business attributes",
    version="1.0.0",
)

# CORS — allow your Lovable frontend (and localhost for testing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to your Lovable URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
def health_check():
    return {"status": "ok", "message": "Restaurant Scraper API is running"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
