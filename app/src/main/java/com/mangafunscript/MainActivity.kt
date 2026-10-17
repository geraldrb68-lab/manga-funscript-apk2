package com.mangafunscript

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.ProgressBar
import android.widget.Toast
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import java.io.File

/**
 * Navegador (WebView) con hitomi.la por defecto.
 * Al entrar en una galería: se importa con el núcleo Python y se abre el lector.
 * Al volver del lector se restaura la posición de scroll exacta.
 */
class MainActivity : Activity() {

    companion object {
        const val HOME_URL = "https://hitomi.la/"
        // Mismo patrón que hitomi_gallery._REF_RE del proyecto (sin distinguir mayúsculas).
        val GALLERY_RE = Regex("""^https?://(?:www\.)?hitomi\.la/(?:reader|galleries)/(\d+)\.html""", RegexOption.IGNORE_CASE)
        private const val STATE_WEB = "web_state"
    }

    private lateinit var web: WebView
    private lateinit var spinner: ProgressBar
    private var pendingScrollY: Int? = null
    private var importing = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!Python.isStarted()) Python.start(AndroidPlatform(this))

        web = WebView(this)
        spinner = ProgressBar(this).apply { visibility = View.GONE }
        val root = FrameLayout(this)
        root.addView(web, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
        root.addView(spinner, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT, Gravity.CENTER))
        setContentView(root)

        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            cacheMode = WebSettings.LOAD_DEFAULT
            builtInZoomControls = true
            displayZoomControls = false
        }
        CookieManager.getInstance().setAcceptCookie(true)
        web.webChromeClient = WebChromeClient()
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url.toString()
                if (!GALLERY_RE.containsMatchIn(url)) return false
                importGallery(url)
                return true
            }
        }

        if (savedInstanceState != null) {
            web.restoreState(savedInstanceState.getBundle(STATE_WEB) ?: Bundle())
        } else {
            web.loadUrl(HOME_URL)
        }
    }

    /** Guarda el scroll, importa la galería en segundo plano y abre el lector. */
    private fun importGallery(url: String) {
        if (importing) return
        importing = true
        spinner.visibility = View.VISIBLE
        web.evaluateJavascript("window.scrollY") { raw ->
            pendingScrollY = raw?.toDoubleOrNull()?.toInt() ?: 0
            Thread {
                val result = try {
                    val lib = File(filesDir, "biblioteca").absolutePath
                    val json = Python.getInstance().getModule("bridge")
                        .callAttr("import_gallery", url, lib).toString()
                    JSONObject(json)
                } catch (e: Exception) {
                    JSONObject().put("ok", false).put("message", e.toString())
                }
                runOnUiThread {
                    importing = false
                    spinner.visibility = View.GONE
                    if (result.optBoolean("ok")) {
                        startActivity(Intent(this, ReaderActivity::class.java)
                            .putExtra(ReaderActivity.EXTRA_FOLDER, result.getString("folder"))
                            .putExtra(ReaderActivity.EXTRA_TITLE, result.optString("title")))
                    } else {
                        pendingScrollY = null
                        Toast.makeText(this, result.optString("message", "Error al importar"), Toast.LENGTH_LONG).show()
                    }
                }
            }.start()
        }
    }

    override fun onResume() {
        super.onResume()
        pendingScrollY?.let { y ->
            web.evaluateJavascript("window.scrollTo(0, $y)", null)
            pendingScrollY = null
        }
    }

    /** Atrás dentro del navegador: usa el historial web nativo. */
    @Deprecated("Compatible con API 26-34")
    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else super.onBackPressed()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        val webState = Bundle()
        web.saveState(webState)
        outState.putBundle(STATE_WEB, webState)
    }

    override fun onDestroy() {
        web.destroy()
        super.onDestroy()
    }
}
