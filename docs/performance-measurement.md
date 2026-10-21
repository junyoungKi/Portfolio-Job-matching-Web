# Measuring query cost, /match stages, and the HNSW index

This page is how to check three things on a machine you control:

1. How many SQL statements `/match` and one crawler city issue, and what share of the request that database time is.
2. Which part of `/match` takes the time: Redis, the vector search, the rerank call, the analysis calls, the analysis write.
3. Whether `ix_job_postings_embedding_hnsw` is actually used, and what recall the approximate search has against an exact scan.

No results are filled in here. The log lines and tables below are the shape of the output, not a measurement.

The owner checklist (what to measure, how to read it, and an empty result column) is [measurement-checklist.md](measurement-checklist.md). This page is the command reference that checklist points at.

The baseline is current `origin/main`:

```text
529e2a1bd866d60c772e8e2e9ac3182388318d94
```

Check it with `git rev-parse HEAD` on a checkout of `main`. The fixed commit is this branch. Compare those two checkouts on the same machine, the same database size, and the same request. Do not compare a cold `/match` with a Redis hit.

`QUERY_STATS` and `MATCH_TIMING` exist only on this branch. They are off unless you set them. The baseline has neither, so the comparison that works on both checkouts is `pg_stat_statements` (section 1) and `curl -w` for wall time (section 2). `EXPLAIN` works on both; the SQL text is different, and that difference is the point of section 3.

## 1. Statements per request, and DB time share

### On this branch: `QUERY_STATS=1`

Start the server with the counter on. Leave it off in production; the cursor hooks are not registered unless the variable is set.

```bash
QUERY_STATS=1 uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Each request logs one line when it finishes:

```text
[QUERY_STATS] GET /match/15 statements=<N> db_ms=<ms> wall_ms=<ms> db_share=<0-1>
```

| Field | Meaning |
|---|---|
| `statements` | Cursor executions during that request. This is "queries per request". |
| `db_ms` | Time spent inside those executions. |
| `wall_ms` | Time from the start of the request to the response. |
| `db_share` | `db_ms / wall_ms`. The rest of the wall time is Redis, OpenAI, and Python. |

A crawler city logs the same shape, with `CRAWL` instead of the HTTP method, plus `inserted=<n>`:

```text
[QUERY_STATS] CRAWL Software Engineer statements=<N> db_ms=<ms> wall_ms=<ms> db_share=<0-1> inserted=<n>
```

To count a city without LinkedIn and without an OpenAI key, this branch has `scripts/crawl_query_stats.py`. It stubs the metadata and embedding calls, inserts five fake postings, prints the log line, then deletes those rows.

```bash
QUERY_STATS=1 DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5432/job_match \
  python scripts/crawl_query_stats.py
```

What the code does, so you know what `<N>` should be near:

| Path | Baseline `529e2a1` | This branch |
|---|---|---|
| `/match`, cold, 10 jobs missing analyses | 1 resume select + 1 vector select + 10 analysis selects + 10 commits | 1 resume select + 1 `SET LOCAL` (+ a second `SET LOCAL` when pgvector is >= 0.8) + 1 vector select + 1 analysis `IN (...)` select + 1 insert commit. Two extra commits only return the connection to the pool before the OpenAI calls. |
| `/match`, analyses already stored | the same 10 selects, and no analysis inserts | the same selects as above, and no insert |
| one crawler city of K new jobs | K duplicate selects + K commits | 1 duplicate select for the whole city + 1 insert commit |

`SET LOCAL` and `COMMIT` show up in `statements` because they go through the cursor. Subtract them if you want only `SELECT`/`INSERT`.

### On both checkouts: `pg_stat_statements`

Use this on the baseline as well, so the counting method is the same. It needs the extension, which is in `postgresql-contrib`.

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
SELECT pg_stat_statements_reset();
```

Send exactly one request (or run the crawl script once), then:

```sql
SELECT calls,
       round(total_exec_time::numeric, 2) AS total_ms,
       round(mean_exec_time::numeric, 2)  AS mean_ms,
       left(query, 180) AS query
FROM pg_stat_statements
WHERE query ILIKE '%job_postings%'
   OR query ILIKE '%match_analyses%'
ORDER BY total_exec_time DESC;
```

Queries per request is the sum of `calls` since the reset, for that one request. DB time share is `sum(total_ms) / (curl time_total in ms)` from section 2. Reset again before the next request, or the calls accumulate.

`pg_stat_statements` records the statement text after parameters are stripped, so the per-job analysis select on the baseline shows up as one query string with `calls` equal to the number of jobs. On this branch that string should have `calls = 1` and an `IN (...)`.

## 2. Which stage of /match is slow

`MATCH_TIMING=1` logs the stages and adds a `Server-Timing` header. Off by default. Baseline does not have it; on the baseline, `curl -w` gives you only the total.

