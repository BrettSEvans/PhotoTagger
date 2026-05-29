# Railway Hybrid Hosting

PhotoTagger uses a hybrid model for hosted use:

- Railway serves the React web UI in `cloud-ui` mode.
- Your computer runs the PhotoTagger Local Agent in `local-agent` mode.
- Photos stay on your computer. The local agent reads images and writes XMP sidecars.

Railway cannot directly access a folder on your laptop, so the hosted UI calls the local agent from your browser.

## Railway Variables

Set these on Railway:

```bash
PHOTOTAGGER_MODE=cloud-ui
```

Railway provides `PORT` automatically. The Dockerfile builds the web UI and starts `python -m src.api`, which serves `web/dist`.

## Local Agent

Run this on the computer that has the photos:

```bash
export PHOTOTAGGER_MODE=local-agent
export PHOTOTAGGER_AGENT_TOKEN="choose-a-long-random-token"
export PHOTOTAGGER_ALLOWED_PHOTO_ROOTS="/Users/you/Pictures:/Users/you/Desktop/Nationals"
python -m src.api
```

Then open the Railway app and enter:

- Local Agent URL: `http://127.0.0.1:5001`
- Agent Token: the same token from `PHOTOTAGGER_AGENT_TOKEN`

## Security Notes

- Do not expose the local agent publicly.
- Keep `PHOTOTAGGER_ALLOWED_PHOTO_ROOTS` narrow.
- The token is for browser-to-local-agent requests only. Future Google SSO should protect hosted user sessions separately.
