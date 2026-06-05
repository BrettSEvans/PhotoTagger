#!/usr/bin/env python3
"""
Render the architecture diagrams (Mermaid) to PNG files in docs/diagrams/.

Uses Playwright's headless Chromium + mermaid from a CDN. High deviceScaleFactor
gives crisp images suitable for PDF embedding.

Usage:
    python docs/render_diagrams.py
"""

from pathlib import Path
from playwright.sync_api import sync_playwright

DOCS = Path(__file__).resolve().parent
OUT = DOCS / "diagrams"
OUT.mkdir(exist_ok=True)

MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"

# Brand-aligned theme variables (purple/violet).
THEME = """{
  startOnLoad: false,
  theme: 'base',
  themeVariables: {
    primaryColor: '#f3f1fb',
    primaryBorderColor: '#5b34d6',
    primaryTextColor: '#1f2430',
    lineColor: '#5b34d6',
    fontFamily: 'Helvetica, Arial, sans-serif',
    fontSize: '15px'
  },
  flowchart: { curve: 'basis', nodeSpacing: 45, rankSpacing: 55 }
}"""

DIAGRAMS = {
    "01-architecture": """
flowchart TB
    SPA["React SPA (web/)<br/>Vite · Router · Axios · Tailwind<br/>Roster · Upload · Players · Gallery"]
    subgraph API["Flask API — src/api.py"]
        direction TB
        BP["Blueprints<br/>system · roster · photos<br/>batches · detection · review"]
        JOB["LocalJobRunner<br/>(background thread + queue)"]
        ML["ML pipeline (local-agent only)<br/>FaceDetector · UniformDetector<br/>JerseyRecognizer · OCREngine · FaceClusterer"]
        REPO["Database facade → Repositories<br/>photos · faces · clusters · roster<br/>batches · jobs · game_context · ReviewService"]
        BP --> JOB
        JOB --> ML
        BP --> REPO
        ML --> REPO
    end
    STORE[("SQLite photo_catalog.db<br/>+ filesystem: photos/ uploads/ *.xmp")]
    SPA -->|JSON / REST| BP
    REPO --> STORE
    ML -->|reads photos<br/>writes XMP sidecars| STORE
""",

    "02-deployment": """
flowchart LR
    Browser([Browser])
    Cloud["Railway — cloud-ui mode<br/>serves SPA + app-config<br/>NO ML (crawler/ocr/jobs = None)"]
    Agent["Local agent — local-agent mode<br/>127.0.0.1:5001 (loopback only)<br/>FaceDetector · OCR · clustering"]
    Disk[("User's disk<br/>photos/ · *.xmp")]
    Browser -->|static SPA + config| Cloud
    Browser -->|detection / images / face-crops<br/>X-PhotoTagger-Agent-Token| Agent
    Agent --> Disk
""",

    "03-pipeline": """
flowchart TB
    U["Upload / Crawl<br/>PhotoCrawler → photos rows (dedup by file_hash)<br/>+ batch + game context (Team A/B colors)"]
    REQ["POST /api/detect-faces-and-cluster<br/>enqueues one job → 202 + job_id"]
    P1["PHASE 1 · Face detection (0–50%)<br/>InsightFace buffalo_l → 384-d embeddings + bbox<br/>UniformDetector samples torso color<br/>idempotent: skip photos that already have faces"]
    P2["PHASE 2 · Jersey recognition (51–80%)<br/>Tesseract OCR on torso crops, color-gated<br/>digit sanity + IoU dedup<br/>match jersey# + color → roster entry"]
    P3["PHASE 3 · Clustering (81–100%)<br/>greedy nearest-centroid over embeddings<br/>quality/size/color gating<br/>auto-match cluster → roster"]
    POLL["Browser polls GET /api/jobs/:id → progress<br/>GET /api/players → live counts<br/>Assign / tag → write_xmp_sidecar()"]
    U --> REQ --> P1 --> P2 --> P3 --> POLL
""",

    "04-datamodel": """
erDiagram
    photo_batches ||--o{ photos : groups
    photos ||--o{ faces : has
    photos ||--o{ ocr_results : has
    player_clusters ||--o{ faces : "cluster_id"
    rosters ||--o{ ocr_results : "roster_entry_id"
    rosters ||--o{ player_clusters : "roster_entry_id"
    photos {
        int id PK
        text file_path UK
        text file_hash UK
        int batch_id FK
    }
    faces {
        int id PK
        int photo_id FK
        blob embedding "384-d"
        int cluster_id FK
        text jersey_color
        real quality_score
    }
    ocr_results {
        int id PK
        int photo_id FK
        text jersey_number
        text uniform_color
        int roster_entry_id FK
    }
    player_clusters {
        int id PK
        text player_name
        text jersey_number
        int roster_entry_id FK
    }
    rosters {
        int id PK
        text team_name
        int team_year
        int jersey_number
        text player_name
        text uniform_color
    }
    game_context_teams {
        int id PK
        text team_name
        text uniform_color
    }
    processing_jobs {
        int id PK
        text type
        text status
        int progress
    }
""",
}


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1600, "height": 1200},
            device_scale_factor=2,
        )
        for name, src in DIAGRAMS.items():
            html = f"""<!doctype html><html><head><meta charset="utf-8">
<style>body{{margin:0;padding:24px;background:#fff;}}</style>
<script src="{MERMAID_CDN}"></script></head>
<body><div class="mermaid">{src.strip()}</div>
<script>
  mermaid.initialize({THEME});
  window.__done = mermaid.run().then(()=>true).catch(e=>{{document.title='ERR:'+e;return false;}});
</script></body></html>"""
            page.set_content(html, wait_until="networkidle")
            page.wait_for_function("window.__done !== undefined", timeout=15000)
            page.wait_for_timeout(400)
            el = page.query_selector("div.mermaid svg") or page.query_selector("div.mermaid")
            el.screenshot(path=str(OUT / f"{name}.png"))
            print(f"  rendered {name}.png")
        browser.close()
    print(f"Diagrams written to {OUT}")


if __name__ == "__main__":
    main()
