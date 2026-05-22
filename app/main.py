from fastapi import FastAPI

app = FastAPI(title="RTFM For Me")


@app.get("/health")
async def health():
    return {"status": "ok"}
