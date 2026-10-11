# Grok Attribute Image Generator (Hardened)

Structured attribute library + single-page web app for generating photorealistic images with the Grok Imagine API.

## Features
- Extensive library (skin, hair, outfit/satin with natural drape, poses, scenery, technical locks)
- Exclusive, boolean, and multi-select attributes
- Strong realism locks (micro-texture, film grain, fabric drape language)
- Error handling, localStorage for API key, status feedback
- Single and batch generation

## Setup

### Hermes xAI OAuth mode (recommended)

This repository now includes a local backend that uses Hermes' xAI OAuth image-generation provider. The browser never stores or sees an xAI API key.

1. Authenticate Hermes once:
   ```bash
   hermes auth add xai-oauth --no-browser
   ```
2. Configure the native backend:
   ```bash
   hermes config set image_gen.provider xai
   hermes config set image_gen.xai.model grok-imagine-image-quality
   hermes config set image_gen.xai.resolution 1k
   ```
3. Start the app with the Hermes virtual environment:
   ```bash
   "$HOME/.hermes/hermes-agent/venv/bin/python" server.py
   ```
4. Open [http://localhost:8123](http://localhost:8123). The UI generates through Hermes and keeps outputs under `generated/`. It exposes every aspect ratio xAI supports: `1:1`, `16:9`, `9:16`, `4:3`, `3:4`, `3:2`, and `2:3`; **9:16 is the default**.

The server accepts one image or four variations at a time. It never exposes OAuth credentials to the browser.

### Direct xAI API-key mode (legacy)

The original static-only approach requires an API key from [console.x.ai](https://console.x.ai), then `python -m http.server 8000`. It is retained only for compatibility; prefer the Hermes backend above.

## Security

- In Hermes mode, the browser calls only the local `/api/generate` endpoint; xAI OAuth credentials remain in Hermes' auth store.
- Generated image files are served locally from `generated/`.
- The legacy direct API-key mode is not recommended for shared or production deployments.

## Library
See `library.json`. Each value has a `steers` description used for prompt assembly and tooltips.
