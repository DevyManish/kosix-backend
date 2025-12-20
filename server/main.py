from fastapi import FastAPI, APIRouter
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(root_path="/api/v1")

api_router = APIRouter()

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "adk": {
            "status": "connected",
            "responseTimeMs": 2
        },
        "database": {
            "status": "connected",
            "responseTimeMs": 27
        },
        "timestamp": datetime.now().isoformat() + "Z",
        "responseTimeMs": 29
    }

app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("SERVER_HOST", "localhost")
    port = int(os.getenv("SERVER_PORT", "8080"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
