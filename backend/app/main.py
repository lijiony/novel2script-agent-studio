from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.runs import router as runs_router
from app.api.schema import router as schema_router


app = FastAPI(
    title="Novel2Script Agent Studio API",
    version="0.1.0",
    description="Stateless AI novel-to-script backend.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs_router)
app.include_router(schema_router)


@app.get("/health")
def health():
    return {"ok": True}
