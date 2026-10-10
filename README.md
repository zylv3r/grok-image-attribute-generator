# Grok Attribute Image Generator

Web app for generating photorealistic images using a structured attribute library and the Grok Imagine API.

## Setup

1. Get an API key from https://console.x.ai
2. Open `index.html` in a browser (or serve the folder).
3. Enter your API key and select attributes.
4. Generate single images or variations.

## Library

See `library.json` for categories, attributes, and values with steering descriptions.

Supports exclusive, boolean, and multi-select attributes. Includes micro-texture locks and natural satin fabric drape language.

## API

Uses `POST https://api.x.ai/v1/images/generations` with model `grok-imagine-image-2.0`.

**Note:** API key is sent from the browser. For production, use a backend proxy.
