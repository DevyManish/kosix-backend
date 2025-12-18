from fastapi import FastAPI
from datetime import datetime

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
    uvicorn.run(app, host="0.0.0.0", port=8000)
