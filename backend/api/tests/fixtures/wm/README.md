# Recorded Wikimedia fixtures

These files are recorded HTTP responses from Wikipedia APIs, for the article
"**Jesus**" used by the wke-api test suite.

## Attribution

The article text, extracts and HTML in `parsoid.html`, `resolve.json`, `morelike.json`
and `search.json` are Wikipedia content, from the "**Jesus**" article:
* revision `1382808793`,
* retrieved `2026-10-30` (`META.json.recorded_at`).

All files and are licensed under the Creative Commons Attribution-ShareAlike
4.0 International License (CC BY-SA 4.0):
<https://creativecommons.org/licenses/by-sa/4.0/>.

Full authorship history for that revision is at
<https://en.wikipedia.org/w/index.php?title=Jesus&action=history>.
`mostread.json` and `pageviews_top.json` are Wikimedia pageview and featured-content
metadata, not article prose, but are recorded from the same source under the same terms.

## Files

- `META.json` - manifest: for each fixture, the source URL, HTTP status,
  byte size and (for `parsoid.html`) the requested and returned revision
  id; plus the recording timestamp and the User-Agent used to fetch them.
- `resolve.json` - Action API `action=query` response resolving the
  title "**Jesus**" to its page id, redirects, description, links and
  the revision timestamp (`prop=revisions&rvprop=timestamp`).
- `parsoid.html` - Parsoid HTML for revision `1382808793` via
  `/w/rest.php/v1/revision/{id}/html`, with every section
  kept; `content-revision-id` in `META.json` is the value of that
  response header, and must equal `requested_rev_id`.
- `revision.json` - Action API `action=query&revids=1382808793&prop=
  revisions&rvprop=timestamp`, same shape as the `revisions` block in
  `resolve.json`. Used as a fallback lookup for the revision timestamp.
- `morelike.json` - Action API `generator=search` with
  `gsrsearch=morelike:Jesus`, for related-article suggestions, each
  page's revision timestamp included (`prop=revisions&rvprop=timestamp`).
- `search.json` - Action API `generator=search` for the query "**Jesus**",
  the same request the topic search sends: 8 results, the spelling
  suggestion and each page's disambiguation flag.
- `mostread.json` - the `mostread` object of the Wikifeeds
  `feed/featured` response for 2026-09-27 (the feed reports each page's
  current revision and extract, so those change between recordings). The feed of day D carries the
  most-read list of day D-1, so this list is dated 2026-09-26. Used for
  the trending/most-read pipeline.
- `pageviews_top.json` - Pageviews API top-articles response for
  2026-09-26, used as the trending fallback source.
- `recentchange.sse` - the first 200 events of the Wikimedia EventStreams
  `recentchange` stream, recorded 2026-09-28, in SSE framing; used by the
  watcher tests. Not listed in `META.json`. Usernames are replaced by
  placeholders of the same kind (IP, temporary account, named), edit
  summaries by a fixed text, and title copies and log parameters removed.
- `record_sse.py` - the script that recorded `recentchange.sse`.
- `record.py` - the script that recorded every fixture above; run it to
  re-record them against live Wikipedia. **Idempotent:** rerunning
  overwrites all files and `META.json` with a fresh recording under the
  same fixed title and date constants defined within the script.
