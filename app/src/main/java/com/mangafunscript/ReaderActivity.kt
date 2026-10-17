package com.mangafunscript

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Matrix
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.speech.tts.TextToSpeech
import android.view.GestureDetector
import android.view.Gravity
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.PopupMenu
import android.widget.TextView
import android.widget.Toast
import com.chaquo.python.Python
import com.chaquo.python.PyObject
import com.google.mlkit.common.model.DownloadConditions
import com.google.mlkit.nl.translate.TranslateLanguage
import com.google.mlkit.nl.translate.Translation
import com.google.mlkit.nl.translate.Translator
import com.google.mlkit.nl.translate.TranslatorOptions
import org.json.JSONObject
import java.io.File
import java.util.Locale
import kotlin.math.max

/**
 * Lector de la galería importada.
 *  - Páginas en orden, decodificadas al tamaño de pantalla (ahorro de memoria).
 *  - Zoom con pellizco, arrastre con el dedo y doble toque para ajustar.
 *  - Menú ☰ con acciones generales.
 *  - Conexión a Intiface Central y bucle del funscript de cada página.
 *  - Cuadro de traducción arrastrable (barra «Mover»), editable y guardado por página.
 *  - Lectura en voz alta del cuadro con el TTS de Android.
 *  - Persistencia: posición del cuadro, URL de Intiface y traducción por página.
 */
class ReaderActivity : Activity(), TextToSpeech.OnInitListener {

    companion object {
        const val EXTRA_FOLDER = "folder"
        const val EXTRA_TITLE = "title"
        private const val PREFS = "reader"
        private const val KEY_URL = "intiface_url"
        private const val KEY_BOX_X = "box_x"
        private const val KEY_BOX_Y = "box_y"
        private const val WRAP = ViewGroup.LayoutParams.WRAP_CONTENT
        private const val MATCH = ViewGroup.LayoutParams.MATCH_PARENT
        private const val MAX_ZOOM = 5f
    }

    private var pages: List<File> = emptyList()
    private var index = 0
    private var title = ""
    private var folderPath = ""
    private var current: Bitmap? = null
    private var tts: TextToSpeech? = null
    private var dragDx = 0f
    private var dragDy = 0f

    // Zoom y arrastre de la imagen
    private val matrix = Matrix()
    private var minScale = 1f
    private lateinit var scaleDetector: ScaleGestureDetector
    private lateinit var gestures: GestureDetector

    private lateinit var image: ImageView
    private lateinit var label: TextView
    private lateinit var status: TextView
    private lateinit var urlField: EditText
    private lateinit var box: LinearLayout
    private lateinit var boxText: EditText
    private lateinit var sourceField: EditText
    private var translator: Translator? = null
    private val prefs: SharedPreferences by lazy { getSharedPreferences(PREFS, Context.MODE_PRIVATE) }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()
    private fun py(): PyObject = Python.getInstance().getModule("bridge")
    private fun lp(w: Int, h: Int, weight: Float = 0f) = LinearLayout.LayoutParams(w, h, weight)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = intent.getStringExtra(EXTRA_TITLE).orEmpty()
        folderPath = intent.getStringExtra(EXTRA_FOLDER).orEmpty()
        pages = File(folderPath).listFiles { f -> f.name.endsWith(".webp") }?.sortedBy { it.name } ?: emptyList()
        tts = TextToSpeech(this, this)

        image = ImageView(this).apply {
            scaleType = ImageView.ScaleType.MATRIX
            setBackgroundColor(Color.BLACK)
        }
        setupZoom()

        label = TextView(this).apply {
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            setPadding(dp(8), dp(8), dp(8), dp(8))
        }
        status = TextView(this).apply {
            setTextColor(Color.LTGRAY)
            textSize = 12f
            setPadding(dp(8), 0, dp(8), dp(4))
            text = "Intiface: sin conectar"
        }
        urlField = EditText(this).apply {
            setText(prefs.getString(KEY_URL, "ws://127.0.0.1:12345"))
            setSingleLine(true)
            textSize = 12f
            setTextColor(Color.WHITE)
        }

