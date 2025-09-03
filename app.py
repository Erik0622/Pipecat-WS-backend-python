import base64
import json
import math
import os
import asyncio
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse
import websockets


APP_NAME = "Pipecat WS Backend (minimal)"
PORT = int(os.getenv("PORT", "8080"))
PIPECAT_PCM_RATE = int(os.getenv("PIPECAT_PCM_RATE", "24000"))
TESTTONE_HZ = int(os.getenv("TESTTONE_HZ", "440"))
TESTTONE_MS = int(os.getenv("TESTTONE_MS", "600"))
DIAG_LOOPBACK = int(os.getenv("DIAG_LOOPBACK_MS", "0")) > 0
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-preview-native-audio-dialog")
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "Sprich kurz und hilfsbereit auf Deutsch.")

GEMINI_WS_URL = (
    "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.LiveClient?key="
    + (GEMINI_API_KEY or "")
)


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
    upstream = None
    try:
        # Optional: ohne API-Key nur Testton/Loopback anbieten
        if GEMINI_API_KEY:
            upstream = await websockets.connect(GEMINI_WS_URL, max_size=8 * 1024 * 1024)
            # Sende Setup an Gemini Live
            setup = {
                "setup": {
                    "model": GEMINI_MODEL,
                    "responseModalities": ["AUDIO"],
                    "systemInstruction": SYSTEM_PROMPT,
                }
            }
            await upstream.send(json.dumps(setup))

            async def pump_down():
                while True:
                    raw = await upstream.recv()
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    # Suche nach serverContent → modelTurn → parts → inlineData (audio)
                    sc = msg.get("serverContent")
                    if sc and isinstance(sc, dict):
                        parts = (
                            sc.get("modelTurn", {}).get("parts")
                            or sc.get("turns", [{}])[-1].get("parts")
                        )
                        if isinstance(parts, list):
                            for p in parts:
                                inline = p.get("inlineData") if isinstance(p, dict) else None
                                if inline and str(inline.get("mimeType", "")).startswith("audio/pcm"):
                                    data = inline.get("data")
                                    if isinstance(data, str):
                                        await ws.send_json({
                                            "type": "audio_out",
                                            "data": data,
                                            "mimeType": inline.get("mimeType"),
                                        })

            async def pump_up():
                while True:
                    msg = await ws.receive_json()
                    mtype = msg.get("type")
                    if mtype == "audio_in":
                        data_b64: Optional[str] = msg.get("data")
                        mime = msg.get("mimeType") or f"audio/pcm;rate={PIPECAT_PCM_RATE}"
                        if isinstance(data_b64, str) and data_b64:
                            await upstream.send(
                                json.dumps({
                                    "realtimeInput": {
                                        "media": [{"data": data_b64, "mimeType": mime}]
                                    }
                                })
                            )
                    elif mtype == "say":
                        text = (msg.get("text") or "").strip() or "Hallo."
                        await upstream.send(
                            json.dumps({
                                "clientContent": {
                                    "turns": [
                                        {"role": "user", "parts": [{"text": text}]}
                                    ],
                                    "turnComplete": True,
                                }
                            })
                        )
                    else:
                        # Optionaler Testton solange kein Gemini-Key vorhanden ist
                        if not GEMINI_API_KEY and mtype == "say":
                            pcm = generate_sine_pcm16(PIPECAT_PCM_RATE, TESTTONE_HZ, TESTTONE_MS)
                            await ws.send_json({
                                "type": "audio_out",
                                "data": base64.b64encode(pcm).decode("ascii"),
                                "mimeType": f"audio/pcm;rate={PIPECAT_PCM_RATE}",
                            })

            await asyncio.gather(pump_down(), pump_up())
        else:
            # Fallback nur Testton/Loopback
            while True:
                msg = await ws.receive_json()
                mtype = msg.get("type")
                if mtype == "say":
                    pcm = generate_sine_pcm16(PIPECAT_PCM_RATE, TESTTONE_HZ, TESTTONE_MS)
                    await ws.send_json({
                        "type": "audio_out",
                        "data": base64.b64encode(pcm).decode("ascii"),
                        "mimeType": f"audio/pcm;rate={PIPECAT_PCM_RATE}",
                    })
                elif mtype == "audio_in" and DIAG_LOOPBACK:
                    data_b64: Optional[str] = msg.get("data")
                    if isinstance(data_b64, str) and data_b64:
                        await ws.send_json({
                            "type": "audio_out",
                            "data": data_b64,
                            "mimeType": msg.get("mimeType") or f"audio/pcm;rate={PIPECAT_PCM_RATE}",
                        })
    except WebSocketDisconnect:
        return
    except Exception:
        return
    finally:
        try:
            if upstream:
                await upstream.close()
        except Exception:
            pass


