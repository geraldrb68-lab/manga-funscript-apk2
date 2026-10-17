"""Cliente mínimo del protocolo Buttplug v3 sobre websocket (Intiface Central)."""
import asyncio
import json
import threading

import websockets


class Intiface:
    def __init__(self, log=print):
        self.log = log
        self.on_devices = lambda: None
        self.devices = {}
        self.connected = False
        self.ws = None
        self._id = 1
        self.send_errors = 0          # órdenes que fallaron (antes se perdían en silencio)
        self.last_error = ""
        self.sent_ok = 0
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

    # ---------- utilidades ----------
    def _next(self):
        self._id += 1
        return self._id

    def _run(self, coro):
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
        fut.add_done_callback(self._done)
        return fut

    def _done(self, fut):
        """Registra los errores de envío (websocket cerrado, etc.) en lugar de perderlos."""
        try:
            exc = fut.exception()
        except Exception as e:                      # cancelado
            exc = e
        if exc is not None:
            self.send_errors += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            if self.send_errors in (1, 10, 100):
                self.log(f"Intiface: fallo al enviar ({self.last_error}).")
        else:
            self.sent_ok += 1

    async def _send(self, msg):
        if self.ws is not None:
            await self.ws.send(json.dumps([msg]))

    # ---------- conexión ----------
    def connect(self, url):
        self._run(self._connect(url))

    async def _connect(self, url):
        try:
            self.ws = await websockets.connect(url)
            await self._send({"RequestServerInfo": {"Id": 1, "ClientName": "MangaFunscript", "MessageVersion": 3}})
            self.connected = True
            asyncio.ensure_future(self._listen())
            self.log(f"Conectado a {url}")
        except Exception as e:
            self.connected = False
            self.log(f"No se pudo conectar: {e}")

    async def _listen(self):
        try:
            async for raw in self.ws:
                for m in json.loads(raw):
                    self._handle(m)
        except Exception as e:
            self.log(f"Conexión cerrada: {e}")
        finally:
            self.connected = False
            self.devices = {}
            self.on_devices()

    def _handle(self, m):
        (kind, v), = m.items()
        if kind == "ServerInfo":
            self.log(f"Servidor: {v.get('ServerName', '?')}")
            asyncio.ensure_future(self._send({"RequestDeviceList": {"Id": self._next()}}))
        elif kind == "DeviceList":
            self.devices = {d["DeviceIndex"]: d for d in v.get("Devices", [])}
            self.on_devices()
        elif kind == "DeviceAdded":
            self.devices[v["DeviceIndex"]] = v
            self.log(f"Dispositivo añadido: {v.get('DeviceName')}")
            self.on_devices()
        elif kind == "DeviceRemoved":
            self.devices.pop(v.get("DeviceIndex"), None)
            self.on_devices()
        elif kind == "Error":
            self.log(f"Error del servidor: {v.get('ErrorMessage')}")

    def disconnect(self):
        async def _c():
            if self.ws is not None:
                await self.ws.close()
        self._run(_c())

    def scan(self):
        self._run(self._send({"StartScanning": {"Id": self._next()}}))

    # ---------- canales ----------
    def channels(self):
        """Lista de canales controlables: (etiqueta, dict)."""
        out = []
        for idx, d in self.devices.items():
            msgs = d.get("DeviceMessages", {})
            for i, a in enumerate(msgs.get("ScalarCmd", [])):
                typ = a.get("ActuatorType", "Scalar")
                steps = a.get("StepCount")             # pasos reales del actuador: por debajo de 1/steps no se mueve
                tag = f" ({steps} pasos)" if steps else ""
                out.append((f"{d.get('DeviceName')} · {typ} #{i}{tag}",
                            {"device": idx, "kind": "scalar", "index": i, "actuator": typ, "steps": steps}))
            for i, _ in enumerate(msgs.get("LinearCmd", [])):
                out.append((f"{d.get('DeviceName')} · Linear #{i}",
                            {"device": idx, "kind": "linear", "index": i, "actuator": "Linear", "steps": None}))
        return out

    # ---------- órdenes ----------
    def send_value(self, ch, value, duration_ms=100):
        """Envía un valor 0-1. Devuelve False si no se pudo (sin conexión)."""
        if not self.connected or ch is None:
            return False
        value = max(0.0, min(1.0, float(value)))
        if ch["kind"] == "scalar":
            msg = {"ScalarCmd": {"Id": self._next(), "DeviceIndex": ch["device"],
                                 "Scalars": [{"Index": ch["index"], "Scalar": value,
                                              "ActuatorType": ch["actuator"]}]}}
        else:
            msg = {"LinearCmd": {"Id": self._next(), "DeviceIndex": ch["device"],
                                 "Vectors": [{"Index": ch["index"], "Duration": int(duration_ms),
                                              "Position": value}]}}
        self._run(self._send(msg))
        return True

    def stop_all(self):
        if self.connected:
            self._run(self._send({"StopAllDevices": {"Id": self._next()}}))
