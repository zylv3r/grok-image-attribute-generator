# Grok Attribute Image Generator (Hardened)

Structured attribute library + single-page web app for generating photorealistic images with the Grok Imagine API.

## Features
- Extensive library (skin, hair, outfit/satin with natural drape, poses, scenery, technical locks)
- Exclusive, boolean, and multi-select attributes
- Strong realism locks (micro-texture, film grain, fabric drape language)
- Error handling, localStorage for API key, status feedback
- Single and batch generation

## Setup
1. Get an API key from https://console.x.ai
2. Serve the folder locally:
   ```bash
   python -m http.server 8000
   ```
3. Open http://localhost:8000
4. Paste your API key and select attributes.

## Security
- API key is stored only in browser localStorage.
- For production, use a backend proxy so the key is never exposed to the client.

## Library
See `library.json`. Each value has a `steers` description used for prompt assembly and tooltips.
