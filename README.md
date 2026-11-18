# Article Research Reader

A mobile-friendly web app for extracting **publicly accessible** article text and downloading attributed Markdown. It does not bypass authentication or paywalls.

## Deploy (Render)

1. Put `main.py` and `requirements.txt` in a GitHub repository.
2. At [render.com](https://render.com), create a **New Web Service** from the repository.
3. Set runtime to **Python**.
4. Build command: `pip install -r requirements.txt`
5. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Open the resulting HTTPS URL in Chrome on Android. Chrome menu → **Add to Home screen**.

Note: Hosting services may charge or sleep on free tiers. The server needs outbound internet access.

## Local development

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Visit http://localhost:8000.

## Security / production notes

The app rejects private/reserved DNS results, rejects redirects, limits HTML response size and sets timeouts. For hostile public deployments, add an egress firewall or pinned DNS/IP connection to prevent DNS rebinding between validation and request, plus rate limiting and a cache. Respect publisher terms and copyright.
