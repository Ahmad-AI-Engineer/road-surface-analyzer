# Road Surface Conditions Analyzer - Roboflow Hosted Inference Architecture Plan

## Overview

The Road Surface Conditions Analyzer processes road driving videos using the
**Roboflow Hosted Inference API** for road damage detection — no local model files,
training, or GPU/CPU inference runtime are required.

The system takes a road video as input, extracts frames locally with OpenCV, sends
selected frames to the Roboflow Hosted Inference API, receives detections, draws
bounding boxes, and returns an analyzed video.

Detected classes:

-   Crack
-   Pothole
-   Alligator Cracking

------------------------------------------------------------------------

# Architecture Flow

The system is intentionally simple: a single-user demo with **no message broker, no job
queue, no event-stream layer, and no local model**. Long-running work runs on a background
thread inside the FastAPI process; the UI polls for status; detection is delegated entirely
to the Roboflow Hosted Inference API.

    React 3D UI
        |
        ↓
    FastAPI Backend
    (BackgroundTasks + single worker thread)
        |
        ↓
    Video Processing (OpenCV)
        |
        ↓
    Frame Extraction
        |
        ↓
    Roboflow Inference API
        |
        ↓
    Detection Results
        |
        ↓
    Bounding Box Rendering
        |
        ↓
    Processed Video Output
        |
        ↓
    3D Analytics Dashboard

------------------------------------------------------------------------

# AI Inference Architecture

    Road Video Frame

            |
            ↓

    Frame Preprocessing
    (resize/encode to JPEG)

            |
            ↓

    Roboflow Hosted Inference API
    (MODEL_ID=road-damage-medium-9semt/1)

            |
            ↓

    Object Detection

            |
            ↓

    Damage Classification

    - Crack
    - Pothole
    - Alligator Cracking

            |
            ↓

    Bounding Box Overlay

------------------------------------------------------------------------

# Inference Engine

No model is downloaded, trained, or deployed locally. All detection requests are sent to the
**Roboflow Hosted Inference API** over HTTPS:

    Backend

        |
        ↓

    POST https://detect.roboflow.com/{MODEL_ID}
    ?api_key={ROBOFLOW_API_KEY}
    (JPEG frame bytes)

        |
        ↓

    JSON response:
    - class name
    - confidence score
    - bounding box (x, y, width, height)

Configuration:

-   `ROBOFLOW_API_KEY` — required to call the inference API
-   `MODEL_ID=road-damage-medium-9semt/1` — the hosted model + version to call
-   `CONF_THRESHOLD` — minimum confidence kept after the response is received
-   `FRAME_STRIDE` — how many frames are skipped between API calls (see below)

If the API is unreachable or no key is configured, `MOCK_DETECTOR=1` produces deterministic
fake boxes so the rest of the demo (UI, video pipeline, dashboard) is never blocked.

------------------------------------------------------------------------

# Hardware Consideration

Because inference runs on Roboflow's hosted infrastructure, the local machine only needs to
run FastAPI, OpenCV, and FFmpeg — no GPU, no CUDA, no local ML runtime.

Example development machine:

Lenovo ThinkPad L480

Specifications:

-   Intel Core i5/i7 8th Generation CPU
-   8GB/16GB RAM
-   Intel UHD Graphics

Expected:

-   Frame extraction and video rebuild run comfortably on this hardware
-   Overall speed is dominated by Roboflow API latency and `FRAME_STRIDE`, not local compute

------------------------------------------------------------------------

# Video Processing Pipeline

    Input Video

        ↓

    Extract Frames

        ↓

    Apply FRAME_STRIDE
    (e.g. process every 5th frame)

        ↓

    Resize / Encode Sampled Frame

        ↓

    Send Frame to Roboflow Inference API

        ↓

    Receive Detection Results
    (class, confidence, bbox)

        ↓

    Draw Bounding Boxes
    (reused on skipped frames)

        ↓

    Rebuild Video (FFmpeg, H.264 yuv420p)

        ↓

    Output Analyzed Video