```bash
MATCH_TIMING=1 QUERY_STATS=1 uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
curl -sD - -o /dev/null -w 'wall %{time_total}s\n' \
  'http://127.0.0.1:8000/match/RESUME_ID'
```

Header and log, same numbers:

```text
server-timing: redis;dur=<ms>, vector;dur=<ms>, rerank;dur=<ms>, analysis;dur=<ms>, db_write;dur=<ms>

[MATCH_TIMING] resume_id=RESUME_ID redis;dur=<ms>, vector;dur=<ms>, rerank;dur=<ms>, analysis;dur=<ms>, db_write;dur=<ms>
```

| Stage | What it includes |
|---|---|
| `redis` | The cache `GET`. A hit stops here. |
| `vector` | Load the resume row, `SET LOCAL` for the HNSW scan, and the nearest-neighbour query. |
| `rerank` | One `gpt-4o-mini` chat call over the candidates. |
| `analysis` | The KO and EN chat calls for jobs that do not already have a stored analysis. Absent when every top job is already stored. They run together, at most 8 at a time. |
| `db_write` | The single `IN (...)` lookup of stored analyses, plus the insert commit when any were missing. |

Repeat the same URL. The second response should be a Redis hit: only `redis`, and a much smaller `curl` total. That is the cached path. The first call is the cold path. Do not average them together.

### Real OpenAI, small on purpose

There is no stub server in this branch. A cold `/match` after a new upload is:

- 1 embedding call (`text-embedding-3-small`) on `POST /process-resume`
- 1 rerank call plus up to 20 analysis calls (`gpt-4o-mini`, 10 jobs × Korean and English) on the first `/match`

That is the whole sample you need for the stage split. Check the current prices before you run it, and expect the account's per-minute limits to dominate if you loop. One resume, one cold `/match`, one repeat of that same URL is enough. Use a resume id that already exists if you only want the `/match` stages and already paid for the embedding.

```bash
curl -s -F 'file=@sample_resume.pdf' \
  'http://127.0.0.1:8000/process-resume?location=Seattle,%20WA'
# then the curl -D - above with the returned id
```

Wall time on the baseline, for the same resume id and the same filters, is the same `curl -w` command. The baseline does the analysis calls one after another; this branch runs them together. The stage header that shows that split exists only on this branch.

## 3. Is the HNSW index used?

### What the code does

`vector_cosine_ops` indexes the `<=>` operator. pgvector can use `ix_job_postings_embedding_hnsw` when `ORDER BY` is that operator applied to the column and a bound parameter, with a `LIMIT`.

On the baseline the query orders by a labeled `1 - (embedding <=> :vec)`. That expression is not the operator, so the index is not eligible.

This branch loads the resume embedding in its own statement and binds it as a parameter. The search statement is:

```sql
SELECT ..., 1 - (job_postings.embedding <=> $1) AS score
FROM job_postings
WHERE company != 'USER_UPLOAD'
  AND location IN (...)
  -- plus experience_level IN, employment_type IN, skills ILIKE when those filters are set
ORDER BY job_postings.embedding <=> $1
LIMIT 100
```

The selected score is still `1 - distance` (cosine similarity). The JSON keys and the `match_score` rounding are unchanged. Which rows come back can differ, because an HNSW scan is approximate and because filters interact with the index (below).

`create_all` does not add an index to a table that already exists. Startup runs:

```sql
CREATE INDEX IF NOT EXISTS ix_job_postings_embedding_hnsw
ON job_postings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

If the index is already there, this does nothing. It will not rebuild an index of the same name that was created with different options.

### Filters, `ef_search`, iterative scan

An HNSW scan returns neighbours in distance order, then the `WHERE` filters throw some of them away. Two settings decide whether you still get 100 rows:

- `hnsw.ef_search` defaults to 40. A non-iterative scan cannot return 100 neighbours when the search list is 40. For the `/match` transaction only, this branch runs `SET LOCAL hnsw.ef_search = 100`. The server default is unchanged afterwards. `SHOW hnsw.ef_search` outside that transaction still shows the default.
- pgvector 0.8 adds `hnsw.iterative_scan`. When the extension version is at least 0.8, the same transaction sets `hnsw.iterative_scan = strict_order`, which keeps walking the index, in order, until `LIMIT` rows survive the filters. On older pgvector that setting does not exist. Filters then apply to a single pass, and a selective `location` / level / type / `skills ILIKE` can return fewer than 100 rows. Raising `ef_search` above 100 reduces that, at the cost of a wider search; this branch does not raise it past 100 on old versions.

`strict_order` preserves distance order. It can do more index work when the filter rejects most neighbours. That is the tradeoff: correct order and a full `LIMIT` when the extension supports it, versus a possible short candidate list on older pgvector.

### Commands

```sql
SHOW hnsw.ef_search;
SELECT extversion FROM pg_extension WHERE extname = 'vector';
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'job_postings';
```

`indexdef` for `ix_job_postings_embedding_hnsw` should mention `hnsw` and `vector_cosine_ops`. If the row is missing, restart the app once so the `CREATE INDEX IF NOT EXISTS` runs, or run that statement yourself.

Take the embedding from a real resume row and paste it as a literal. A subquery in `ORDER BY` is not the statement the app sends, and it is a poor test of the index.

```sql
SELECT embedding FROM job_postings WHERE id = :resume_id;
```

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id,
       1 - (embedding <=> '[...]'::vector) AS score
FROM job_postings
WHERE company <> 'USER_UPLOAD'
  AND location IN (
    'Vancouver, BC', 'Toronto, ON', 'Seattle, WA', 'San Francisco, CA',
    'Austin, TX', 'New York, NY', 'Los Angeles, CA', 'Montreal, QC'
  )
ORDER BY embedding <=> '[...]'::vector
LIMIT 100;
```

