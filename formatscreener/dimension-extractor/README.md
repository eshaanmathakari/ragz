# 📐 Dimension Extractor

Extract handwritten dimensions from images using Claude Vision. Drop an image, get clean measurements — ready to copy and paste.

Handles messy handwriting, mixed units (ft, m, mm, fractions), labeled sketches, and measurement tables.

## Quick Start

```bash
# 1. Install dependencies
npm install

# 2. Add your API key
cp .env.example .env
# Edit .env and paste your Anthropic API key

# 3. Run
npm start
```

Open **http://localhost:3000** in your browser.

## Usage

Three ways to load an image:
- **Drag & drop** onto the upload zone
- **Click** to browse files
- **Ctrl+V / Cmd+V** to paste from clipboard

Hit **Extract Dimensions** → get a numbered list → **Copy All** to clipboard.

## Project Structure

```
dimension-extractor/
├── server.js          # Express backend (API proxy + static server)
├── public/
│   └── index.html     # Frontend (self-contained, no build step)
├── package.json
├── .env.example
└── README.md
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required.** Your Anthropic API key |
| `PORT` | `3000` | Server port |
| `CLAUDE_MODEL` | `claude-sonnet-4-20250514` | Model to use for extraction |
| `MAX_PAYLOAD` | `20mb` | Max image upload size |

## Architecture

```
Browser                    Server                    Anthropic
┌──────────┐  POST /api  ┌──────────┐  Messages   ┌──────────┐
│  Image   │────────────▶│  Express │────────────▶│  Claude  │
│  Upload  │  (base64)   │  Proxy   │  API call   │  Vision  │
│          │◀────────────│          │◀────────────│          │
│  Results │  dimensions │  + rate  │  extracted  │          │
└──────────┘             │  limit   │  text       └──────────┘
                         └──────────┘
```

**Why a backend proxy?** Your API key stays on the server, never exposed to the browser. The server also adds rate limiting (30 req/min per IP) and input validation.

## Deployment

Works anywhere Node.js runs:

**Fly.io:**
```bash
fly launch
fly secrets set ANTHROPIC_API_KEY=sk-ant-xxx
fly deploy
```

**Railway / Render:** Connect your repo, set the `ANTHROPIC_API_KEY` env var, done.

**Docker:**
```dockerfile
FROM node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .
EXPOSE 3000
CMD ["node", "server.js"]
```

## Cost

Each extraction is a single Claude Sonnet API call with one image. Typical cost: **~$0.01–0.03** per image depending on resolution.

## License

MIT
