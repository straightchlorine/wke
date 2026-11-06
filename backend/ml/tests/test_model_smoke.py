"""Real-model smoke test against the pinned torch backend."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from wke_ml.main import create_app
from wke_ml.settings import Settings


@pytest.mark.model
async def test_real_backend_summarize_and_analyze() -> None:
    settings = Settings(backend="torch")
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        import torch

        assert app.state.summarizer._model.dtype == torch.float32

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            summarize_response = await client.post(
                "/v1/summarize",
                json={
                    "text": (
                        "Alan Turing was a British mathematician and computer scientist. "
                        "He is widely considered the father of theoretical computer science."
                    )
                    * 3,
                },
            )
            assert summarize_response.status_code == 200
            summary = summarize_response.json()
            assert summary["model_revision"] == settings.summarize_model_revision
            assert summary["truncated"] is False
            assert summary["text"].endswith((".", "!", "?", '"'))

            analyze_response = await client.post(
                "/v1/analyze",
                json={
                    "lead": "Alan Turing was a mathematician and computer scientist.",
                    "chunks": [
                        {"id": "c1", "text": "Turing worked on the Enigma codebreaking effort."},
                        {
                            "id": "c2",
                            "text": "He formalized the concept of algorithm and computation.",
                        },
                    ],
                },
            )
            assert analyze_response.status_code == 200
            assert analyze_response.json()["model_revision"] == settings.embed_model_revision
