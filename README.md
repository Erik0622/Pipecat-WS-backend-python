# Pipecat WS Backend (Minimal)

Ein minimaler WebSocket‑Dienst, der das vereinbarte Protokoll spricht:
- Eingehend: `audio_in` (Base64 PCM LE 16‑bit, z. B. 24000 Hz)
- Eingehend: `say` (Text), antwortet mit kurzem Testton als `audio_out`
- Ausgehend: `audio_out` (Base64 PCM)

Damit kann dein bestehender Twilio‑Server Audio an Pipecat weiterleiten und die Antworten zurückspielen.

## Endpunkte
- `GET /health` – einfacher Health‑Check
- `GET /` – Text "running"
- `WS /ws` – WebSocket‑Protokoll

## Env Variablen
- `PORT` (default 8080)
- `PIPECAT_PCM_RATE` (default 24000)
- `TESTTONE_HZ` (default 440)
- `TESTTONE_MS` (default 600)
- `DIAG_LOOPBACK_MS` (>0 aktiviert Loopback von `audio_in`→`audio_out`)

## Lokal starten
```bash
uvicorn app:app --host 0.0.0.0 --port 8080
```

## Docker
```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8080
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
```

## Fly.io Deploy (kurz)
- Neues Fly‑App erstellen oder vorhandene nutzen
- `fly launch` (ja zu Dockerfile)
- `fly secrets set` falls nötig (z. B. `PIPECAT_PCM_RATE=24000`)
- `fly deploy`

Nach Deploy bekommst du eine URL, z. B. `wss://pipecat-xyz.fly.dev/ws`. Diese trägst du als `PIPELINE_WS_URL` in deinem Twilio‑Server ein.
