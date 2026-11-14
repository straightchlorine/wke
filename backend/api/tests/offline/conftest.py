"""Fixtures local to tests/offline/: a synchronous fake Redis and a stored dossier."""

from __future__ import annotations

import fakeredis
import pytest

from tests.factories.dossier import make_fixture_dossier
from tests.support.offline import store_dossier
from wke.core.models import Dossier


@pytest.fixture
def client() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def stored(client: fakeredis.FakeRedis) -> Dossier:
    dossier = make_fixture_dossier()
    store_dossier(client, dossier)
    return dossier
