from fastapi import FastAPI

app = FastAPI(title="ProjectGen API")

@app.get("/health")
def health():
    return {"status":"ok"}
