# Port de text_regions.py (OpenCV -> numpy + scipy)

## Qué es
`app/src/main/python/text_regions.py` es el detector de texto del original, con la misma lógica y los mismos
nombres de funciones. Las 38 llamadas a OpenCV se sustituyen por `cvcompat.py`, que reimplementa cada operación
con numpy y scipy (ambos disponibles en Chaquopy). **No hace falta OpenCV en el APK.**

## Cómo se validó
Cada operación de OpenCV se comparó con su equivalente en 12 páginas sintéticas tipo manga (globos, cajas,
texto suelto, onomatopeyas, tramas de puntos y rayas). Las pruebas están en `tests_python/`.

| Operación | Resultado medido |
|---|---|
| Gris (BGR2GRAY) | ±1 nivel |
| Lab (BGR2LAB) | ±2 niveles |
| Desenfoque 3×3 | ±1 nivel |
| Umbral adaptativo | idéntico (0 píxeles distintos) |
| Componentes conectados (4 y 8) | idénticos (etiquetas y estadísticas) |
| Apertura y dilatación elípticas/cuadradas, pares e impares | idénticas |
| Mediana 3×3 y gradiente | idénticos |
| Ampliación cúbica | ±1 nivel |
| Reducción (escalas enteras) | ±1 nivel |
| Reducción (escalas no enteras) | difiere en los bordes de las letras (ver abajo) |
| Propiedades de contorno (área, envolvente, bbox) | área de relleno exacta; polígono ±2 px² |

**Resultado sobre las páginas de prueba:**
- Bloques de texto: 33 encontrados por el original, 33 por el port, todos emparejados.
- Tipo (globo/caja/libre) y polaridad: 33 de 33 iguales.
- Onomatopeyas: 15 y 15.
- Máscaras de letras: 3 píxeles distintos en todo el conjunto.
- Imagen limpia (`clean_crop`): ampliaciones sin ningún píxel con diferencia mayor de 20 niveles.

## Diferencia conocida (no resuelta)
En la **reducción con escala no entera**, la última columna o fila de píxeles de salida difiere de OpenCV.
Afecta a un 0,2 % de los píxeles de los recortes reducidos, solo en los bordes de las letras. Probé tres
variantes del tramo final de la correspondencia y ninguna coincidió exactamente. Se mantiene la más cercana.
Las escalas enteras y las ampliaciones son exactas. Si el OCR real muestra diferencias, esta es la primera
sospecha.

## Qué NO está hecho todavía
- La lectura de cada bloque con ML Kit (japonés) y su unión con `ocr_verify`. Es el siguiente paso.
- La validación con páginas reales en japonés. La prueba usa páginas sintéticas: sirve para comprobar la
  lógica, no la calidad sobre manga real.
