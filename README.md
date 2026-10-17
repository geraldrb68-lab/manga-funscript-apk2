# Manga Funscript — APK, Fase 3 (Intiface, funscript por página, traducción, TTS)

## Qué hace
- **Navegador** hitomi.la, Atrás nativo, restauración del scroll (Fase 1).
- **Importar galería** con el código Python original (Fase 2).
- **Lector**:
  - **Intiface Central** en el mismo teléfono: pulsa «Conectar» (URL por defecto `ws://127.0.0.1:12345`).
  - **Bucle por página**: `funscripts/001.funscript`, `002.funscript`… dentro de la carpeta de la galería.
    El funscript de la página se repite hasta que cambias de página; al cambiar, se sustituye por el de la nueva.
  - **Cuadro de traducción** arrastrable por su barra «⠿ Mover»; texto editable, guardado por página.
  - **Leer** en voz alta el cuadro con el TTS de Android (español).
  - Persistencia: posición del cuadro, URL de Intiface y traducción de cada página.

## Lo que NO está todavía (y por qué)
- **Generación de funscript desde las páginas**: `funscript_gen` → `motion_strategies` importa `cv2` y `tagger` (ONNX).
  Hay que portar la detección de paneles a Android. Por ahora, los funscripts se colocan a mano en `funscripts/`.
- **OCR**: el original usa `pytesseract`, `manga_ocr` y `text_regions`/`ocr_verify` (unas 1 200 líneas). Requiere ML Kit y la lógica de verificación.
- **Etiquetador ONNX** (`tagger.py`).
- **RVC y clonación de voz**: fuera de la v1 (decisión D1).
- **Menús hamburguesa**, gestos de zoom, reproductor completo con audio y SFX (`player.py`).
- **Traducción automática**: el cuadro solo muestra y guarda lo que escribes.

## Cómo probarla
1. Importa una galería desde el navegador.
2. Crea la carpeta `funscripts/` dentro de la galería (en el almacenamiento interno de la app) y coloca
   `001.funscript`… con el formato estándar `{"actions":[{"at":0,"pos":0},{"at":500,"pos":100}]}`.
3. En Intiface Central, conecta el juguete. En la APK, pulsa «Conectar».
4. Cambia de página: el funscript de la nueva página empieza en bucle.

## Estado
- **Sin compilar**. Revisado a mano, pero sin SDK de Android en el entorno. Errores pequeños son probables.
- Versiones por verificar: Chaquopy 15.0.1, AGP 8.5.2, Kotlin 2.0.20, Gradle 8.7.
- `websockets` y `requests` se instalan vía Chaquopy.
