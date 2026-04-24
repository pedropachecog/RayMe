from fastapi import FastAPI

HEALTH_PAYLOAD = {
    "service": "rayme-ai-backend",
    "status": "ok",
    "phase": "01",
    "capabilities": ["health"],
}


def create_app() -> FastAPI:
    app = FastAPI(title="RayMe AI Backend", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, object]:
        return {**HEALTH_PAYLOAD, "capabilities": list(HEALTH_PAYLOAD["capabilities"])}

    return app
