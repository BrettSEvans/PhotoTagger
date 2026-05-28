# PhotoTagger

Find photos of Ultimate Frisbee players by jersey number.

## Quick Start

1. Create a `photos/` directory with your test JPGs
2. Run the crawler: `python -m src.crawler --photos ./photos`
3. Start the API: `python -m src.api`
4. Query: `curl http://localhost:5000/api/search?jersey=23&team=team-name`

## Architecture

**Crawler** → scans local photo folder → **OCR Engine** → extracts jersey numbers → **SQLite** → **REST API**

## Testing

```bash
pytest tests/ -v --cov=src
```
