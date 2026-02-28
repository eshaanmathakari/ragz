import Anthropic from "@anthropic-ai/sdk";
import express from "express";
import rateLimit from "express-rate-limit";
import helmet from "helmet";
import cors from "cors";
import { config } from "dotenv";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ── Validate env ────────────────────────────────────────────────
if (!process.env.ANTHROPIC_API_KEY) {
  console.error("❌  ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.");
  process.exit(1);
}

const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

// ── Express setup ───────────────────────────────────────────────
const app = express();
const PORT = process.env.PORT || 3000;
const MAX_PAYLOAD = process.env.MAX_PAYLOAD || "20mb";

// Security headers
app.use(helmet({ contentSecurityPolicy: false }));
app.use(cors());
app.use(express.json({ limit: MAX_PAYLOAD }));

// Rate limiting — 30 extractions per minute per IP
const apiLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 30,
  message: { error: "Too many requests. Please wait a moment and try again." },
  standardHeaders: true,
  legacyHeaders: false,
});

// ── Static frontend ─────────────────────────────────────────────
app.use(express.static(join(__dirname, "public")));

// ── System prompt ───────────────────────────────────────────────
const SYSTEM_PROMPT = `You are a precision dimension extractor. Your job is to look at images (photos, sketches, drawings, handwritten notes) and extract ALL dimensions, measurements, and numeric values you can find.

Rules:
- Output ONLY the extracted dimensions, one per line
- Include units exactly as written (ft, in, m, cm, mm, ", ', etc.)
- Preserve fractions as written (e.g. 1/2", 3/4")
- If a dimension has a label, format as: Label: Dimension
- If dimensions appear to be in a table, preserve the row structure
- If you see arrows or lines with measurements, extract them
- Do NOT add commentary, headers, or explanations
- Do NOT wrap in markdown or code blocks
- If you cannot find any dimensions, respond with exactly: NO_DIMENSIONS_FOUND`;

// ── API endpoint ────────────────────────────────────────────────
app.post("/api/extract", apiLimiter, async (req, res) => {
  try {
    const { image, mediaType } = req.body;

    if (!image || !mediaType) {
      return res.status(400).json({ error: "Missing image or mediaType in request body." });
    }

    // Validate media type
    const allowedTypes = ["image/jpeg", "image/png", "image/gif", "image/webp"];
    if (!allowedTypes.includes(mediaType)) {
      return res.status(400).json({ error: `Unsupported image type: ${mediaType}. Use JPEG, PNG, GIF, or WebP.` });
    }

    const response = await client.messages.create({
      model: process.env.CLAUDE_MODEL || "claude-sonnet-4-20250514",
      max_tokens: 1024,
      system: SYSTEM_PROMPT,
      messages: [
        {
          role: "user",
          content: [
            {
              type: "image",
              source: {
                type: "base64",
                media_type: mediaType,
                data: image,
              },
            },
            {
              type: "text",
              text: "Extract all dimensions and measurements from this image.",
            },
          ],
        },
      ],
    });

    const text = response.content
      ?.map((block) => block.text || "")
      .filter(Boolean)
      .join("\n")
      .trim();

    if (!text || text === "NO_DIMENSIONS_FOUND") {
      return res.json({ dimensions: null, message: "No dimensions found in this image." });
    }

    return res.json({
      dimensions: text,
      lines: text.split("\n").filter((l) => l.trim()),
      usage: {
        input_tokens: response.usage?.input_tokens,
        output_tokens: response.usage?.output_tokens,
      },
    });
  } catch (err) {
    console.error("Extraction error:", err.message);

    if (err.status === 401) {
      return res.status(500).json({ error: "Invalid API key. Check your ANTHROPIC_API_KEY." });
    }
    if (err.status === 429) {
      return res.status(429).json({ error: "Rate limited by Anthropic. Please wait and retry." });
    }

    return res.status(500).json({ error: "Extraction failed. Please try again." });
  }
});

// ── Health check ────────────────────────────────────────────────
app.get("/api/health", (req, res) => {
  res.json({ status: "ok", model: process.env.CLAUDE_MODEL || "claude-sonnet-4-20250514" });
});

// ── Start ───────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`\n  ⚡ Dimension Extractor running at http://localhost:${PORT}\n`);
});
