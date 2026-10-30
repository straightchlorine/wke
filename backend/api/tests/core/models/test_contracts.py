"""Model rules the API contract depends on: link names, dossier ids, hidden request ids."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.factories.dossier import make_fixture_dossier
from tests.support.jobs import make_job
from wke.core.models import Dossier, DossierLinks

LINKS = {
    "self": "https://wke.example/api/v1/dossiers/1",
    "pinned": "https://wke.example/api/v1/dossiers/1/rev/2",
    "markdown": "https://wke.example/api/v1/dossiers/1.md",
    "wikipedia": "https://en.wikipedia.org/wiki/Example",
}


def test_dossier_links_serialise_as_self() -> None:
    links = DossierLinks.model_validate(LINKS)
    # FastAPI serialises responses by alias: the JSON key is "self", never "self_".
    assert links.model_dump(mode="json", by_alias=True) == LINKS


def test_dossier_links_accept_the_python_name_too() -> None:
    by_name = {"self_" if key == "self" else key: value for key, value in LINKS.items()}
    assert DossierLinks.model_validate(by_name) == DossierLinks.model_validate(LINKS)


@pytest.mark.parametrize("dossier_id", ["1@2:0123456789ab", "1095706@1382808793:abcdef012345"])
def test_dossier_id_of_page_revision_and_build_hash_is_accepted(dossier_id: str) -> None:
    payload = make_fixture_dossier().model_dump() | {"id": dossier_id}
    assert Dossier.model_validate(payload).id == dossier_id


@pytest.mark.parametrize(
    "dossier_id",
    [
        "1@2:0123456789AB",  # upper-case hash
        "1@2:0123456789a",  # hash one digit short
        "1:2:0123456789ab",  # no "@" between page and revision
        "Jesus@2:0123456789ab",  # title instead of page id
        "1@2:0123456789ab ",  # trailing space
    ],
)
def test_malformed_dossier_id_is_rejected(dossier_id: str) -> None:
    payload = make_fixture_dossier().model_dump() | {"id": dossier_id}
    with pytest.raises(ValidationError):
        Dossier.model_validate(payload)


def test_job_request_id_is_kept_but_never_serialised() -> None:
    job = make_job(request_id="req-12345678")
    assert job.request_id == "req-12345678"
    assert "request_id" not in job.model_dump(mode="json")
    assert "request_id" not in job.model_dump_json()
