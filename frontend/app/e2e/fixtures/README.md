# Fixtures

Recorded API responses and Wikimedia data for the unit tests
(`src/test/fixtures.ts`) and for Playwright (`e2e/mockApi.ts`, which serves
them under the wke-api routes). Nothing here is invented text. Article
titles are written in ASCII ("Godel's incompleteness theorems" stands for
the article whose title has an o with an umlaut).

## Dossier builds: dossier_<page_id>_<budget>.json, dossier_<page_id>_md.json

Real dossier builds of seven articles, recorded on 2026-11-12 from the
local stack (wke-api, wke-ml and Redis, pipeline version
`fixtures-2026-11-12`, real Wikimedia calls, real MiniLM clustering, real
distilbart-cnn-6-6 summaries). `dossier_<page_id>_<budget>.json`
(budget 2000, 8000 or 32000) is the flat `DossierView` that
`GET /api/v1/dossiers/{page_id}?budget=<budget>` returns once its parts are
merged, summaries included. `dossier_<page_id>_md.json` is
`{"markdown": ...}` with the body of `GET /api/v1/dossiers/{page_id}.md`
at budget 8000. `mockApi.ts` nests the flat builds into the schema-2
response the API serves; `src/test/fixtures.ts` loads them flat.

| Article | Page id | Revision |
| --- | --- | --- |
| Jesus (the main topic) | 1095706 | 1385149975 |
| Lizzie Borden | 214796 | 1384380651 |
| Godel's incompleteness theorems | 58863 | 1382685320 |
| Mercury (planet) | 19694 | 1384573767 |
| Apollo 11 | 662 | 1384203118 |
| API | 27697009 | 1384555837 |
| Kamchatka Peninsula | 678671 | 1378316402 |

Used by the unit tests `src/api/dossier.test.ts`,
`src/lib/dossierPack.test.ts`, `src/lib/seo.test.ts`,
`src/lib/lede.test.ts` and `src/lib/proseSections.test.ts` (Jesus at
budgets 8000 and 2000), and by every Playwright spec that opens a
dossier.

## job_queued.json, job_done.json, job_running_partial.json

Real `Job` bodies recorded on 2026-11-12 from the same local stack.
`job_queued.json` is the 202 answer of `POST /api/v1/dossiers` for Jesus
and `job_done.json` is the same job once finished. `job_running_partial.json`
is a poll of an Apollo 11 build that is still running with a partial
build available. `mockApi.ts` answers a build request with the queued job,
polls of that job with the done one, and polls of the Apollo 11 job with
the running one. Used by `src/api/dossier.test.ts` and the build specs.

## search_*.json

Answers of `GET /api/v1/search`, recorded on 2026-11-12 from the local
stack: `search_jesus`, `search_lizzie` ("Lizzie Borden"), `search_godel`
("Godel" with an umlaut), `search_mercury`, `search_apollo`, `search_api`
and `search_kamchatka` ("Kamchatka", which resolves to Kamchatka
Peninsula). `mockApi.ts` picks one by the query and falls back to the
Jesus answer. Used by the search and suggestion specs.

## disambiguation_mercury.json

The 409 `application/problem+json` body of `POST /api/v1/dossiers` with
`{"title": "Mercury"}`, recorded on 2026-11-12 from the local stack. It
lists 7 candidates; `mockApi.ts` serves it for that request. Used by the
specs of the "did you mean" panel.

## dossiers_api.json

The answer of `GET /api/v1/dossiers?q=api&limit=20`, recorded on
2026-11-12 from the local stack. Served by `mockApi.ts` when the title
filter starts with "api". Used by the dossier index and suggestion specs.

## trending.json

Built by `make_trending.py` from `backend/api/tests/fixtures/wm/mostread.json`,
a recording of the featured-feed "most read" endpoint dated 2026-09-26.
The script's title filter, top-40 cut and edge rules are described in its
docstring. The edges come from MiniLM embeddings
(`sentence-transformers/all-MiniLM-L6-v2`, revision `1110a243`) run
locally on 2026-09-28. `dossier_state` is set by the script, not
recorded: the first 30 topics are `ready`, the other 10 rotate through
`partial`, `building` and `none`. Used by the home page specs,
`src/lib/graphLayout.test.ts` and `src/lib/labelLayout.test.ts`.

## trending-top-right-group.json

The topic ids, titles, view counts and 18 edges of a real
`GET /api/v1/trending` response from the local API on 2026-09-28, copied
unchanged. Its Lizzie Borden group lands under the corner chip of the
home graph, which is the regression case for flat groups. Used only by
`src/lib/graphLayout.test.ts`.

## live.json

Built by `make_live.py` from `backend/api/tests/fixtures/wm/recentchange.sse`,
a recording of `stream.wikimedia.org/v2/stream/recentchange`. The
recording has 4 events that pass the script's filter (of 200 total); all 4
are kept. `page_id` is null on every event because none of them lands on
a trending topic. Used by the home page specs and `src/lib/hooks/useLive.test.ts`
through `mockApi.ts`.

## dossiers.json

Built by `make_dossiers.py` from the 30 `ready` topics of
`trending.json`, so `page_id`, `title` and `rev_id` are real. The other
fields are made up and varied so the dossiers index shows a mix of
budgets, freshness states and edit counts. Used by the dossier index
specs.

## Attribution

Article text, titles, summaries' source passages and revision data come
from English Wikipedia and are licensed CC BY-SA 4.0. Each build pins one
revision of its article (history pages):

- Jesus, page 1095706, revision 1385149975:
  https://en.wikipedia.org/w/index.php?title=Jesus&action=history
- Lizzie Borden, page 214796, revision 1384380651:
  https://en.wikipedia.org/w/index.php?title=Lizzie_Borden&action=history
- Godel's incompleteness theorems, page 58863, revision 1382685320:
  https://en.wikipedia.org/w/index.php?title=G%C3%B6del%27s_incompleteness_theorems&action=history
- Mercury (planet), page 19694, revision 1384573767:
  https://en.wikipedia.org/w/index.php?title=Mercury_(planet)&action=history
- Apollo 11, page 662, revision 1384203118:
  https://en.wikipedia.org/w/index.php?title=Apollo_11&action=history
- API, page 27697009, revision 1384555837:
  https://en.wikipedia.org/w/index.php?title=API&action=history
- Kamchatka Peninsula, page 678671, revision 1378316402:
  https://en.wikipedia.org/w/index.php?title=Kamchatka_Peninsula&action=history

The most-read counts and lead excerpts in `trending.json`, and the edit
events in `live.json`, are Wikimedia data under the same terms.
