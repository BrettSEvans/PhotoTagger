# PhotoTagger Web UI

React + TypeScript frontend for PhotoTagger tournament photo discovery system.

## Setup

```bash
cd web
npm install
```

## Development

Start the dev server:

```bash
npm run dev
```

Opens at http://localhost:3000 (backend proxy to http://localhost:5000)

## Build

```bash
npm run build
```

Generates optimized build in `dist/`.

## Architecture

- **Vite** - Fast build tool
- **React 19** - UI library
- **TypeScript** - Type safety
- **Tailwind CSS** - Styling
- **Axios** - API client

## Pages

1. **Upload** - Crawl and upload tournament photos
2. **Search** - Search by jersey number, filter by confidence
3. **Gallery** - Browse all uploaded photos

## API Integration

Frontend communicates with Flask backend at `http://localhost:5000`:

- `POST /api/crawl` - Upload photos
- `GET /api/search` - Search by jersey
- `GET /api/photos` - List all photos
- `GET /api/info` - Database stats
- `GET /api/faces/<id>` - Get faces for photo