Set the same session knobs the request uses before `EXPLAIN`, or you are not explaining the request:

```sql
SET hnsw.ef_search = 100;
-- only if extversion >= 0.8; otherwise this errors
SET hnsw.iterative_scan = strict_order;
```

How to read the plan:

| What you see | What it means |
|---|---|
| `Index Scan using ix_job_postings_embedding_hnsw` | The index was used. |
| `Seq Scan on job_postings` with a `Sort` | The index was not used. On a small table this is normal: the planner prefers a sequential scan. It does not by itself mean the query is ineligible. |
| `Rows Removed by Filter` under the index scan | Post-filtering. If the scan returns far fewer than 100 rows, the filter is throwing away neighbours. On pgvector >= 0.8, `strict_order` is what avoids that. |
| `Execution Time` | The number to compare. Ignore `Planning Time` for the comparison. |

To see whether the index *can* be used on a small table, run the same `EXPLAIN` after `SET enable_seqscan = off`. That plan is a capability check, not a timing result. Turn `enable_seqscan` back on (`SET enable_seqscan = on`) before any timing comparison, and use a table large enough that the planner chooses for itself.

Index on/off timing, sequential scan allowed both times:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM job_postings
WHERE company <> 'USER_UPLOAD'
ORDER BY embedding <=> '[...]'::vector
LIMIT 100;

BEGIN;
DROP INDEX IF EXISTS ix_job_postings_embedding_hnsw;
EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM job_postings
WHERE company <> 'USER_UPLOAD'
ORDER BY embedding <=> '[...]'::vector
LIMIT 100;
ROLLBACK;   -- puts the index back. Do not COMMIT this.
```

`ROLLBACK` restores the index only if `DROP INDEX` was inside the same transaction. Do not run `DROP INDEX` outside that `BEGIN`.

### Recall

Recall here is the overlap of the approximate top-k with the exact top-k. Run the index plan and the exact plan in two sessions (the second disables index scans), then count the overlap. k is 10 below; use 100 if you want the full candidate list.

```sql
-- Session A: approximate (index allowed)
SET hnsw.ef_search = 100;
CREATE TEMP TABLE ann_ids AS
SELECT id FROM job_postings
WHERE company <> 'USER_UPLOAD'
ORDER BY embedding <=> '[...]'::vector
LIMIT 10;
```

```sql
-- Session B: exact
SET enable_indexscan = off;
SET enable_bitmapscan = off;
CREATE TEMP TABLE exact_ids AS
SELECT id FROM job_postings
WHERE company <> 'USER_UPLOAD'
ORDER BY embedding <=> '[...]'::vector
LIMIT 10;
```

Temp tables are per session, so copy the ids out (or run both as `SELECT id` and diff them in a script). With both id lists in one session:

```sql
SELECT count(*) AS overlap
FROM exact_ids
JOIN ann_ids USING (id);
-- recall = overlap / 10
```

State that fraction next to `ef_search` and the pgvector version. A higher `ef_search` usually raises recall and the scan time together. This repository does not ship a recall number.

## Cache hits, and the resume text hash

`/match` caches under `match_results:{resume_id}:{md5 of the filter lists}` for one hour. Re-uploading the same parsed text and the same location, while that row still exists, returns the existing id (`search_keyword` is `md5(text + location)`), so the next `/match` uses the same Redis key. A text-hash cache key is not required for that case. It still misses when the filters change, when the location string changes (that is a different row and a different search), and when the row has been deleted after its one-hour lifetime while you are matching a new id. Those are reasons a repeat can look like a cold request. Section 2's second `curl` of the same URL is the hit; a re-upload is not automatically one.
