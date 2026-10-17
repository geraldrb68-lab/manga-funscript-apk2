plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "com.mangafunscript"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.mangafunscript"
        minSdk = 26            // D4 propuesto; pendiente de confirmar
        targetSdk = 34
        versionCode = 2
        versionName = "0.2.0-fase2"
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a") }   // sin x86: ahorra tamaño
    }

    buildTypes {
        release { isMinifyEnabled = false }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

chaquopy {
    defaultConfig {
        version = "3.11"
        pip { install("requests"); install("websockets"); install("numpy") }
    }
}

dependencies {
    // Traducción en el dispositivo (japonés -> español). Versión a verificar en Maven.
    implementation("com.google.mlkit:translate:17.0.3")
}