        val menuBtn = Button(this).apply { text = "☰"; setOnClickListener { openMenu(this) } }
        val connectBtn = Button(this).apply { text = "Conectar"; setOnClickListener { connectIntiface() } }
        val boxBtn = Button(this).apply { text = "Traducción"; setOnClickListener { toggleBox() } }
        val speakBtn = Button(this).apply { text = "Leer"; setOnClickListener { speakBox() } }
        val prev = Button(this).apply { text = "◀"; setOnClickListener { show(index - 1) } }
        val next = Button(this).apply { text = "▶"; setOnClickListener { show(index + 1) } }

        val topBar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(menuBtn, lp(0, WRAP, 0.8f))
            addView(urlField, lp(0, WRAP, 3f))
            addView(connectBtn, lp(0, WRAP, 1.2f))
            addView(boxBtn, lp(0, WRAP, 1.2f))
            addView(speakBtn, lp(0, WRAP, 1f))
        }
        val navBar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(prev, lp(0, WRAP, 1f))
            addView(label, lp(0, WRAP, 2f))
            addView(next, lp(0, WRAP, 1f))
        }
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.BLACK)
            addView(topBar, lp(MATCH, WRAP))
            addView(status, lp(MATCH, WRAP))
            addView(image, lp(MATCH, 0, 1f))
            addView(navBar, lp(MATCH, WRAP))
        }

        box = buildBox()
        box.visibility = View.GONE
        val overlay = FrameLayout(this)
        overlay.addView(content, FrameLayout.LayoutParams(MATCH, MATCH))
        overlay.addView(box, FrameLayout.LayoutParams(dp(260), WRAP))
        setContentView(overlay)

        box.post {
            box.x = prefs.getFloat(KEY_BOX_X, dp(16).toFloat())
            box.y = prefs.getFloat(KEY_BOX_Y, dp(160).toFloat())
        }

        if (pages.isEmpty()) {
            label.text = "Galería vacía"
        } else {
            show(0)
        }
    }

    // ---------- zoom y arrastre de la imagen ----------

    private fun setupZoom() {
        scaleDetector = ScaleGestureDetector(this, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
            override fun onScale(d: ScaleGestureDetector): Boolean {
                val cur = currentScale()
                val target = (cur * d.scaleFactor).coerceIn(minScale, minScale * MAX_ZOOM)
                val real = target / cur
                matrix.postScale(real, real, d.focusX, d.focusY)
                applyMatrix()
                return true
            }
        })
        gestures = GestureDetector(this, object : GestureDetector.SimpleOnGestureListener() {
            override fun onDoubleTap(e: MotionEvent): Boolean {
                fitImage()
                return true
            }

            override fun onScroll(e1: MotionEvent?, e2: MotionEvent, dx: Float, dy: Float): Boolean {
                if (currentScale() > minScale + 0.01f) {
                    matrix.postTranslate(-dx, -dy)
                    applyMatrix()
                }
                return true
            }
        })
        image.setOnTouchListener { _, ev ->
            scaleDetector.onTouchEvent(ev)
            gestures.onTouchEvent(ev)
            true
        }
    }

    private fun currentScale(): Float {
        val v = FloatArray(9)
        matrix.getValues(v)
        return v[Matrix.MSCALE_X]
    }

    private fun applyMatrix() {
        image.imageMatrix = matrix
    }

    /** Ajusta la página a la pantalla, centrada. */
    private fun fitImage() {
        val d = image.drawable ?: return
        val vw = image.width.toFloat()
        val vh = image.height.toFloat()
        if (vw == 0f || vh == 0f) return
        val bw = d.intrinsicWidth.toFloat()
        val bh = d.intrinsicHeight.toFloat()
        val s = minOf(vw / bw, vh / bh)
        minScale = s
        matrix.reset()
        matrix.postScale(s, s)
        matrix.postTranslate((vw - bw * s) / 2f, (vh - bh * s) / 2f)
        applyMatrix()
    }

    // ---------- menú ☰ ----------

    private fun openMenu(anchor: View) {
        val pm = PopupMenu(this, anchor)
        pm.menu.add(0, 1, 0, "Restablecer zoom")
        pm.menu.add(0, 2, 1, "Mostrar ruta de la galería")
        pm.menu.add(0, 3, 2, "Mostrar/ocultar traducción")
        pm.menu.add(0, 4, 3, "Ajustes del sistema")
        pm.menu.add(0, 5, 4, "Cerrar lector")
        pm.menu.add(0, 6, 5, "Corregir: debía haber funscript aquí")
        pm.menu.add(0, 7, 6, "Corregir: no debía haber funscript aquí")
        pm.setOnMenuItemClickListener { item ->
            when (item.itemId) {
                1 -> fitImage()
                2 -> Toast.makeText(this, folderPath, Toast.LENGTH_LONG).show()
                3 -> toggleBox()
                4 -> startActivity(Intent(
                    Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                    Uri.parse("package:$packageName")))
                5 -> finish()
                6 -> correct("falta")
                7 -> correct("sobra")
            }
            true
        }
        pm.show()
    }

    // ---------- aprendizaje ----------

    private fun correct(kind: String) {
        val page = index + 1
        Thread {
            try {
                val res = JSONObject(py().callAttr("correccion", folderPath, page, kind).toString())
                val msg = if (res.optBoolean("ok")) "Corrección guardada: el generador aprenderá de ella"
                          else res.optString("message", "No se pudo guardar la corrección")
                runOnUiThread { Toast.makeText(this, msg, Toast.LENGTH_LONG).show() }
            } catch (e: Exception) {
                runOnUiThread { Toast.makeText(this, "Error: ${e.message}", Toast.LENGTH_LONG).show() }
            }
        }.start()
    }

    // ---------- traducción en el dispositivo (ML Kit) ----------

    private fun ensureTranslator(): Translator {
        translator?.let { return it }
        val opts = TranslatorOptions.Builder()
            .setSourceLanguage(TranslateLanguage.JAPANESE)
            .setTargetLanguage(TranslateLanguage.SPANISH)
            .build()
        return Translation.getClient(opts).also { translator = it }
    }

    /** Traduce el texto original escrito en el campo superior y lo pone en el cuadro. No sale del teléfono. */
    private fun translateSource() {
        val src = sourceField.text.toString().trim()
        if (src.isEmpty()) {
            Toast.makeText(this, "Escribe primero el texto original", Toast.LENGTH_SHORT).show()
            return
        }
        val t = ensureTranslator()
        setStatus("Traducción: preparando modelo japonés → español…")
        t.downloadModelIfNeeded(DownloadConditions.Builder().build())
            .addOnSuccessListener {
                t.translate(src)
                    .addOnSuccessListener { out ->
                        boxText.setText(out)
                        setStatus("Traducción lista (en el teléfono)")
                    }
                    .addOnFailureListener { e -> setStatus("Traducción: error (${e.message})") }
            }
            .addOnFailureListener { e -> setStatus("Traducción: no se pudo preparar el modelo (${e.message})") }
    }

    // ---------- cuadro de traducción ----------

    private fun buildBox(): LinearLayout {
        val handle = TextView(this).apply {
            text = "⠿ Mover"
            setTextColor(Color.BLACK)
            setBackgroundColor(Color.parseColor("#FFD54F"))
            setPadding(dp(8), dp(6), dp(8), dp(6))
            setOnTouchListener { _, ev -> onDragTouch(ev) }
        }
        boxText = EditText(this).apply {
            hint = "Traducción…"
            setTextColor(Color.BLACK)
            setHintTextColor(Color.GRAY)
            setBackgroundColor(Color.WHITE)
            minLines = 3
            gravity = Gravity.TOP
        }
        sourceField = EditText(this).apply {
            hint = "Texto original (japonés)"
            setTextColor(Color.BLACK)
            setHintTextColor(Color.GRAY)
            setBackgroundColor(Color.WHITE)
            minLines = 2
            gravity = Gravity.TOP
        }
        val translateBtn = Button(this).apply { text = "Traducir"; setOnClickListener { translateSource() } }
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#E6FFFFFF"))
            addView(handle, lp(MATCH, WRAP))
            addView(sourceField, lp(MATCH, WRAP))
            addView(translateBtn, lp(MATCH, WRAP))
            addView(boxText, lp(MATCH, WRAP))
        }
    }

    private fun onDragTouch(ev: MotionEvent): Boolean {
        val parent = box.parent as? View ?: return false
        return when (ev.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                dragDx = ev.rawX - box.x
                dragDy = ev.rawY - box.y
                true
            }
            MotionEvent.ACTION_MOVE -> {
                box.x = clamp(ev.rawX - dragDx, parent.width - box.width)
                box.y = clamp(ev.rawY - dragDy, parent.height - box.height)
                true
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                prefs.edit().putFloat(KEY_BOX_X, box.x).putFloat(KEY_BOX_Y, box.y).apply()
                true
            }
            else -> false
        }
    }

    private fun clamp(v: Float, limit: Int): Float = v.coerceIn(0f, max(0, limit).toFloat())

    private fun toggleBox() {
        box.visibility = if (box.visibility == View.VISIBLE) View.GONE else View.VISIBLE
    }

    private fun speakBox() {
        tts?.speak(boxText.text.toString(), TextToSpeech.QUEUE_FLUSH, null, "pagina")
    }

    override fun onInit(st: Int) {
        if (st == TextToSpeech.SUCCESS) tts?.language = Locale("es", "ES")
    }

    // ---------- Intiface ----------

    private fun setStatus(msg: String) = runOnUiThread { status.text = msg }

    private fun connectIntiface() {
        val url = urlField.text.toString().trim()
        prefs.edit().putString(KEY_URL, url).apply()
        setStatus("Intiface: conectando…")
        Thread {
            try {
                py().callAttr("intiface_connect", url)
                var st = JSONObject()
                var tries = 0
                while (tries < 25) {          // hasta ~10 s
                    Thread.sleep(400)
                    st = JSONObject(py().callAttr("intiface_status").toString())
                    tries++
                    if (st.optBoolean("connected") && (st.optJSONArray("channels")?.length() ?: 0) > 0) break
                }
                val text = when {
                    !st.optBoolean("connected") -> "Intiface: no conectado (${st.optString("log")})"
                    st.optString("selected").isEmpty() ->
                        "Intiface: servidor conectado, sin dispositivos. ¿Conectaste el juguete en Intiface Central?"
                    else -> "Intiface: ${st.optString("selected")}"
                }
                setStatus(text)
            } catch (e: Exception) {
                setStatus("Intiface: error (${e.message})")
            }
        }.start()
    }

    private fun playPage() {
        val fs = File(folderPath, "funscripts/%03d.funscript".format(index + 1))
        Thread {
            try {
                py().callAttr("play_page", fs.absolutePath)   // sin conexión o sin funscript: no hace nada
            } catch (_: Exception) {
            }
        }.start()
    }

    // ---------- páginas ----------

    private fun trKey(i: Int) = "tr|$folderPath|$i"

    private fun saveTranslation() {
        if (pages.isNotEmpty() && ::boxText.isInitialized) {
            prefs.edit().putString(trKey(index), boxText.text.toString()).apply()
        }
    }

    private fun show(i: Int) {
        if (pages.isEmpty()) return
        saveTranslation()
        index = i.coerceIn(0, pages.size - 1)

        // Decodificación al tamaño de pantalla y en RGB_565: menos memoria por página.
        val maxW = resources.displayMetrics.widthPixels
        val maxH = resources.displayMetrics.heightPixels
        val file = pages[index]
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.path, bounds)
        var sample = 1
        while (bounds.outWidth / (sample * 2) >= maxW && bounds.outHeight / (sample * 2) >= maxH) sample *= 2
        val opts = BitmapFactory.Options().apply {
            inSampleSize = sample
            inPreferredConfig = Bitmap.Config.RGB_565
        }
        val bmp = BitmapFactory.decodeFile(file.path, opts)
        image.setImageBitmap(bmp)
        image.post { fitImage() }
        current?.recycle()
        current = bmp

        label.text = "$title  ${index + 1} / ${pages.size}"
        boxText.setText(prefs.getString(trKey(index), ""))
        playPage()   // el bucle anterior se detiene y arranca el de esta página
    }

    override fun onPause() {
        saveTranslation()
        Thread { try { py().callAttr("stop_play") } catch (_: Exception) {} }.start()
        super.onPause()
    }

    override fun onDestroy() {
        translator?.close()
        tts?.shutdown()
        image.setImageBitmap(null)
        current?.recycle()
        current = null
        super.onDestroy()
    }

    @Deprecated("Compatible con API 26-34")
    override fun onBackPressed() {
        finish()
    }
}
