# Security / Privacy Notes

This package intentionally does not include:

- Hugging Face tokens.
- Google Cloud credentials.
- A hard-coded GCS bucket path.
- `.git/` metadata.
- Generated benchmark outputs, activations, `.npz`, model weights, or user-specific caches.

Configure secrets and paths only in `.env.local`, environment variables, or your server's credential manager. `.env.local` is ignored by git.
