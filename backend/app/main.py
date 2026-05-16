from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.bootstrap_import import ensure_part_of_speech_entries, run_startup_import
from app.database import SessionLocal, init_db
from app.routes_entries import router as entries_router
from app.schemas import HealthDto

app = FastAPI(title="Ginger dictionary")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    logging.basicConfig(level=logging.INFO)
    init_db()
    sess = SessionLocal()
    try:
        n_pos = ensure_part_of_speech_entries(sess)
        if n_pos:
            logging.getLogger("app.bootstrap_import").info("Inserted %s POS lemmas as dictionary rows", n_pos)
    finally:
        sess.close()
    run_startup_import()


@app.get("/api/health", response_model=HealthDto)
def health():
    return HealthDto(ok=True)


app.include_router(entries_router)