Only sampled frames are sent to the Roboflow API — not every frame — to reduce API calls and
latency. Detections from the last analyzed frame are reused on the frames skipped in between,
so bounding boxes remain visually continuous.

Processing runs on a background thread owned by the FastAPI process. Progress is written
directly to the job record in SQLite and read back by the frontend through periodic
`GET /api/v1/jobs/{id}` polling — no queue, no broker, no event stream.

------------------------------------------------------------------------

# Frontend Architecture

Technology:

-   React
-   HTML
-   CSS
-   3D UI effects and animations

Features:

-   Video upload
-   Processing status via status polling
-   Interactive dashboard
-   Damage visualization (class, confidence, bounding boxes)
-   Processed video playback

Flow:

    React 3D Interface

            |
            ↓

    Upload Component

            |
            ↓

    Backend Processing

            |
            ↓

    Status Polling

            |
            ↓

    Detection Results

            |
            ↓

    Dashboard Visualization

------------------------------------------------------------------------

# Backend Architecture

Technology:

-   FastAPI
-   Python
-   OpenCV
-   FFmpeg
-   Roboflow Inference SDK / REST API
-   SQLite (job history)

Responsibilities:

-   Receive videos
-   Extract frames
-   Apply `FRAME_STRIDE` frame sampling
-   Call the Roboflow Hosted Inference API for sampled frames
-   Generate bounding boxes from the API response
-   Create processed videos
-   Track job progress in SQLite
-   Return results to frontend

Not used: local model files, local GPU/CPU inference runtime, message brokers, distributed
task queues, server-sent event streams.

------------------------------------------------------------------------

# Detection Output

Example:

``` json
{
  "detections": [
    {
      "class": "pothole",
      "confidence": 0.91,
      "bbox": [120,240,300,380]
    }
  ]
}
```

------------------------------------------------------------------------

# Client Demo Workflow

1.  User uploads road video.
2.  Backend accepts the upload and starts background processing.
3.  Backend extracts frames and applies `FRAME_STRIDE` sampling.
4.  Sampled frames are sent to the Roboflow Hosted Inference API.
5.  System receives class, confidence, and bounding box for each detection.
6.  Bounding boxes are drawn on frames.
7.  Frontend polls job status until processing completes.
8.  Final processed video is displayed in the 3D dashboard.

------------------------------------------------------------------------

# Technology Stack

## Frontend

-   React
-   TypeScript
-   TailwindCSS
-   Three.js / react-three-fiber
-   Framer Motion

## Backend

-   FastAPI
-   Python
-   OpenCV
-   FFmpeg
-   Roboflow Inference SDK / API

## Deployment

Single docker compose stack — three services, no local model, no broker:

| Port | Service | Purpose |
|------|---------|---------|
| 8007 | backend | FastAPI REST API |
| 3007 | frontend | React SPA (nginx) |
| 3006 | media | processed video / thumbnail hosting (nginx) |

Detection quality and speed depend on the Roboflow Hosted Inference API, not on local
hardware — the same setup works identically on any machine with internet access.

------------------------------------------------------------------------

# Deployment Architecture

    React 3D Frontend
            |
            ↓
    FastAPI Backend
            |
            ↓
    OpenCV Video Processor
            |
            ↓
    Roboflow Inference API
            |
            ↓
    Detection Renderer
            |
            ↓
    Processed Video

------------------------------------------------------------------------

# MVP Scope

This remains a client demo — no production scaling components are included.

## Phase 1

-   Roboflow Hosted Inference API integration
-   Video upload
-   Damage detection (pothole / crack / alligator cracking)
-   Bounding boxes + confidence display
-   Processed video generation

## Phase 2

-   3D analytics dashboard
-   Damage statistics
-   Confidence visualization
-   Interactive video review

## Phase 3

-   Real-time camera processing
-   Multi-video batch review
-   (Out of scope for this demo; noted here only as a possible future direction)
