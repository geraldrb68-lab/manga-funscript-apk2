"""Sistema de aprendizaje del generador: aprende de tus correcciones.

Tipos de corrección (lo que tú indicas en una viñeta):
  - "falta":      debería haber funscript aquí y no lo hubo  -> sube el sesgo de sus etiquetas.
  - "sobra":      no debía haberlo                           -> baja el sesgo de sus etiquetas.
  - "intensidad": la intensidad fue mal; delta en [-1, 1]    -> ajusta el sesgo según el signo.

El sesgo se guarda por etiqueta. Al generar, la intensidad base de una viñeta se corrige con la suma de
los sesgos de sus etiquetas, acotada a ±MAX_BIAS. Así una corrección nunca descontrola el generador.

Garantías:
  - Nunca aprende de viñetas con indicios de menores (seguridad.minor_hits): el registro se rechaza.
  - El ajuste total queda acotado (MAX_BIAS) y la intensidad final siempre está en [0, 1].
  - Guardado atómico (archivo temporal + reemplazo): una escritura interrumpida no corrompe el historial.
  - Si el archivo está dañado, se guarda una copia .corrupto y se empieza vacío.
"""
import json
import os
import tempfile
import time

from seguridad import minor_hits, norm

LEARN_RATE = 0.05        # cuánto cambia el sesgo de una etiqueta por corrección
SCALE = 0.1              # convierte la suma de sesgos en ajuste de intensidad
MAX_BIAS = 0.30          # ajuste máximo total sobre la intensidad base
MAX_RECORDS = 500        # historial acotado
KINDS_FIXED = {"falta": 1.0, "sobra": -1.0}


class RechazadoError(ValueError):
    """La corrección no se puede aprender (p. ej. viñeta con indicios de menores)."""


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


class Aprendizaje:
    def __init__(self, path):
        self.path = path
        self.bias = {}          # etiqueta normalizada -> sesgo en [-1, 1]
        self.records = []       # historial de correcciones (para revisar y deshacer a mano)
        self._load()

    # ---------- registro ----------

    def registrar(self, gallery_id, page, tags, kind, delta=None):
        """Registra una corrección. Devuelve el valor aplicado (en [-1, 1])."""
        tags = [str(t) for t in tags]
        if minor_hits(tags):
            raise RechazadoError("La viñeta tiene indicios de personajes menores: no se aprende de ella.")
        if kind in KINDS_FIXED:
            valor = KINDS_FIXED[kind]
        elif kind == "intensidad":
            if delta is None:
                raise ValueError("La corrección de intensidad necesita un delta.")
            valor = _clamp(float(delta), -1.0, 1.0)
        else:
            raise ValueError(f"Tipo de corrección desconocido: {kind}")

        for t in {norm(t) for t in tags if norm(t)}:
            self.bias[t] = _clamp(self.bias.get(t, 0.0) + LEARN_RATE * valor, -1.0, 1.0)

        self.records.append({"t": int(time.time()), "gallery": str(gallery_id), "page": int(page),
                             "tags": sorted({norm(t) for t in tags if norm(t)}),
                             "kind": kind, "valor": round(valor, 3)})
        del self.records[:-MAX_RECORDS]
        self._save()
        return valor

    # ---------- aplicación ----------

    def ajuste(self, tags):
        """Ajuste de intensidad para unas etiquetas, acotado a ±MAX_BIAS."""
        s = sum(self.bias.get(norm(t), 0.0) for t in tags)
        return _clamp(s * SCALE, -MAX_BIAS, MAX_BIAS)

    def ajustar(self, base, tags):
        """Intensidad corregida, siempre en [0, 1]."""
        return _clamp(float(base) + self.ajuste(tags), 0.0, 1.0)

    def decide(self, score, tags, umbral=0.35):
        """¿Debe haber movimiento en esta viñeta? Aplica el mismo ajuste al puntaje."""
        return float(score) + self.ajuste(tags) >= umbral

    # ---------- persistencia ----------

    def _load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self.bias = {str(k): _clamp(float(v), -1.0, 1.0) for k, v in data.get("bias", {}).items()}
            self.records = list(data.get("records", []))[-MAX_RECORDS:]
        except (ValueError, TypeError, AttributeError, OSError):
            try:
                os.replace(self.path, self.path + ".corrupto")
            except OSError:
                pass
            self.bias, self.records = {}, []

    def _save(self):
        folder = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".aprendizaje.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "bias": self.bias, "records": self.records},
                          f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
