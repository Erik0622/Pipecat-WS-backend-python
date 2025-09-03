import base64
import math
import os
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse


APP_NAME = "Pipecat WS Backend (minimal)"
PORT = int(os.getenv("PORT", "8080"))
PIPECAT_PCM_RATE = int(os.getenv("PIPECAT_PCM_RATE", "24000"))
TESTTONE_HZ = int(os.getenv("TESTTONE_HZ", "440"))
TESTTONE_MS = int(os.getenv("TESTTONE_MS", "600"))
DIAG_LOOPBACK = int(os.getenv("DIAG_LOOPBACK_MS", "0")) > 0


app = FastAPI(title=APP_NAME)


def generate_sine_pcm16(rate: int, hz: int, ms: int, amplitude: float = 0.25) -> bytes:
    total_samples = int(rate * ms / 1000)
    out = bytearray()
    for i in range(total_samples):
        t = float(i) / rate
        s = int(32767 * amplitude * math.sin(2.0 * math.pi * hz * t))
        out += s.to_bytes(2, byteorder="little", signed=True)
    return bytes(out)


@app.get("/health")
def health():
    return JSONResponse({
        "status": "ok",
        "service": APP_NAME,
        "rate": PIPECAT_PCM_RATE,
        "loopback": DIAG_LOOPBACK,
    })


@app.get("/")
def root():
    return PlainTextResponse(f"{APP_NAME} running on :{PORT}")


@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_json()
            mtype = msg.get("type")

            if mtype == "say":
                # Simple test tone as audio_out (to verify end-to-end)
                text = (msg.get("text") or "").strip()
                pcm = generate_sine_pcm16(PIPECAT_PCM_RATE, TESTTONE_HZ, TESTTONE_MS)
                await ws.send_json({
                    "type": "audio_out",
                    "data": base64.b64encode(pcm).decode("ascii"),
                    "mimeType": f"audio/pcm;rate={PIPECAT_PCM_RATE}",
                    "note": f"TESTTONE {TESTTONE_HZ}Hz for '{text}'"
                })

            elif mtype == "audio_in":
                # Optional: loopback incoming PCM as audio_out for diagnostics
                if DIAG_LOOPBACK:
                    data_b64: Optional[str] = msg.get("data")
                    if isinstance(data_b64, str) and data_b64:
                        await ws.send_json({
                            "type": "audio_out",
                            "data": data_b64,
                            "mimeType": msg.get("mimeType") or f"audio/pcm;rate={PIPECAT_PCM_RATE}",
                            "note": "loopback"
                        })

            else:
                # Ignore unknown messages silently
                pass

    except WebSocketDisconnect:
        return
    except Exception:
        # Best-effort: keep server alive; client can reconnect
        return


