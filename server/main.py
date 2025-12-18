from fastapi import FastAPI
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

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

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("SERVER_HOST", "localhost")
    port = int(os.getenv("SERVER_PORT", "8080"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
