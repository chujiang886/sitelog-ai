"""Development CORS policy for the BOIP web application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


DEVELOPMENT_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8000",
)


def register_cors(app: FastAPI, origins: tuple[str, ...] = DEVELOPMENT_ORIGINS) -> None:
    """Allow browser requests from supported local development ports."""

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
