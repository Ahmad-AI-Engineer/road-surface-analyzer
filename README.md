# Road Surface Conditions Analyzer

Upload a road video, get it back with potholes, cracks and alligator cracking boxed —
powered by the **Roboflow Hosted Inference API**. No local model, no GPU, no training,
no message broker.

```
React 3D UI → FastAPI → OpenCV frame extraction → Roboflow Inference API
           → detections → bounding boxes → ffmpeg H.264 output → 3D dashboard
```

---

## Quickstart

```bash
cp .env.example .env          # 1. add your ROBOFLOW_API_KEY
docker compose up --build     # 2. build and run
# 3. open http://localhost:3007
```

No API key handy? Run the whole demo offline with deterministic fake boxes:

```bash
MOCK_DETECTOR=1 docker compose up --build
```

### Ports

| Port | Service | Purpose |
|------|---------|---------|
| 8007 | `backend` | FastAPI REST API (`/health`, `/api/v1/...`, `/docs`) |
| 3007 | `frontend` | React SPA served by nginx |
| 3006 | `media` | Processed videos + thumbnails (range requests enabled) |

---

## Getting a Roboflow API key

1. Sign in at <https://app.roboflow.com>.
2. **Settings → API Keys** → copy your private key.
3. Put it in `.env`:

   ```env
   ROBOFLOW_API_KEY=your_key_here
   MODEL_ID=road-damage-medium-9semt/1
   ```

`MODEL_ID` is `{project}/{version}` of any Roboflow object-detection model. The default
detects **pothole**, **crack** and **alligator cracking**.

---

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `ROBOFLOW_API_KEY` | — | Required unless `MOCK_DETECTOR=1` |
| `MODEL_ID` | `road-damage-medium-9semt/1` | Hosted model + version |
| `CONF_THRESHOLD` | `0.35` | Minimum confidence kept from the API response |
| `FRAME_STRIDE` | `5` | Send every Nth frame to Roboflow |
| `MAX_UPLOAD_MB` | `200` | Upload size cap |
| `MOCK_DETECTOR` | `0` | `1` = deterministic fake boxes, fully offline |
| `INFERENCE_WIDTH` | `640` | Frames are downscaled to this width before upload |

### Tuning `FRAME_STRIDE`

Only sampled frames are sent to Roboflow; boxes from the last analyzed frame are reused on
the frames in between, so the overlay stays continuous.

| Stride | API calls (20 s @ 25 fps) | Trade-off |
|---|---|---|
| `2` | ~250 | Smoothest boxes, 2.5× the quota and time |
| `5` (default) | ~100 | Good balance for a demo |
| `10` | ~50 | Fastest, boxes visibly lag fast motion |

Processing time is dominated by Roboflow round-trips, not local CPU.

---

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Config + readiness |
| `POST` | `/api/v1/jobs` | Multipart upload → `202 {job_id}` |
| `GET` | `/api/v1/jobs` | Job history |
| `GET` | `/api/v1/jobs/{id}` | Status, progress, ETA, summary (polled ~1 Hz) |
| `DELETE` | `/api/v1/jobs/{id}` | Remove a job and its media |
| `GET` | `/api/v1/jobs/{id}/detections` | Paginated; `?format=csv\|json` |
| `GET` | `/api/v1/jobs/{id}/timeline` | Detections bucketed over time |
| `GET` | `/api/v1/stats` | Aggregates + Roboflow call count / avg latency |

Interactive docs: <http://localhost:8007/docs>

```bash
# upload and poll from the shell
JOB=$(curl -s -F "file=@samples/road_demo.mp4" localhost:8007/api/v1/jobs | jq -r .job_id)
watch -n1 "curl -s localhost:8007/api/v1/jobs/$JOB | jq '{status,progress,api_calls}'"
```

---

## Demo data

```bash
# 20s synthetic road clip
docker compose exec backend python /scripts/make_sample.py /samples/road_demo.mp4 --seconds 20

# 3 pre-finished jobs so the dashboard is never empty
docker compose exec backend python /scripts/seed_demo.py
```

Run the pipeline directly (useful for debugging):

```bash
docker compose exec backend python -m app.ml.video_pipeline /samples/road_demo.mp4 /media/processed/test.mp4
```

---

## How it works

1. **Upload** — extension + magic-byte check, streamed to `/media/uploads/{job_id}`, size-capped.
2. **Queue** — `BackgroundTasks` hands the job to a single-worker `ThreadPoolExecutor`, so
   the event loop never blocks and API usage stays serialized.
3. **Process** — OpenCV decodes every frame; every `FRAME_STRIDE`-th frame is JPEG-encoded and
   POSTed to `https://detect.roboflow.com/{MODEL_ID}`. Failures retry with backoff and only
   affect that frame.
4. **Render** — boxes and labels are drawn on *every* frame and piped to ffmpeg as raw BGR24,
   encoded to **H.264 / yuv420p / +faststart** so browsers can play and seek it.
   (OpenCV's default `mp4v` writer produces files Chrome refuses to play — hence ffmpeg.)
5. **Persist** — progress is written to the SQLite `jobs` row about every 1%; the UI polls
   `GET /api/v1/jobs/{id}` at ~1 Hz. Detections are bulk-inserted at the end.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `roboflow_configured: false` on `/health` | `ROBOFLOW_API_KEY` missing from `.env`; recreate with `docker compose up -d --force-recreate backend` |
| Job fails with *"Roboflow rejected the API key"* | Wrong/expired key, or the key has no access to `MODEL_ID` |
| Many `api_failures` on a job | Rate limiting or flaky network — raise `FRAME_STRIDE`, or retry later |
| Video shows but won't seek | Media service not reachable on 3006; check `docker compose logs media` |
| Video won't play at all | Confirm the output is H.264: `docker compose exec backend ffprobe /media/processed/<id>.mp4` |
| Upload rejected with 415 | Unsupported container — use MP4/MOV/AVI/MKV/WEBM |
| History shows *"Interrupted by a backend restart"* | Expected: in-flight jobs are marked failed on startup. Re-upload. |
| Frontend can't reach the API | `VITE_API_URL` is baked in at build time — rebuild after changing it |

Reset everything:

```bash
docker compose down -v && docker compose up --build
```

---

## Local development (without Docker)

```bash
# backend — needs ffmpeg on PATH
cd backend
python -m venv .venv && .venv/Scripts/activate      # Windows
pip install -r requirements.txt
set MEDIA_ROOT=../media& set DB_PATH=../media/app.db
uvicorn app.main:app --reload --port 8007

# frontend
cd frontend
npm install
npm run dev        # http://localhost:3007
```

---

## Scope

Included: upload, hosted inference, boxed video, 3D dashboard, history, exports.
Not included: auth, cloud storage, live camera, multi-tenant, HTTPS, local training or
ONNX/CUDA inference, distributed queues.
