# Plan 2b-i — Android Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Android project skeleton: multi-module Gradle, Deep Botanical Material 3 theme, network/database/auth core, app shell with bottom nav, and a working auth bootstrap that talks to the Plan 2a backend. Ships an installable app that boots, applies the brand theme, signs the user in via Firebase, and shows placeholder Home/Orders/Settings tabs.

**Architecture:** Multi-module Gradle (`:app`, `:core:ui`, `:core:common`, `:core:network`, `:core:database`). MVVM with sealed-class intents and `StateFlow`. Hilt with KSP for DI across modules. Retrofit + OkHttp for the API; Room with Flow for local cache; Firebase Auth for identity. Convention plugins in `build-logic/` share Compose/Hilt/Kotlin config.

**Tech Stack:** Kotlin 2.0.21, AGP 8.6.1, Gradle 8.10, Compose BOM 2024.10.01, Hilt 2.52, Room 2.6.1, Retrofit 2.11.0, OkHttp 4.12.0, kotlinx-serialization 1.7.3, Firebase BOM 33.5.1, MockK 1.13.13, Turbine 1.2.0, JUnit 5.11.

**Repo:** `/Users/sdagguba/kibble-reorder/android/`

**Spec:** `/Users/sdagguba/sasank-playground/docs/superpowers/specs/2026-04-30-kibble-android-app-design.md`
**Design system:** `/Users/sdagguba/sasank-playground/docs/superpowers/specs/assets/2026-04-30-kibble-design-system.md`
**Backend (Plan 2a) endpoints:** `POST /auth/firebase`, `GET /users/me`, `PATCH /users/{id}`, `POST /users/{id}/dogs|bins`, `POST/GET/DELETE /users/{id}/retailer-sessions`, `PATCH /users/{id}/quiet-hours`, `POST /bins/{id}/readings`, `GET /bins/{id}/forecast`, `POST /bins/{id}/calibrate-empty`

---

## Prerequisites

The implementer must verify before starting:
- Plan 2a is implemented (run `pytest -v` in `/Users/sdagguba/kibble-reorder/backend/` and confirm green)
- The user has created a Firebase project at https://console.firebase.google.com and downloaded `google-services.json` (placed it at `/Users/sdagguba/kibble-reorder/android/app/google-services.json` — gitignored)
- The user has enabled Email/Password and Phone sign-in providers in Firebase Auth console
- A Firebase service-account JSON exists for the backend (referenced in Plan 2a `FIREBASE_CREDENTIALS_PATH`)
- Android SDK 35 installed; Java 21 in `JAVA_HOME`

If any of these are missing, halt and ask the user.

---

## File Structure

```
/Users/sdagguba/kibble-reorder/android/
├── build.gradle.kts                       (root build script)
├── settings.gradle.kts                    (module list + plugin management)
├── gradle.properties                      (JVM args, AndroidX flag, Kotlin code style)
├── gradle/
│   ├── libs.versions.toml                 (version catalog)
│   └── wrapper/
│       ├── gradle-wrapper.properties
│       └── gradle-wrapper.jar
├── gradlew, gradlew.bat
├── .gitignore                             (Android + IDE artifacts; google-services.json)
├── build-logic/
│   ├── settings.gradle.kts
│   └── convention/
│       ├── build.gradle.kts
│       └── src/main/kotlin/
│           ├── KibbleAndroidLibraryConvention.kt
│           ├── KibbleComposeConvention.kt
│           ├── KibbleHiltConvention.kt
│           └── KotlinAndroid.kt           (shared kotlinOptions / android { } block)
├── app/
│   ├── build.gradle.kts
│   ├── google-services.json               (gitignored — user-provided)
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── res/
│       │   ├── values/strings.xml
│       │   ├── values/colors.xml
│       │   └── values/font_certs.xml      (Google Fonts provider certs)
│       └── kotlin/com/kibble/
│           ├── KibbleApplication.kt
│           ├── MainActivity.kt
│           ├── auth/
│           │   ├── AuthState.kt
│           │   ├── AuthBootstrapViewModel.kt
│           │   └── AuthBootstrapScreen.kt
│           ├── navigation/
│           │   ├── KibbleDestinations.kt
│           │   ├── KibbleNavHost.kt
│           │   └── KibbleBottomNav.kt
│           └── home/, orders/, settings/  (placeholder Composables only in this plan)
├── core/
│   ├── ui/
│   │   ├── build.gradle.kts
│   │   └── src/main/kotlin/com/kibble/core/ui/
│   │       └── theme/
│   │           ├── Color.kt
│   │           ├── Type.kt
│   │           ├── Shape.kt
│   │           └── KibbleTheme.kt
│   ├── common/
│   │   ├── build.gradle.kts
│   │   └── src/main/kotlin/com/kibble/core/common/
│   │       ├── Result.kt
│   │       ├── DispatcherProvider.kt
│   │       └── di/CommonModule.kt
│   ├── network/
│   │   ├── build.gradle.kts
│   │   └── src/main/kotlin/com/kibble/core/network/
│   │       ├── KibbleApi.kt
│   │       ├── AuthInterceptor.kt
│   │       ├── FirebaseTokenProvider.kt
│   │       ├── di/NetworkModule.kt
│   │       └── dto/
│   │           ├── AuthDto.kt
│   │           ├── UserDto.kt
│   │           ├── DogDto.kt
│   │           ├── BinDto.kt
│   │           ├── ForecastDto.kt
│   │           └── RetailerSessionDto.kt
│   └── database/
│       ├── build.gradle.kts
│       └── src/main/kotlin/com/kibble/core/database/
│           ├── KibbleDatabase.kt
│           ├── di/DatabaseModule.kt
│           ├── entity/
│           │   ├── UserEntity.kt
│           │   ├── DogEntity.kt
│           │   ├── BinEntity.kt
│           │   ├── SensorReadingEntity.kt
│           │   ├── OrderEntity.kt
│           │   └── RetailerSessionEntity.kt
│           └── dao/
│               ├── UserDao.kt
│               ├── DogDao.kt
│               ├── BinDao.kt
│               ├── SensorReadingDao.kt
│               ├── OrderDao.kt
│               └── RetailerSessionDao.kt
```

---

## Task 1: Initialize Android project skeleton

**Files:**
- Create: `/Users/sdagguba/kibble-reorder/android/.gitignore`
- Create: `/Users/sdagguba/kibble-reorder/android/settings.gradle.kts`
- Create: `/Users/sdagguba/kibble-reorder/android/build.gradle.kts`
- Create: `/Users/sdagguba/kibble-reorder/android/gradle.properties`
- Create: `/Users/sdagguba/kibble-reorder/android/gradle/wrapper/gradle-wrapper.properties`
- Create: `/Users/sdagguba/kibble-reorder/android/gradlew`, `gradlew.bat` (Gradle wrapper scripts)

- [ ] **Step 1: Make the directory and seed `.gitignore`**

```bash
mkdir -p /Users/sdagguba/kibble-reorder/android
cd /Users/sdagguba/kibble-reorder/android
```

Create `.gitignore`:

```
# Built application files
*.apk
*.aar
*.ap_
*.aab

# Gradle
.gradle/
build/
local.properties

# IntelliJ
*.iml
.idea/
captures/

# Keystore files
*.jks
*.keystore

# Firebase
app/google-services.json

# Android Studio
.cxx/
.kotlin/
```

- [ ] **Step 2: Create `gradle.properties`**

```
org.gradle.jvmargs=-Xmx4g -Dfile.encoding=UTF-8 -XX:+UseParallelGC
org.gradle.parallel=true
org.gradle.caching=true
org.gradle.configuration-cache=true
android.useAndroidX=true
android.nonTransitiveRClass=true
android.nonFinalResIds=true
kotlin.code.style=official
```

- [ ] **Step 3: Initialize the Gradle wrapper**

Run from `/Users/sdagguba/kibble-reorder/android/`:

```bash
gradle wrapper --gradle-version 8.10 --distribution-type bin
```

If `gradle` is not on PATH, install via `brew install gradle` first, or download the 8.10 wrapper jar manually from `https://services.gradle.org/distributions/gradle-8.10-bin.zip` and extract `gradle-wrapper.jar`/`.properties` into `gradle/wrapper/`.

Verify:
```bash
./gradlew --version
```
Expected: prints "Gradle 8.10".

- [ ] **Step 4: Create root `settings.gradle.kts`**

```kotlin
pluginManagement {
    includeBuild("build-logic")
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "kibble"

include(":app")
include(":core:ui")
include(":core:common")
include(":core:network")
include(":core:database")
```

- [ ] **Step 5: Create root `build.gradle.kts`**

```kotlin
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.android.library) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.ksp) apply false
    alias(libs.plugins.hilt) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.compose.compiler) apply false
    alias(libs.plugins.google.services) apply false
}
```

- [ ] **Step 6: Verify the project boots**

```bash
./gradlew help
```
Expected: completes successfully (no module-not-found errors yet because we haven't created the modules; just the root project should resolve).

- [ ] **Step 7: Commit**

```bash
cd /Users/sdagguba/kibble-reorder
git add android/.gitignore android/gradle.properties android/settings.gradle.kts android/build.gradle.kts android/gradlew* android/gradle/
git commit -m "feat(android): initialize Gradle multi-module skeleton"
```

---

## Task 2: Version catalog + build-logic convention plugins

**Files:**
- Create: `gradle/libs.versions.toml`
- Create: `build-logic/settings.gradle.kts`
- Create: `build-logic/convention/build.gradle.kts`
- Create: `build-logic/convention/src/main/kotlin/KotlinAndroid.kt`
- Create: `build-logic/convention/src/main/kotlin/KibbleAndroidLibraryConvention.kt`
- Create: `build-logic/convention/src/main/kotlin/KibbleComposeConvention.kt`
- Create: `build-logic/convention/src/main/kotlin/KibbleHiltConvention.kt`

- [ ] **Step 1: Create the version catalog**

Create `/Users/sdagguba/kibble-reorder/android/gradle/libs.versions.toml`:

```toml
[versions]
agp = "8.6.1"
kotlin = "2.0.21"
ksp = "2.0.21-1.0.27"
compose-bom = "2024.10.01"
hilt = "2.52"
hilt-navigation-compose = "1.2.0"
room = "2.6.1"
retrofit = "2.11.0"
okhttp = "4.12.0"
kotlinx-serialization = "1.7.3"
kotlinx-serialization-converter = "1.0.0"
coroutines = "1.9.0"
lifecycle = "2.8.7"
nav-compose = "2.8.4"
firebase-bom = "33.5.1"
google-services = "4.4.2"
junit-jupiter = "5.11.3"
mockk = "1.13.13"
turbine = "1.2.0"
mockwebserver = "4.12.0"
core-ktx = "1.15.0"
activity-compose = "1.9.3"
google-fonts = "1.7.5"
work = "2.10.0"

[libraries]
androidx-core-ktx = { group = "androidx.core", name = "core-ktx", version.ref = "core-ktx" }
androidx-activity-compose = { group = "androidx.activity", name = "activity-compose", version.ref = "activity-compose" }
androidx-lifecycle-runtime-ktx = { group = "androidx.lifecycle", name = "lifecycle-runtime-ktx", version.ref = "lifecycle" }
androidx-lifecycle-viewmodel-compose = { group = "androidx.lifecycle", name = "lifecycle-viewmodel-compose", version.ref = "lifecycle" }
androidx-lifecycle-runtime-compose = { group = "androidx.lifecycle", name = "lifecycle-runtime-compose", version.ref = "lifecycle" }

# Compose
compose-bom = { group = "androidx.compose", name = "compose-bom", version.ref = "compose-bom" }
compose-ui = { group = "androidx.compose.ui", name = "ui" }
compose-ui-graphics = { group = "androidx.compose.ui", name = "ui-graphics" }
compose-ui-tooling = { group = "androidx.compose.ui", name = "ui-tooling" }
compose-ui-tooling-preview = { group = "androidx.compose.ui", name = "ui-tooling-preview" }
compose-material3 = { group = "androidx.compose.material3", name = "material3" }
compose-material-icons-extended = { group = "androidx.compose.material", name = "material-icons-extended" }
compose-google-fonts = { group = "androidx.compose.ui", name = "ui-text-google-fonts", version.ref = "google-fonts" }

# Navigation
nav-compose = { group = "androidx.navigation", name = "navigation-compose", version.ref = "nav-compose" }

# Hilt
hilt-android = { group = "com.google.dagger", name = "hilt-android", version.ref = "hilt" }
hilt-compiler = { group = "com.google.dagger", name = "hilt-android-compiler", version.ref = "hilt" }
hilt-navigation-compose = { group = "androidx.hilt", name = "hilt-navigation-compose", version.ref = "hilt-navigation-compose" }

# Room
room-runtime = { group = "androidx.room", name = "room-runtime", version.ref = "room" }
room-ktx = { group = "androidx.room", name = "room-ktx", version.ref = "room" }
room-compiler = { group = "androidx.room", name = "room-compiler", version.ref = "room" }
room-testing = { group = "androidx.room", name = "room-testing", version.ref = "room" }

# Network
retrofit = { group = "com.squareup.retrofit2", name = "retrofit", version.ref = "retrofit" }
retrofit-kotlinx-serialization = { group = "com.jakewharton.retrofit", name = "retrofit2-kotlinx-serialization-converter", version.ref = "kotlinx-serialization-converter" }
okhttp = { group = "com.squareup.okhttp3", name = "okhttp", version.ref = "okhttp" }
okhttp-logging = { group = "com.squareup.okhttp3", name = "logging-interceptor", version.ref = "okhttp" }
kotlinx-serialization-json = { group = "org.jetbrains.kotlinx", name = "kotlinx-serialization-json", version.ref = "kotlinx-serialization" }

# Coroutines
coroutines-core = { group = "org.jetbrains.kotlinx", name = "kotlinx-coroutines-core", version.ref = "coroutines" }
coroutines-android = { group = "org.jetbrains.kotlinx", name = "kotlinx-coroutines-android", version.ref = "coroutines" }
coroutines-test = { group = "org.jetbrains.kotlinx", name = "kotlinx-coroutines-test", version.ref = "coroutines" }

# WorkManager
work-runtime-ktx = { group = "androidx.work", name = "work-runtime-ktx", version.ref = "work" }
hilt-work = { group = "androidx.hilt", name = "hilt-work", version = "1.2.0" }

# Firebase
firebase-bom = { group = "com.google.firebase", name = "firebase-bom", version.ref = "firebase-bom" }
firebase-auth = { group = "com.google.firebase", name = "firebase-auth-ktx" }
firebase-messaging = { group = "com.google.firebase", name = "firebase-messaging-ktx" }

# Test
junit-jupiter = { group = "org.junit.jupiter", name = "junit-jupiter", version.ref = "junit-jupiter" }
mockk = { group = "io.mockk", name = "mockk", version.ref = "mockk" }
turbine = { group = "app.cash.turbine", name = "turbine", version.ref = "turbine" }
mockwebserver = { group = "com.squareup.okhttp3", name = "mockwebserver", version.ref = "mockwebserver" }

# Build-logic plugin classpath dependencies
android-gradle-plugin = { group = "com.android.tools.build", name = "gradle", version.ref = "agp" }
kotlin-gradle-plugin = { group = "org.jetbrains.kotlin", name = "kotlin-gradle-plugin", version.ref = "kotlin" }
ksp-gradle-plugin = { group = "com.google.devtools.ksp", name = "com.google.devtools.ksp.gradle.plugin", version.ref = "ksp" }
compose-compiler-gradle-plugin = { group = "org.jetbrains.kotlin", name = "compose-compiler-gradle-plugin", version.ref = "kotlin" }

[plugins]
android-application = { id = "com.android.application", version.ref = "agp" }
android-library = { id = "com.android.library", version.ref = "agp" }
kotlin-android = { id = "org.jetbrains.kotlin.android", version.ref = "kotlin" }
kotlin-jvm = { id = "org.jetbrains.kotlin.jvm", version.ref = "kotlin" }
kotlin-serialization = { id = "org.jetbrains.kotlin.plugin.serialization", version.ref = "kotlin" }
ksp = { id = "com.google.devtools.ksp", version.ref = "ksp" }
hilt = { id = "com.google.dagger.hilt.android", version.ref = "hilt" }
compose-compiler = { id = "org.jetbrains.kotlin.plugin.compose", version.ref = "kotlin" }
google-services = { id = "com.google.gms.google-services", version.ref = "google-services" }
```

- [ ] **Step 2: Create build-logic settings**

Create `/Users/sdagguba/kibble-reorder/android/build-logic/settings.gradle.kts`:

```kotlin
dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
    versionCatalogs {
        create("libs") {
            from(files("../gradle/libs.versions.toml"))
        }
    }
}

rootProject.name = "build-logic"
include(":convention")
```

- [ ] **Step 3: Create build-logic convention build script**

Create `/Users/sdagguba/kibble-reorder/android/build-logic/convention/build.gradle.kts`:

```kotlin
plugins {
    `kotlin-dsl`
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    compileOnly(libs.android.gradle.plugin)
    compileOnly(libs.kotlin.gradle.plugin)
    compileOnly(libs.ksp.gradle.plugin)
    compileOnly(libs.compose.compiler.gradle.plugin)
}

gradlePlugin {
    plugins {
        register("kibbleAndroidLibrary") {
            id = "kibble.android.library"
            implementationClass = "KibbleAndroidLibraryConvention"
        }
        register("kibbleCompose") {
            id = "kibble.android.compose"
            implementationClass = "KibbleComposeConvention"
        }
        register("kibbleHilt") {
            id = "kibble.android.hilt"
            implementationClass = "KibbleHiltConvention"
        }
    }
}
```

- [ ] **Step 4: Shared Android config**

Create `/Users/sdagguba/kibble-reorder/android/build-logic/convention/src/main/kotlin/KotlinAndroid.kt`:

```kotlin
import com.android.build.api.dsl.CommonExtension
import org.gradle.api.JavaVersion
import org.gradle.api.Project
import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import org.jetbrains.kotlin.gradle.dsl.KotlinAndroidProjectExtension

internal fun Project.configureKotlinAndroid(
    commonExtension: CommonExtension<*, *, *, *, *, *>,
) {
    commonExtension.apply {
        compileSdk = 35
        defaultConfig {
            minSdk = 26
        }
        compileOptions {
            sourceCompatibility = JavaVersion.VERSION_17
            targetCompatibility = JavaVersion.VERSION_17
        }
    }
    extensions.configure<KotlinAndroidProjectExtension> {
        compilerOptions {
            jvmTarget.set(JvmTarget.JVM_17)
        }
    }
}
```

- [ ] **Step 5: Library convention plugin**

Create `/Users/sdagguba/kibble-reorder/android/build-logic/convention/src/main/kotlin/KibbleAndroidLibraryConvention.kt`:

```kotlin
import com.android.build.gradle.LibraryExtension
import org.gradle.api.Plugin
import org.gradle.api.Project
import org.gradle.kotlin.dsl.configure

class KibbleAndroidLibraryConvention : Plugin<Project> {
    override fun apply(target: Project) {
        with(target) {
            with(pluginManager) {
                apply("com.android.library")
                apply("org.jetbrains.kotlin.android")
            }
            extensions.configure<LibraryExtension> {
                configureKotlinAndroid(this)
                defaultConfig.targetSdk = 35
                testOptions.unitTests.isReturnDefaultValues = true
            }
        }
    }
}
```

- [ ] **Step 6: Compose convention plugin**

Create `/Users/sdagguba/kibble-reorder/android/build-logic/convention/src/main/kotlin/KibbleComposeConvention.kt`:

```kotlin
import com.android.build.api.dsl.CommonExtension
import com.android.build.gradle.LibraryExtension
import org.gradle.api.Plugin
import org.gradle.api.Project
import org.gradle.api.artifacts.VersionCatalogsExtension
import org.gradle.kotlin.dsl.configure
import org.gradle.kotlin.dsl.dependencies
import org.gradle.kotlin.dsl.getByType

class KibbleComposeConvention : Plugin<Project> {
    override fun apply(target: Project) {
        with(target) {
            pluginManager.apply("org.jetbrains.kotlin.plugin.compose")
            extensions.configure<LibraryExtension> {
                buildFeatures {
                    compose = true
                }
            }
            val libs = extensions.getByType<VersionCatalogsExtension>().named("libs")
            dependencies {
                val bom = libs.findLibrary("compose-bom").get()
                add("implementation", platform(bom))
                add("androidTestImplementation", platform(bom))
                add("implementation", libs.findLibrary("compose-ui").get())
                add("implementation", libs.findLibrary("compose-ui-graphics").get())
                add("implementation", libs.findLibrary("compose-ui-tooling-preview").get())
                add("implementation", libs.findLibrary("compose-material3").get())
                add("debugImplementation", libs.findLibrary("compose-ui-tooling").get())
            }
        }
    }
}
```

- [ ] **Step 7: Hilt convention plugin**

Create `/Users/sdagguba/kibble-reorder/android/build-logic/convention/src/main/kotlin/KibbleHiltConvention.kt`:

```kotlin
import org.gradle.api.Plugin
import org.gradle.api.Project
import org.gradle.api.artifacts.VersionCatalogsExtension
import org.gradle.kotlin.dsl.dependencies
import org.gradle.kotlin.dsl.getByType

class KibbleHiltConvention : Plugin<Project> {
    override fun apply(target: Project) {
        with(target) {
            with(pluginManager) {
                apply("com.google.devtools.ksp")
                apply("com.google.dagger.hilt.android")
            }
            val libs = extensions.getByType<VersionCatalogsExtension>().named("libs")
            dependencies {
                add("implementation", libs.findLibrary("hilt-android").get())
                add("ksp", libs.findLibrary("hilt-compiler").get())
            }
        }
    }
}
```

- [ ] **Step 8: Verify build-logic compiles**

Run from `/Users/sdagguba/kibble-reorder/android/`:

```bash
./gradlew :build-logic:convention:compileKotlin
```
Expected: BUILD SUCCESSFUL.

- [ ] **Step 9: Commit**

```bash
cd /Users/sdagguba/kibble-reorder
git add android/gradle/libs.versions.toml android/build-logic/
git commit -m "feat(android): version catalog + convention plugins for Library/Compose/Hilt"
```

---

## Task 3: `:core:common` module

**Files:**
- Create: `core/common/build.gradle.kts`
- Create: `core/common/src/main/AndroidManifest.xml`
- Create: `core/common/src/main/kotlin/com/kibble/core/common/Result.kt`
- Create: `core/common/src/main/kotlin/com/kibble/core/common/DispatcherProvider.kt`
- Create: `core/common/src/main/kotlin/com/kibble/core/common/di/CommonModule.kt`
- Create: `core/common/src/test/kotlin/com/kibble/core/common/ResultTest.kt`

- [ ] **Step 1: Create the module build script**

Create `/Users/sdagguba/kibble-reorder/android/core/common/build.gradle.kts`:

```kotlin
plugins {
    id("kibble.android.library")
    id("kibble.android.hilt")
}

android {
    namespace = "com.kibble.core.common"
}

dependencies {
    implementation(libs.coroutines.core)
    implementation(libs.coroutines.android)

    testImplementation(libs.junit.jupiter)
    testImplementation(libs.coroutines.test)
    testRuntimeOnly("org.junit.jupiter:junit-jupiter-engine:5.11.3")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
```

- [ ] **Step 2: Empty manifest**

Create `core/common/src/main/AndroidManifest.xml`:

```xml
<manifest />
```

- [ ] **Step 3: Write the failing test for Result**

Create `core/common/src/test/kotlin/com/kibble/core/common/ResultTest.kt`:

```kotlin
package com.kibble.core.common

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class ResultTest {
    @Test
    fun `Success carries data`() {
        val r: KibbleResult<Int> = KibbleResult.Success(42)
        assertTrue(r is KibbleResult.Success)
        assertEquals(42, (r as KibbleResult.Success).data)
    }

    @Test
    fun `Failure carries an exception`() {
        val ex = IllegalStateException("nope")
        val r: KibbleResult<Int> = KibbleResult.Failure(ex)
        assertTrue(r is KibbleResult.Failure)
        assertEquals(ex, (r as KibbleResult.Failure).cause)
    }

    @Test
    fun `map only transforms Success`() {
        val s: KibbleResult<Int> = KibbleResult.Success(2)
        val f: KibbleResult<Int> = KibbleResult.Failure(RuntimeException("x"))
        assertEquals(KibbleResult.Success(4), s.map { it * 2 })
        assertEquals(KibbleResult.Failure(RuntimeException("x")).cause::class, (f.map { it * 2 } as KibbleResult.Failure).cause::class)
    }
}
```

- [ ] **Step 4: Run test to confirm it fails**

```bash
cd /Users/sdagguba/kibble-reorder/android
./gradlew :core:common:test
```
Expected: compilation error — `KibbleResult` not found.

- [ ] **Step 5: Implement `KibbleResult`**

Create `core/common/src/main/kotlin/com/kibble/core/common/Result.kt`:

```kotlin
package com.kibble.core.common

sealed interface KibbleResult<out T> {
    data class Success<T>(val data: T) : KibbleResult<T>
    data class Failure(val cause: Throwable) : KibbleResult<Nothing>
}

inline fun <T, R> KibbleResult<T>.map(transform: (T) -> R): KibbleResult<R> = when (this) {
    is KibbleResult.Success -> KibbleResult.Success(transform(data))
    is KibbleResult.Failure -> this
}

inline fun <T> KibbleResult<T>.onSuccess(block: (T) -> Unit): KibbleResult<T> = also {
    if (this is KibbleResult.Success) block(data)
}

inline fun <T> KibbleResult<T>.onFailure(block: (Throwable) -> Unit): KibbleResult<T> = also {
    if (this is KibbleResult.Failure) block(cause)
}

inline fun <T> kibbleRunCatching(block: () -> T): KibbleResult<T> = try {
    KibbleResult.Success(block())
} catch (t: Throwable) {
    KibbleResult.Failure(t)
}
```

- [ ] **Step 6: Implement `DispatcherProvider`**

Create `core/common/src/main/kotlin/com/kibble/core/common/DispatcherProvider.kt`:

```kotlin
package com.kibble.core.common

import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers

interface DispatcherProvider {
    val main: CoroutineDispatcher
    val io: CoroutineDispatcher
    val default: CoroutineDispatcher
}

object DefaultDispatcherProvider : DispatcherProvider {
    override val main = Dispatchers.Main
    override val io = Dispatchers.IO
    override val default = Dispatchers.Default
}
```

- [ ] **Step 7: Hilt binding**

Create `core/common/src/main/kotlin/com/kibble/core/common/di/CommonModule.kt`:

```kotlin
package com.kibble.core.common.di

import com.kibble.core.common.DefaultDispatcherProvider
import com.kibble.core.common.DispatcherProvider
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object CommonModule {
    @Provides @Singleton
    fun provideDispatchers(): DispatcherProvider = DefaultDispatcherProvider
}
```

- [ ] **Step 8: Run tests**

```bash
cd /Users/sdagguba/kibble-reorder/android
./gradlew :core:common:test
```
Expected: 3 passed.

- [ ] **Step 9: Commit**

```bash
cd /Users/sdagguba/kibble-reorder
git add android/core/common/
git commit -m "feat(android/common): KibbleResult sealed type + DispatcherProvider + Hilt module"
```

---

## Task 4: `:core:ui` module — Deep Botanical Material 3 theme

**Files:**
- Create: `core/ui/build.gradle.kts`
- Create: `core/ui/src/main/AndroidManifest.xml`
- Create: `core/ui/src/main/res/values/font_certs.xml`
- Create: `core/ui/src/main/kotlin/com/kibble/core/ui/theme/Color.kt`
- Create: `core/ui/src/main/kotlin/com/kibble/core/ui/theme/Type.kt`
- Create: `core/ui/src/main/kotlin/com/kibble/core/ui/theme/Shape.kt`
- Create: `core/ui/src/main/kotlin/com/kibble/core/ui/theme/KibbleTheme.kt`

- [ ] **Step 1: Module build script**

Create `core/ui/build.gradle.kts`:

```kotlin
plugins {
    id("kibble.android.library")
    id("kibble.android.compose")
}

android {
    namespace = "com.kibble.core.ui"
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.compose.google.fonts)
    implementation(libs.compose.material.icons.extended)
}
```

- [ ] **Step 2: Manifest**

Create `core/ui/src/main/AndroidManifest.xml`:

```xml
<manifest />
```

- [ ] **Step 3: Google Fonts cert array**

Create `core/ui/src/main/res/values/font_certs.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <array name="com_google_android_gms_fonts_certs">
        <item>@array/com_google_android_gms_fonts_certs_dev</item>
        <item>@array/com_google_android_gms_fonts_certs_prod</item>
    </array>
    <string-array name="com_google_android_gms_fonts_certs_dev">
        <item>
            MIIEqDCCA5CgAwIBAgIJANWFuGx90071MA0GCSqGSIb3DQEBBAUAMIGUMQswCQYDVQQGEwJVUzETMBEGA1UECBMKQ2FsaWZvcm5pYTEWMBQGA1UEBxMNTW91bnRhaW4gVmlldzEQMA4GA1UEChMHQW5kcm9pZDEQMA4GA1UECxMHQW5kcm9pZDEQMA4GA1UEAxMHQW5kcm9pZDEiMCAGCSqGSIb3DQEJARYTYW5kcm9pZEBhbmRyb2lkLmNvbTAeFw0wODA0MTUyMzM2NTZaFw0zNTA5MDEyMzM2NTZaMIGUMQswCQYDVQQGEwJVUzETMBEGA1UECBMKQ2FsaWZvcm5pYTEWMBQGA1UEBxMNTW91bnRhaW4gVmlldzEQMA4GA1UEChMHQW5kcm9pZDEQMA4GA1UECxMHQW5kcm9pZDEQMA4GA1UEAxMHQW5kcm9pZDEiMCAGCSqGSIb3DQEJARYTYW5kcm9pZEBhbmRyb2lkLmNvbTCCASAwDQYJKoZIhvcNAQEBBQADggENADCCAQgCggEBANbOLggKv+IxTdGNs8/TGFy0PTP6DHThvbbR24kT9ixcOd9W+EaBPWW+wPPKQmsHxajtWjmQwWfna8mZuSeJS48LIgAZlKkpoOjnS+ON6tMmIymINJkRxtpwQAzi5YGzsSrpv5AHgIYVdkw1W7ldHeS4cBYecBz5oMrPiHIyDrfx2eDV5/yrDpljY//hFxiQRG0qCu+RTTXmcMTjOmUDQ8fw8PtCfSIWlmbB91WoBWmyxPuQV1PssLBNFkU79UzkmWFFBhdPi+VEbq2PmZxe5DC6jrjIq3a/Yk5ZulhDikfh0xn71fJzgmLk+OOnRqTKaXmRZLbKy4cFqSWj97u2digCAQOjgfwwgfkwHQYDVR0OBBYEFI0cxb6VTEM8YYY6FbBMvAPyT+CyMIHJBgNVHSMEgcEwgb6AFI0cxb6VTEM8YYY6FbBMvAPyT+CyoYGapIGXMIGUMQswCQYDVQQGEwJVUzETMBEGA1UECBMKQ2FsaWZvcm5pYTEWMBQGA1UEBxMNTW91bnRhaW4gVmlldzEQMA4GA1UEChMHQW5kcm9pZDEQMA4GA1UECxMHQW5kcm9pZDEQMA4GA1UEAxMHQW5kcm9pZDEiMCAGCSqGSIb3DQEJARYTYW5kcm9pZEBhbmRyb2lkLmNvbYIJANWFuGx90071MAwGA1UdEwQFMAMBAf8wDQYJKoZIhvcNAQEEBQADggEBABnTDPEF+3iSP0hM/qf4aXLFOjy3T6npVrmgbeAmDB1fEmlcj9SeKKKJXJXTPlqwVHbi9Fq+jrKApJ3ICkHmDZVTI4RJwsBBxvX1cOL2I3UWfFeBhU0lfpcwT+JnGD9UY1ZmKJp0u6hNyyT5b8nULpEaZ3pHEDR4rjXaCAyT2FFXvuztlkWZhc1J6aCzxKdE+fcxX3BUPWNQQ8FyFGxxLBKQhe5O72KEAZHXMcfvX9nKXHeYjF4hKLTXG/VfXkrx5KJlFdHpJ6BvhM5mE2wNn+CFr4Vt5pRn+/OYvPMpBBXh+ZaB4mZxlFxXxVnLE
        </item>
    </string-array>
    <string-array name="com_google_android_gms_fonts_certs_prod">
        <item>
            MIIEQzCCAyugAwIBAgIJAMLgh0ZkSjCNMA0GCSqGSIb3DQEBBAUAMHQxCzAJBgNVBAYTAlVTMRMwEQYDVQQIEwpDYWxpZm9ybmlhMRYwFAYDVQQHEw1Nb3VudGFpbiBWaWV3MRQwEgYDVQQKEwtHb29nbGUgSW5jLjEQMA4GA1UECxMHQW5kcm9pZDEQMA4GA1UEAxMHQW5kcm9pZDAeFw0wODA4MjEyMzEzMzRaFw0zNjAxMDcyMzEzMzRaMHQxCzAJBgNVBAYTAlVTMRMwEQYDVQQIEwpDYWxpZm9ybmlhMRYwFAYDVQQHEw1Nb3VudGFpbiBWaWV3MRQwEgYDVQQKEwtHb29nbGUgSW5jLjEQMA4GA1UECxMHQW5kcm9pZDEQMA4GA1UEAxMHQW5kcm9pZDCCASAwDQYJKoZIhvcNAQEBBQADggENADCCAQgCggEBAKtWLgDYO6IIrgqWbxJOKdoR8qtW0I9Y4sypEwPpt1TTcvZApxsdyxMJZ2JORland2qSGT2y5b+3JKkedxiLDmpHpDsz2WCbdxgxRczfey5YZnTJ4VZbH0xqWVW/8lGmPav5xVwnIiJS6HXk+BVKZF+JcWjAsTPgVT2H7T8DoiKy4mtL+9CxTk6P5uROKfUYvgB/SoEi1AFEd8wZBPUJq3GH5XCFuQABNRrDgzUIVEvy9G3hk16pgCBwdzpEf5XzIK1iiozWp5ZgJxA+rV9aGz1lZA5jYI78Eg4PfbwdPzr1DDxv7bLA1NmugGjrFjShsXvpOBxIkXWeqFkmqXR6QzM9wwIBA6OB1zCB1DAdBgNVHQ4EFgQUq2Zfdg9TmIIvQuqCwfAVeGl3UikwgaQGA1UdIwSBnDCBmYAUq2Zfdg9TmIIvQuqCwfAVeGl3UimhealmaiXJyRKpv6vBn5VJWKGQS1tH5rUqvQ8pX1zUw0cFMhMEx6mUOL3KXfyz8E2ZSFhz+G7H1lpMSKnEyWLDrKt9bVvGW7Cg2N0mTYlS4FMHZbkMm6vYYhcLHjmTuIUCDmF5xGw6gNUGfNMzcL5JPkmsrOOhrlJyk/oTV2zU3M9V+f1zfbXBJWfmcOK/dIuPTpVfAHjWj4HTU/E6mdjN8tjmzWvLEZcTRKwMS+vvRq2YNBGcM89kY3xhpmsLsuFtJSV
        </item>
    </string-array>
</resources>
```

(Use the exact certs from `androidx.compose.ui:ui-text-google-fonts` documentation if these are out of date — search "compose downloadable fonts certs xml" for the official upstream resource.)

- [ ] **Step 4: Color tokens**

Create `core/ui/src/main/kotlin/com/kibble/core/ui/theme/Color.kt`:

```kotlin
package com.kibble.core.ui.theme

import androidx.compose.ui.graphics.Color

// Deep Botanical — light scheme
val DeepForest = Color(0xFF003A2E)
val Forest = Color(0xFF155243)
val InverseForest = Color(0xFF98D2BF)
val SageContainer = Color(0xFFE8F0EA)
val SageContainerLight = Color(0xFFECF6F1)
val WarmCream = Color(0xFFFCFAF7)
val SurfaceCanvas = Color(0xFFF2FCF7)
val OnSurface = Color(0xFF151D1B)
val OnSurfaceVariant = Color(0xFF404945)
val OnSurfaceMuted = Color(0xFF8A948F)
val Outline = Color(0xFF707975)
val OutlineVariant = Color(0xFFBFC9C4)
val WarningAmber = Color(0xFFB07C2E)
val ErrorRed = Color(0xFFBA1A1A)

// Dark mode
val DarkSurface = Color(0xFF111817)
val DarkOnSurface = Color(0xFFE9F3EE)
val DarkSurfaceContainer = Color(0xFF1A2422)
val DarkOnSurfaceVariant = Color(0xFFBFC9C4)
val DarkPrimary = InverseForest
val DarkOnPrimary = Color(0xFF00382C)
```

- [ ] **Step 5: Typography (downloadable Google Fonts)**

Create `core/ui/src/main/kotlin/com/kibble/core/ui/theme/Type.kt`:

```kotlin
package com.kibble.core.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.googlefonts.GoogleFont
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.kibble.core.ui.R

private val provider = GoogleFont.Provider(
    providerAuthority = "com.google.android.gms.fonts",
    providerPackage = "com.google.android.gms",
    certificates = R.array.com_google_android_gms_fonts_certs,
)

private val notoSerifFont = GoogleFont("Noto Serif")
private val manropeFont = GoogleFont("Manrope")

val NotoSerif: FontFamily = FontFamily(
    Font(googleFont = notoSerifFont, fontProvider = provider, weight = FontWeight.Normal),
    Font(googleFont = notoSerifFont, fontProvider = provider, weight = FontWeight.Normal, style = FontStyle.Italic),
    Font(googleFont = notoSerifFont, fontProvider = provider, weight = FontWeight.Medium, style = FontStyle.Italic),
)

val Manrope: FontFamily = FontFamily(
    Font(googleFont = manropeFont, fontProvider = provider, weight = FontWeight.Normal),
    Font(googleFont = manropeFont, fontProvider = provider, weight = FontWeight.Medium),
    Font(googleFont = manropeFont, fontProvider = provider, weight = FontWeight.SemiBold),
    Font(googleFont = manropeFont, fontProvider = provider, weight = FontWeight.Bold),
)

val KibbleTypography: Typography = Typography(
    displayLarge = TextStyle(fontFamily = NotoSerif, fontSize = 56.sp, fontWeight = FontWeight.Normal, letterSpacing = (-0.02).em, lineHeight = 64.sp),
    displayMedium = TextStyle(fontFamily = NotoSerif, fontSize = 48.sp, fontWeight = FontWeight.Normal, letterSpacing = (-0.02).em, lineHeight = 56.sp),
    headlineLarge = TextStyle(fontFamily = NotoSerif, fontSize = 32.sp, fontWeight = FontWeight.Normal, letterSpacing = (-0.01).em, lineHeight = 40.sp),
    headlineMedium = TextStyle(fontFamily = NotoSerif, fontSize = 28.sp, fontWeight = FontWeight.Normal, lineHeight = 36.sp),
    headlineSmall = TextStyle(fontFamily = NotoSerif, fontSize = 24.sp, fontWeight = FontWeight.Normal, lineHeight = 32.sp),
    titleLarge = TextStyle(fontFamily = NotoSerif, fontSize = 22.sp, fontWeight = FontWeight.Medium, lineHeight = 28.sp),
    titleMedium = TextStyle(fontFamily = Manrope, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, lineHeight = 24.sp),
    titleSmall = TextStyle(fontFamily = Manrope, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, lineHeight = 20.sp),
    bodyLarge = TextStyle(fontFamily = Manrope, fontSize = 18.sp, fontWeight = FontWeight.Normal, lineHeight = 28.sp),
    bodyMedium = TextStyle(fontFamily = Manrope, fontSize = 16.sp, fontWeight = FontWeight.Normal, lineHeight = 24.sp),
    bodySmall = TextStyle(fontFamily = Manrope, fontSize = 14.sp, fontWeight = FontWeight.Normal, lineHeight = 20.sp),
    labelLarge = TextStyle(fontFamily = Manrope, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 0.08.em, lineHeight = 20.sp),
    labelMedium = TextStyle(fontFamily = Manrope, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 0.08.em, lineHeight = 16.sp),
    labelSmall = TextStyle(fontFamily = Manrope, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 0.10.em, lineHeight = 14.sp),
)
```

- [ ] **Step 6: Shape tokens**

Create `core/ui/src/main/kotlin/com/kibble/core/ui/theme/Shape.kt`:

```kotlin
package com.kibble.core.ui.theme

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Shapes
import androidx.compose.ui.unit.dp

val KibbleShapes = Shapes(
    extraSmall = RoundedCornerShape(4.dp),
    small = RoundedCornerShape(8.dp),
    medium = RoundedCornerShape(12.dp),
    large = RoundedCornerShape(16.dp),
    extraLarge = RoundedCornerShape(24.dp),
)
```

- [ ] **Step 7: Theme assembly**

Create `core/ui/src/main/kotlin/com/kibble/core/ui/theme/KibbleTheme.kt`:

```kotlin
package com.kibble.core.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

private val LightColors = lightColorScheme(
    primary = DeepForest,
    onPrimary = WarmCream,
    primaryContainer = Forest,
    onPrimaryContainer = InverseForest,
    inversePrimary = InverseForest,
    secondary = Forest,
    onSecondary = WarmCream,
    secondaryContainer = SageContainer,
    onSecondaryContainer = DeepForest,
    tertiary = WarningAmber,
    onTertiary = WarmCream,
    background = SurfaceCanvas,
    onBackground = OnSurface,
    surface = SurfaceCanvas,
    onSurface = OnSurface,
    surfaceVariant = SageContainerLight,
    onSurfaceVariant = OnSurfaceVariant,
    outline = Outline,
    outlineVariant = OutlineVariant,
    error = ErrorRed,
    onError = WarmCream,
)

private val DarkColors = darkColorScheme(
    primary = DarkPrimary,
    onPrimary = DarkOnPrimary,
    primaryContainer = Forest,
    onPrimaryContainer = InverseForest,
    inversePrimary = DeepForest,
    secondary = InverseForest,
    onSecondary = DeepForest,
    secondaryContainer = DarkSurfaceContainer,
    onSecondaryContainer = InverseForest,
    background = DarkSurface,
    onBackground = DarkOnSurface,
    surface = DarkSurface,
    onSurface = DarkOnSurface,
    surfaceVariant = DarkSurfaceContainer,
    onSurfaceVariant = DarkOnSurfaceVariant,
    outline = OutlineVariant,
    error = ErrorRed,
    onError = DarkOnSurface,
)

@Composable
fun KibbleTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        typography = KibbleTypography,
        shapes = KibbleShapes,
        content = content,
    )
}
```

- [ ] **Step 8: Build**

```bash
cd /Users/sdagguba/kibble-reorder/android
./gradlew :core:ui:assemble
```
Expected: BUILD SUCCESSFUL.

- [ ] **Step 9: Commit**

```bash
cd /Users/sdagguba/kibble-reorder
git add android/core/ui/
git commit -m "feat(android/ui): Deep Botanical Material 3 theme + downloadable Noto Serif/Manrope"
```

---

## Task 5: `:core:database` module

**Files:**
- Create: `core/database/build.gradle.kts`
- Create: `core/database/src/main/AndroidManifest.xml`
- Create: `core/database/src/main/kotlin/com/kibble/core/database/entity/*.kt` (6 entities)
- Create: `core/database/src/main/kotlin/com/kibble/core/database/dao/*.kt` (6 DAOs)
- Create: `core/database/src/main/kotlin/com/kibble/core/database/KibbleDatabase.kt`
- Create: `core/database/src/main/kotlin/com/kibble/core/database/di/DatabaseModule.kt`
- Create: `core/database/src/test/kotlin/com/kibble/core/database/UserDaoTest.kt` (and similar)

- [ ] **Step 1: Module build script**

Create `core/database/build.gradle.kts`:

```kotlin
plugins {
    id("kibble.android.library")
    id("kibble.android.hilt")
}

android {
    namespace = "com.kibble.core.database"
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.coroutines.core)
    implementation(libs.room.runtime)
    implementation(libs.room.ktx)
    ksp(libs.room.compiler)

    testImplementation(libs.junit.jupiter)
    testImplementation(libs.coroutines.test)
    testImplementation(libs.room.testing)
    testImplementation("androidx.test:core:1.6.1")
    testImplementation("org.robolectric:robolectric:4.13")
    testRuntimeOnly("org.junit.jupiter:junit-jupiter-engine:5.11.3")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
```

- [ ] **Step 2: Manifest**

`core/database/src/main/AndroidManifest.xml`: `<manifest />`

- [ ] **Step 3: Entities**

Create `core/database/src/main/kotlin/com/kibble/core/database/entity/UserEntity.kt`:

```kotlin
package com.kibble.core.database.entity

import androidx.room.Entity
import androidx.room.PrimaryKey
import java.util.UUID

@Entity(tableName = "users")
data class UserEntity(
    @PrimaryKey val id: UUID,
    val firebaseUid: String,
    val email: String?,
    val name: String?,
    val pincode: String?,
    val reorderThresholdPct: Int = 20,
    val paymentMode: String = "90pct",
    val packSizePreference: String = "best_value",
    val minSellerRating: Float = 4.0f,
    val quietHoursStart: String? = null,
    val quietHoursEnd: String? = null,
    val quietHoursTz: String? = null,
    val onboardingComplete: Boolean = false,
    val createdAt: Long = System.currentTimeMillis(),
)
```

Create `DogEntity.kt`:

```kotlin
package com.kibble.core.database.entity

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey
import java.util.UUID

@Entity(
    tableName = "dogs",
    foreignKeys = [ForeignKey(entity = UserEntity::class, parentColumns = ["id"], childColumns = ["userId"], onDelete = ForeignKey.CASCADE)],
    indices = [Index("userId")],
)
data class DogEntity(
    @PrimaryKey val id: UUID,
    val userId: UUID,
    val name: String,
    val breed: String?,
    val kibbleBrand: String,
    val kibbleProductName: String,
)
```

Create `BinEntity.kt`:

```kotlin
package com.kibble.core.database.entity

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey
import java.util.UUID

@Entity(
    tableName = "bins",
    foreignKeys = [
        ForeignKey(entity = UserEntity::class, parentColumns = ["id"], childColumns = ["userId"], onDelete = ForeignKey.CASCADE),
        ForeignKey(entity = DogEntity::class, parentColumns = ["id"], childColumns = ["dogId"], onDelete = ForeignKey.CASCADE),
    ],
    indices = [Index("userId"), Index("dogId")],
)
data class BinEntity(
    @PrimaryKey val id: UUID,
    val userId: UUID,
    val dogId: UUID,
    val sensorDeviceId: String,
    val containerCapacityKg: Double,
    val calibrationState: String,
    val emptyCalibrationMm: Double?,
    val fullCalibrationMm: Double?,
)
```

Create `SensorReadingEntity.kt`:

```kotlin
package com.kibble.core.database.entity

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey
import java.util.UUID

@Entity(
    tableName = "sensor_readings",
    foreignKeys = [ForeignKey(entity = BinEntity::class, parentColumns = ["id"], childColumns = ["binId"], onDelete = ForeignKey.CASCADE)],
    indices = [Index("binId"), Index("timestamp")],
)
data class SensorReadingEntity(
    @PrimaryKey val id: UUID,
    val binId: UUID,
    val distanceMm: Double,
    val timestamp: Long,
    val synced: Boolean = false,
)
```

Create `OrderEntity.kt`:

```kotlin
package com.kibble.core.database.entity

import androidx.room.Entity
import androidx.room.PrimaryKey
import java.util.UUID

@Entity(tableName = "orders")
data class OrderEntity(
    @PrimaryKey val id: UUID,
    val binId: UUID,
    val retailer: String,
    val packKg: Double,
    val priceInr: Double,
    val status: String,
    val placedAt: Long,
)
```

Create `RetailerSessionEntity.kt`:

```kotlin
package com.kibble.core.database.entity

import androidx.room.Entity
import java.util.UUID

@Entity(tableName = "retailer_sessions", primaryKeys = ["userId", "retailer"])
data class RetailerSessionEntity(
    val userId: UUID,
    val retailer: String,
    val type: String, // "cookie" | "credentials"
    val expiresAtMillis: Long?,
    val source: String, // "ONBOARDING" | "CHECKOUT_PROMPT" | "SETTINGS_ADD"
    val isExpired: Boolean = false,
    val updatedAt: Long = System.currentTimeMillis(),
)
```

- [ ] **Step 4: Type converters**

Create `core/database/src/main/kotlin/com/kibble/core/database/Converters.kt`:

```kotlin
package com.kibble.core.database

import androidx.room.TypeConverter
import java.util.UUID

class Converters {
    @TypeConverter fun uuidToString(uuid: UUID?): String? = uuid?.toString()
    @TypeConverter fun stringToUuid(s: String?): UUID? = s?.let { UUID.fromString(it) }
}
```

- [ ] **Step 5: DAOs**

Create `core/database/src/main/kotlin/com/kibble/core/database/dao/UserDao.kt`:

```kotlin
package com.kibble.core.database.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.kibble.core.database.entity.UserEntity
import kotlinx.coroutines.flow.Flow
import java.util.UUID

@Dao
interface UserDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(user: UserEntity)

    @Query("SELECT * FROM users WHERE id = :id")
    fun observe(id: UUID): Flow<UserEntity?>

    @Query("SELECT * FROM users LIMIT 1")
    suspend fun first(): UserEntity?

    @Query("DELETE FROM users")
    suspend fun clear()
}
```

Create the same pattern for `DogDao`, `BinDao`, `SensorReadingDao`, `OrderDao`, `RetailerSessionDao`. Each DAO has at minimum: `upsert`, `observe`/`getAll`, and `clear`. Below are the contents:

`DogDao.kt`:

```kotlin
package com.kibble.core.database.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.kibble.core.database.entity.DogEntity
import kotlinx.coroutines.flow.Flow
import java.util.UUID

@Dao
interface DogDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsert(dog: DogEntity)
    @Query("SELECT * FROM dogs WHERE userId = :userId") fun observeForUser(userId: UUID): Flow<List<DogEntity>>
    @Query("SELECT * FROM dogs WHERE id = :id") suspend fun get(id: UUID): DogEntity?
    @Query("DELETE FROM dogs") suspend fun clear()
}
```

`BinDao.kt`:

```kotlin
package com.kibble.core.database.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.kibble.core.database.entity.BinEntity
import kotlinx.coroutines.flow.Flow
import java.util.UUID

@Dao
interface BinDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsert(bin: BinEntity)
    @Query("SELECT * FROM bins WHERE userId = :userId") fun observeForUser(userId: UUID): Flow<List<BinEntity>>
    @Query("SELECT * FROM bins WHERE id = :id") fun observeById(id: UUID): Flow<BinEntity?>
    @Query("DELETE FROM bins") suspend fun clear()
}
```

`SensorReadingDao.kt`:

```kotlin
package com.kibble.core.database.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.kibble.core.database.entity.SensorReadingEntity
import kotlinx.coroutines.flow.Flow
import java.util.UUID

@Dao
interface SensorReadingDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsert(reading: SensorReadingEntity)
    @Query("SELECT * FROM sensor_readings WHERE binId = :binId ORDER BY timestamp DESC") fun observeForBin(binId: UUID): Flow<List<SensorReadingEntity>>
    @Query("SELECT * FROM sensor_readings WHERE binId = :binId ORDER BY timestamp DESC LIMIT 1") fun observeLatest(binId: UUID): Flow<SensorReadingEntity?>
    @Query("SELECT * FROM sensor_readings WHERE synced = 0") suspend fun unsynced(): List<SensorReadingEntity>
    @Query("UPDATE sensor_readings SET synced = 1 WHERE id = :id") suspend fun markSynced(id: UUID)
    @Query("DELETE FROM sensor_readings") suspend fun clear()
}
```

`OrderDao.kt`:

```kotlin
package com.kibble.core.database.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.kibble.core.database.entity.OrderEntity
import kotlinx.coroutines.flow.Flow
import java.util.UUID

@Dao
interface OrderDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsert(order: OrderEntity)
    @Query("SELECT * FROM orders WHERE binId = :binId ORDER BY placedAt DESC") fun observeForBin(binId: UUID): Flow<List<OrderEntity>>
    @Query("DELETE FROM orders") suspend fun clear()
}
```

`RetailerSessionDao.kt`:

```kotlin
package com.kibble.core.database.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.kibble.core.database.entity.RetailerSessionEntity
import kotlinx.coroutines.flow.Flow
import java.util.UUID

@Dao
interface RetailerSessionDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsert(session: RetailerSessionEntity)
    @Query("SELECT * FROM retailer_sessions WHERE userId = :userId") fun observeForUser(userId: UUID): Flow<List<RetailerSessionEntity>>
    @Query("DELETE FROM retailer_sessions WHERE userId = :userId AND retailer = :retailer") suspend fun delete(userId: UUID, retailer: String)
    @Query("DELETE FROM retailer_sessions") suspend fun clear()
}
```

- [ ] **Step 6: Database**

Create `core/database/src/main/kotlin/com/kibble/core/database/KibbleDatabase.kt`:

```kotlin
package com.kibble.core.database

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.TypeConverters
import com.kibble.core.database.dao.BinDao
import com.kibble.core.database.dao.DogDao
import com.kibble.core.database.dao.OrderDao
import com.kibble.core.database.dao.RetailerSessionDao
import com.kibble.core.database.dao.SensorReadingDao
import com.kibble.core.database.dao.UserDao
import com.kibble.core.database.entity.BinEntity
import com.kibble.core.database.entity.DogEntity
import com.kibble.core.database.entity.OrderEntity
import com.kibble.core.database.entity.RetailerSessionEntity
import com.kibble.core.database.entity.SensorReadingEntity
import com.kibble.core.database.entity.UserEntity

@Database(
    entities = [
        UserEntity::class, DogEntity::class, BinEntity::class,
        SensorReadingEntity::class, OrderEntity::class, RetailerSessionEntity::class,
    ],
    version = 1,
    exportSchema = true,
)
@TypeConverters(Converters::class)
abstract class KibbleDatabase : RoomDatabase() {
    abstract fun userDao(): UserDao
    abstract fun dogDao(): DogDao
    abstract fun binDao(): BinDao
    abstract fun sensorReadingDao(): SensorReadingDao
    abstract fun orderDao(): OrderDao
    abstract fun retailerSessionDao(): RetailerSessionDao
}
```

- [ ] **Step 7: Hilt module**

Create `core/database/src/main/kotlin/com/kibble/core/database/di/DatabaseModule.kt`:

```kotlin
package com.kibble.core.database.di

import android.content.Context
import androidx.room.Room
import com.kibble.core.database.KibbleDatabase
import com.kibble.core.database.dao.BinDao
import com.kibble.core.database.dao.DogDao
import com.kibble.core.database.dao.OrderDao
import com.kibble.core.database.dao.RetailerSessionDao
import com.kibble.core.database.dao.SensorReadingDao
import com.kibble.core.database.dao.UserDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {
    @Provides @Singleton
    fun provideDatabase(@ApplicationContext ctx: Context): KibbleDatabase =
        Room.databaseBuilder(ctx, KibbleDatabase::class.java, "kibble.db").build()

    @Provides fun provideUserDao(db: KibbleDatabase): UserDao = db.userDao()
    @Provides fun provideDogDao(db: KibbleDatabase): DogDao = db.dogDao()
    @Provides fun provideBinDao(db: KibbleDatabase): BinDao = db.binDao()
    @Provides fun provideSensorReadingDao(db: KibbleDatabase): SensorReadingDao = db.sensorReadingDao()
    @Provides fun provideOrderDao(db: KibbleDatabase): OrderDao = db.orderDao()
    @Provides fun provideRetailerSessionDao(db: KibbleDatabase): RetailerSessionDao = db.retailerSessionDao()
}
```

- [ ] **Step 8: DAO test**

Create `core/database/src/test/kotlin/com/kibble/core/database/UserDaoTest.kt`:

```kotlin
package com.kibble.core.database

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.kibble.core.database.entity.UserEntity
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.extension.ExtendWith
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import java.util.UUID

@RunWith(RobolectricTestRunner::class)
class UserDaoTest {
    private lateinit var db: KibbleDatabase

    @BeforeEach
    fun setUp() {
        db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext(), KibbleDatabase::class.java)
            .allowMainThreadQueries()
            .build()
    }

    @AfterEach fun tearDown() = db.close()

    @Test
    fun `upsert and observe round-trip a user`() = runTest {
        val id = UUID.randomUUID()
        val user = UserEntity(id = id, firebaseUid = "fb-1", email = "x@y.com", name = "Sasank", pincode = "560001")
        db.userDao().upsert(user)
        val out = db.userDao().observe(id).first()
        assertEquals(user, out)
    }

    @Test
    fun `clear removes all users`() = runTest {
        db.userDao().upsert(UserEntity(UUID.randomUUID(), "fb-2", null, null, null))
        db.userDao().clear()
        assertEquals(null, db.userDao().first())
    }
}
```

(Robolectric is needed because Room requires an Android Context. Add `@RunWith(RobolectricTestRunner::class)` and the test runner config in `core/database/build.gradle.kts` if needed via `testOptions { unitTests { isIncludeAndroidResources = true } }`.)

- [ ] **Step 9: Run tests**

```bash
cd /Users/sdagguba/kibble-reorder/android
./gradlew :core:database:test
```
Expected: 2 passed.

- [ ] **Step 10: Commit**

```bash
cd /Users/sdagguba/kibble-reorder
git add android/core/database/
git commit -m "feat(android/database): Room schema with 6 entities + DAOs + Hilt module"
```

---

## Task 6: `:core:network` module — Retrofit + Auth interceptor + KibbleApi

**Files:**
- Create: `core/network/build.gradle.kts`
- Create: `core/network/src/main/AndroidManifest.xml`
- Create: `core/network/src/main/kotlin/com/kibble/core/network/dto/*.kt` (one file per DTO group)
- Create: `core/network/src/main/kotlin/com/kibble/core/network/KibbleApi.kt`
- Create: `core/network/src/main/kotlin/com/kibble/core/network/FirebaseTokenProvider.kt`
- Create: `core/network/src/main/kotlin/com/kibble/core/network/AuthInterceptor.kt`
- Create: `core/network/src/main/kotlin/com/kibble/core/network/di/NetworkModule.kt`
- Create: `core/network/src/test/kotlin/com/kibble/core/network/AuthInterceptorTest.kt`
- Create: `core/network/src/test/kotlin/com/kibble/core/network/KibbleApiTest.kt`

- [ ] **Step 1: Module build script**

Create `core/network/build.gradle.kts`:

```kotlin
plugins {
    id("kibble.android.library")
    id("kibble.android.hilt")
    alias(libs.plugins.kotlin.serialization)
}

android {
    namespace = "com.kibble.core.network"
    buildTypes {
        debug { buildConfigField("String", "API_BASE_URL", "\"http://10.0.2.2:8000/\"") }
        release { buildConfigField("String", "API_BASE_URL", "\"https://api.kibble.app/\"") }
    }
    buildFeatures { buildConfig = true }
}

dependencies {
    implementation(project(":core:common"))
    implementation(libs.retrofit)
    implementation(libs.retrofit.kotlinx.serialization)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.okhttp)
    implementation(libs.okhttp.logging)
    implementation(libs.coroutines.core)

    testImplementation(libs.junit.jupiter)
    testImplementation(libs.coroutines.test)
    testImplementation(libs.mockk)
    testImplementation(libs.mockwebserver)
    testRuntimeOnly("org.junit.jupiter:junit-jupiter-engine:5.11.3")
}

tasks.withType<Test> { useJUnitPlatform() }
```

- [ ] **Step 2: Manifest**

`<manifest />` at `core/network/src/main/AndroidManifest.xml`.

- [ ] **Step 3: DTOs**

Create `core/network/src/main/kotlin/com/kibble/core/network/dto/AuthDto.kt`:

```kotlin
package com.kibble.core.network.dto

import kotlinx.serialization.Serializable

@Serializable
data class FirebaseLoginRequest(val firebase_id_token: String)

@Serializable
data class FirebaseLoginResponse(val user_id: String, val is_new_user: Boolean, val email: String?)
```

Create `UserDto.kt`:

```kotlin
package com.kibble.core.network.dto

import kotlinx.serialization.Serializable

@Serializable
data class UserDto(
    val id: String,
    val email: String?,
    val name: String?,
    val pincode: String?,
    val reorder_threshold_pct: Int,
    val payment_mode: String,
    val min_seller_rating: Float,
    val pack_size_preference: String,
)

@Serializable
data class UserPatchRequest(
    val name: String? = null,
    val pincode: String? = null,
    val reorder_threshold_pct: Int? = null,
    val payment_mode: String? = null,
    val pack_size_preference: String? = null,
    val min_seller_rating: Float? = null,
)

@Serializable
data class QuietHoursRequest(val start: String, val end: String, val timezone: String)
```

Create `DogDto.kt`:

```kotlin
package com.kibble.core.network.dto

import kotlinx.serialization.Serializable

@Serializable
data class DogCreateRequest(val name: String, val breed: String?, val kibble_brand: String, val kibble_product_name: String)

@Serializable
data class DogDto(val id: String, val name: String, val breed: String?, val kibble_brand: String, val kibble_product_name: String)
```

Create `BinDto.kt`:

```kotlin
package com.kibble.core.network.dto

import kotlinx.serialization.Serializable

@Serializable
data class BinCreateRequest(val dog_id: String, val sensor_device_id: String, val container_capacity_kg: Double)

@Serializable
data class BinDto(val id: String, val dog_id: String, val sensor_device_id: String, val container_capacity_kg: Double, val calibration_state: String, val empty_calibration_mm: Double?, val full_calibration_mm: Double?)

@Serializable
data class CalibrateEmptyRequest(val distance_mm: Double)

@Serializable
data class SensorReadingRequest(val distance_mm: Double, val timestamp: String)

@Serializable
data class SensorReadingResponse(val id: String, val bin_id: String, val distance_mm: Double, val timestamp: String, val level_pct: Double?, val kg_remaining: Double?)
```

Create `ForecastDto.kt`:

```kotlin
package com.kibble.core.network.dto

import kotlinx.serialization.Serializable

@Serializable
data class ForecastResponse(
    val status: String, // "ok" | "insufficient_data"
    val reorder_threshold_pct: Int,
    val historical: List<ForecastPoint> = emptyList(),
    val forecast: List<ForecastPoint> = emptyList(),
    val confidence_band: List<ConfidenceBandPoint> = emptyList(),
    val predicted_reorder_date: String? = null,
    val predicted_empty_date: String? = null,
)

@Serializable data class ForecastPoint(val date: String, val level_pct: Double)
@Serializable data class ConfidenceBandPoint(val date: String, val lower_pct: Double, val upper_pct: Double)
```

Create `RetailerSessionDto.kt`:

```kotlin
package com.kibble.core.network.dto

import kotlinx.serialization.Serializable

@Serializable
data class RetailerSessionRequest(
    val retailer: String,
    val type: String, // "cookie" | "credentials"
    val session_blob: String? = null,
    val credentials_blob: String? = null,
    val expires_at: String? = null,
    val source: String = "ONBOARDING",
)

@Serializable
data class RetailerSessionResponse(val id: String, val retailer: String, val type: String, val expires_at: String?, val source: String)

@Serializable
data class RetailerSessionListItem(val retailer: String, val type: String, val expires_at: String?, val is_expired: Boolean, val source: String)
```

- [ ] **Step 4: KibbleApi interface**

Create `core/network/src/main/kotlin/com/kibble/core/network/KibbleApi.kt`:

```kotlin
package com.kibble.core.network

import com.kibble.core.network.dto.*
import retrofit2.http.*

interface KibbleApi {

    @POST("auth/firebase")
    suspend fun firebaseLogin(@Body body: FirebaseLoginRequest): FirebaseLoginResponse

    @GET("users/me")
    suspend fun getMe(): UserDto

    @PATCH("users/{id}")
    suspend fun patchUser(@Path("id") userId: String, @Body body: UserPatchRequest): UserDto

    @PATCH("users/{id}/quiet-hours")
    suspend fun patchQuietHours(@Path("id") userId: String, @Body body: QuietHoursRequest): UserDto

    @POST("users/{id}/dogs")
    suspend fun createDog(@Path("id") userId: String, @Body body: DogCreateRequest): DogDto

    @POST("users/{id}/bins")
    suspend fun createBin(@Path("id") userId: String, @Body body: BinCreateRequest): BinDto

    @POST("bins/{id}/calibrate-empty")
    suspend fun calibrateEmpty(@Path("id") binId: String, @Body body: CalibrateEmptyRequest): BinDto

    @POST("bins/{id}/readings")
    suspend fun postReading(@Path("id") binId: String, @Body body: SensorReadingRequest): SensorReadingResponse

    @GET("bins/{id}/forecast")
    suspend fun getForecast(@Path("id") binId: String): ForecastResponse

    @POST("users/{id}/retailer-sessions")
    suspend fun createRetailerSession(@Path("id") userId: String, @Body body: RetailerSessionRequest): RetailerSessionResponse

    @GET("users/{id}/retailer-sessions")
    suspend fun listRetailerSessions(@Path("id") userId: String): List<RetailerSessionListItem>

    @DELETE("users/{id}/retailer-sessions/{retailer}")
    suspend fun deleteRetailerSession(@Path("id") userId: String, @Path("retailer") retailer: String)
}
```

- [ ] **Step 5: FirebaseTokenProvider interface**

Create `core/network/src/main/kotlin/com/kibble/core/network/FirebaseTokenProvider.kt`:

```kotlin
package com.kibble.core.network

interface FirebaseTokenProvider {
    /** Returns the current Firebase ID token, refreshing if expired. Returns null if user isn't signed in. */
    suspend fun currentToken(): String?
}
```

(Implementation lives in `:app` because it depends on FirebaseAuth SDK, which `:core:network` shouldn't bring in.)

- [ ] **Step 6: Write the failing AuthInterceptor test**

Create `core/network/src/test/kotlin/com/kibble/core/network/AuthInterceptorTest.kt`:

```kotlin
package com.kibble.core.network

import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test

class AuthInterceptorTest {
    private lateinit var server: MockWebServer
    private val tokenProvider = mockk<FirebaseTokenProvider>()

    @BeforeEach
    fun setUp() {
        server = MockWebServer().apply { start() }
    }

    @AfterEach fun tearDown() = server.shutdown()

    @Test
    fun `injects Bearer header when token available`() = runTest {
        coEvery { tokenProvider.currentToken() } returns "abc.def.ghi"
        val client = OkHttpClient.Builder().addInterceptor(AuthInterceptor(tokenProvider)).build()
        server.enqueue(MockResponse().setResponseCode(200))
        client.newCall(Request.Builder().url(server.url("/x")).build()).execute()
        val recorded = server.takeRequest()
        assertEquals("Bearer abc.def.ghi", recorded.getHeader("Authorization"))
    }

    @Test
    fun `omits Authorization header when no token`() = runTest {
        coEvery { tokenProvider.currentToken() } returns null
        val client = OkHttpClient.Builder().addInterceptor(AuthInterceptor(tokenProvider)).build()
        server.enqueue(MockResponse().setResponseCode(200))
        client.newCall(Request.Builder().url(server.url("/x")).build()).execute()
        val recorded = server.takeRequest()
        assertNull(recorded.getHeader("Authorization"))
    }
}
```

- [ ] **Step 7: Run tests to confirm they fail**

```bash
cd /Users/sdagguba/kibble-reorder/android
./gradlew :core:network:test
```
Expected: compile error — `AuthInterceptor` not defined.

- [ ] **Step 8: Implement AuthInterceptor**

Create `core/network/src/main/kotlin/com/kibble/core/network/AuthInterceptor.kt`:

```kotlin
package com.kibble.core.network

import kotlinx.coroutines.runBlocking
import okhttp3.Interceptor
import okhttp3.Response

class AuthInterceptor(private val tokenProvider: FirebaseTokenProvider) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val token = runBlocking { tokenProvider.currentToken() }
        val req = if (token == null) chain.request()
        else chain.request().newBuilder().addHeader("Authorization", "Bearer $token").build()
        return chain.proceed(req)
    }
}
```

- [ ] **Step 9: NetworkModule**

Create `core/network/src/main/kotlin/com/kibble/core/network/di/NetworkModule.kt`:

```kotlin
package com.kibble.core.network.di

import com.kibble.core.network.AuthInterceptor
import com.kibble.core.network.BuildConfig
import com.kibble.core.network.FirebaseTokenProvider
import com.kibble.core.network.KibbleApi
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides @Singleton
    fun provideJson(): Json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    @Provides @Singleton
    fun provideOkHttp(tokenProvider: FirebaseTokenProvider): OkHttpClient {
        val logging = HttpLoggingInterceptor().apply {
            level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BASIC else HttpLoggingInterceptor.Level.NONE
        }
        return OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(tokenProvider))
            .addInterceptor(logging)
            .build()
    }

    @Provides @Singleton
    fun provideRetrofit(okHttp: OkHttpClient, json: Json): Retrofit = Retrofit.Builder()
        .baseUrl(BuildConfig.API_BASE_URL)
        .client(okHttp)
        .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
        .build()

    @Provides @Singleton
    fun provideKibbleApi(retrofit: Retrofit): KibbleApi = retrofit.create(KibbleApi::class.java)
}
```

- [ ] **Step 10: KibbleApi smoke test against MockWebServer**

Create `core/network/src/test/kotlin/com/kibble/core/network/KibbleApiTest.kt`:

```kotlin
package com.kibble.core.network

import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import retrofit2.Retrofit

class KibbleApiTest {
    private lateinit var server: MockWebServer
    private lateinit var api: KibbleApi
    private val json = Json { ignoreUnknownKeys = true }

    @BeforeEach
    fun setUp() {
        server = MockWebServer().apply { start() }
        api = Retrofit.Builder()
            .baseUrl(server.url("/"))
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(KibbleApi::class.java)
    }

    @AfterEach fun tearDown() = server.shutdown()

    @Test
    fun `firebase login parses response`() = runTest {
        server.enqueue(MockResponse().setBody("""{"user_id":"abc-123","is_new_user":true,"email":"x@y.com"}"""))
        val resp = api.firebaseLogin(com.kibble.core.network.dto.FirebaseLoginRequest("token"))
        assertEquals("abc-123", resp.user_id)
        assertEquals(true, resp.is_new_user)
        assertEquals("x@y.com", resp.email)
    }

    @Test
    fun `forecast insufficient_data parses without lists`() = runTest {
        server.enqueue(MockResponse().setBody("""{"status":"insufficient_data","reorder_threshold_pct":20}"""))
        val resp = api.getForecast("bin-1")
        assertEquals("insufficient_data", resp.status)
        assertEquals(20, resp.reorder_threshold_pct)
        assertEquals(0, resp.historical.size)
    }
}
```

- [ ] **Step 11: Run tests**

```bash
cd /Users/sdagguba/kibble-reorder/android
./gradlew :core:network:test
```
Expected: 4 passed.

- [ ] **Step 12: Commit**

```bash
cd /Users/sdagguba/kibble-reorder
git add android/core/network/
git commit -m "feat(android/network): KibbleApi + AuthInterceptor + FirebaseTokenProvider seam"
```

---

## Task 7: `:app` module — Application, MainActivity, Hilt root

**Files:**
- Create: `app/build.gradle.kts`
- Create: `app/src/main/AndroidManifest.xml`
- Create: `app/src/main/res/values/strings.xml`
- Create: `app/src/main/kotlin/com/kibble/KibbleApplication.kt`
- Create: `app/src/main/kotlin/com/kibble/MainActivity.kt`
- Create: `app/src/main/kotlin/com/kibble/auth/FirebaseTokenProviderImpl.kt`
- Create: `app/src/main/kotlin/com/kibble/auth/di/AuthModule.kt`

- [ ] **Step 1: App build script**

Create `app/build.gradle.kts`:

```kotlin
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.compose.compiler)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
    alias(libs.plugins.google.services)
}

android {
    namespace = "com.kibble"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.kibble"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }

    buildTypes {
        debug { isDebuggable = true }
        release {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlin { jvmToolchain(17) }
    buildFeatures { compose = true }
}

dependencies {
    implementation(project(":core:ui"))
    implementation(project(":core:common"))
    implementation(project(":core:network"))
    implementation(project(":core:database"))

    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)

    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    debugImplementation(libs.compose.ui.tooling)

    implementation(libs.nav.compose)
    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)
    implementation(libs.hilt.navigation.compose)

    implementation(platform(libs.firebase.bom))
    implementation(libs.firebase.auth)

    testImplementation(libs.junit.jupiter)
    testRuntimeOnly("org.junit.jupiter:junit-jupiter-engine:5.11.3")
}

tasks.withType<Test> { useJUnitPlatform() }
```

- [ ] **Step 2: AndroidManifest**

Create `app/src/main/AndroidManifest.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <uses-permission android:name="android.permission.INTERNET"/>

    <application
        android:name=".KibbleApplication"
        android:label="@string/app_name"
        android:supportsRtl="true"
        android:theme="@android:style/Theme.Material.Light.NoActionBar">
        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:configChanges="orientation|keyboardHidden|screenSize|smallestScreenSize|screenLayout|uiMode">
            <intent-filter>
                <action android:name="android.intent.action.MAIN"/>
                <category android:name="android.intent.category.LAUNCHER"/>
            </intent-filter>
        </activity>
    </application>
</manifest>
```

- [ ] **Step 3: strings.xml**

Create `app/src/main/res/values/strings.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">Kibble</string>
</resources>
```

- [ ] **Step 4: Application class**

Create `app/src/main/kotlin/com/kibble/KibbleApplication.kt`:

```kotlin
package com.kibble

import android.app.Application
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class KibbleApplication : Application()
```

- [ ] **Step 5: FirebaseTokenProvider impl**

Create `app/src/main/kotlin/com/kibble/auth/FirebaseTokenProviderImpl.kt`:

```kotlin
package com.kibble.auth

import com.google.firebase.auth.FirebaseAuth
import com.kibble.core.network.FirebaseTokenProvider
import kotlinx.coroutines.tasks.await
import javax.inject.Inject

class FirebaseTokenProviderImpl @Inject constructor(
    private val firebaseAuth: FirebaseAuth,
) : FirebaseTokenProvider {
    override suspend fun currentToken(): String? {
        val user = firebaseAuth.currentUser ?: return null
        return user.getIdToken(false).await().token
    }
}
```

- [ ] **Step 6: Auth module (binds + Firebase singleton)**

Create `app/src/main/kotlin/com/kibble/auth/di/AuthModule.kt`:

```kotlin
package com.kibble.auth.di

import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.ktx.auth
import com.google.firebase.ktx.Firebase
import com.kibble.auth.FirebaseTokenProviderImpl
import com.kibble.core.network.FirebaseTokenProvider
import dagger.Binds
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class AuthBindingsModule {
    @Binds @Singleton
    abstract fun bindFirebaseTokenProvider(impl: FirebaseTokenProviderImpl): FirebaseTokenProvider
}

@Module
@InstallIn(SingletonComponent::class)
object AuthModule {
    @Provides @Singleton
    fun provideFirebaseAuth(): FirebaseAuth = Firebase.auth
}
```

- [ ] **Step 7: MainActivity (placeholder hosting just the theme)**

Create `app/src/main/kotlin/com/kibble/MainActivity.kt`:

```kotlin
package com.kibble

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.kibble.core.ui.theme.KibbleTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { KibbleApp() }
    }
}

@Composable
fun KibbleApp() {
    KibbleTheme {
        Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
            Box(contentAlignment = Alignment.Center, modifier = Modifier.fillMaxSize()) {
                Text("Kibble", style = MaterialTheme.typography.headlineLarge)
            }
        }
    }
}
```

- [ ] **Step 8: Build the app**

```bash
cd /Users/sdagguba/kibble-reorder/android
./gradlew :app:assembleDebug
```
Expected: BUILD SUCCESSFUL. Note: this will fail without `app/google-services.json`. If it fails due to that, prompt the user to add it before continuing.

- [ ] **Step 9: Commit**

```bash
cd /Users/sdagguba/kibble-reorder
git add android/app/
git commit -m "feat(android/app): Application class + MainActivity + Firebase token provider"
```

---

## Task 8: Auth bootstrap — splash → /auth/firebase → route

**Files:**
- Create: `app/src/main/kotlin/com/kibble/auth/AuthState.kt`
- Create: `app/src/main/kotlin/com/kibble/auth/AuthRepository.kt`
- Create: `app/src/main/kotlin/com/kibble/auth/AuthBootstrapViewModel.kt`
- Create: `app/src/main/kotlin/com/kibble/auth/AuthBootstrapScreen.kt`
- Create: `app/src/test/kotlin/com/kibble/auth/AuthBootstrapViewModelTest.kt`
- Modify: `app/src/main/kotlin/com/kibble/MainActivity.kt`

- [ ] **Step 1: AuthState**

Create `app/src/main/kotlin/com/kibble/auth/AuthState.kt`:

```kotlin
package com.kibble.auth

import java.util.UUID

sealed interface AuthState {
    data object Checking : AuthState
    data object SignedOut : AuthState
    data class SignedIn(val userId: UUID, val isNewUser: Boolean, val onboardingComplete: Boolean) : AuthState
    data class Error(val message: String) : AuthState
}
```

- [ ] **Step 2: AuthRepository**

Create `app/src/main/kotlin/com/kibble/auth/AuthRepository.kt`:

```kotlin
package com.kibble.auth

import com.google.firebase.auth.FirebaseAuth
import com.kibble.core.common.KibbleResult
import com.kibble.core.common.kibbleRunCatching
import com.kibble.core.database.dao.UserDao
import com.kibble.core.database.entity.UserEntity
import com.kibble.core.network.KibbleApi
import com.kibble.core.network.dto.FirebaseLoginRequest
import kotlinx.coroutines.tasks.await
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AuthRepository @Inject constructor(
    private val firebaseAuth: FirebaseAuth,
    private val api: KibbleApi,
    private val userDao: UserDao,
) {
    suspend fun bootstrap(): KibbleResult<AuthState> = kibbleRunCatching {
        val firebaseUser = firebaseAuth.currentUser ?: return@kibbleRunCatching AuthState.SignedOut
        val token = firebaseUser.getIdToken(false).await().token
            ?: return@kibbleRunCatching AuthState.SignedOut
        val resp = api.firebaseLogin(FirebaseLoginRequest(token))
        val userId = UUID.fromString(resp.user_id)
        // Cache locally so other modules can read it without a network round-trip
        userDao.upsert(
            UserEntity(
                id = userId,
                firebaseUid = firebaseUser.uid,
                email = resp.email,
                name = null, pincode = null,
                onboardingComplete = false,
            )
        )
        // Fetch full profile to know whether onboarding is complete
        val me = api.getMe()
        val onboardingComplete = me.name != null && me.pincode != null
        AuthState.SignedIn(userId = userId, isNewUser = resp.is_new_user, onboardingComplete = onboardingComplete)
    }

    suspend fun signOut() {
        firebaseAuth.signOut()
        userDao.clear()
    }
}
```

- [ ] **Step 3: ViewModel**

Create `app/src/main/kotlin/com/kibble/auth/AuthBootstrapViewModel.kt`:

```kotlin
package com.kibble.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.kibble.core.common.KibbleResult
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class AuthBootstrapViewModel @Inject constructor(
    private val repository: AuthRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<AuthState>(AuthState.Checking)
    val state: StateFlow<AuthState> = _state.asStateFlow()

    init { bootstrap() }

    fun bootstrap() {
        viewModelScope.launch {
            _state.value = AuthState.Checking
            _state.value = when (val r = repository.bootstrap()) {
                is KibbleResult.Success -> r.data
                is KibbleResult.Failure -> AuthState.Error(r.cause.message ?: "Auth failed")
            }
        }
    }
}
```

- [ ] **Step 4: Bootstrap screen**

Create `app/src/main/kotlin/com/kibble/auth/AuthBootstrapScreen.kt`:

```kotlin
package com.kibble.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun AuthBootstrapScreen(
    onSignedIn: (AuthState.SignedIn) -> Unit,
    onSignedOut: () -> Unit,
    viewModel: AuthBootstrapViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    when (val s = state) {
        AuthState.Checking -> Splash()
        AuthState.SignedOut -> { onSignedOut() }
        is AuthState.SignedIn -> { onSignedIn(s) }
        is AuthState.Error -> Splash(error = s.message)
    }
}

@Composable
private fun Splash(error: String? = null) {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("Kibble", style = MaterialTheme.typography.displayMedium)
        if (error != null) {
            Text(error, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.error)
        } else {
            CircularProgressIndicator()
        }
    }
}
```

- [ ] **Step 5: ViewModel test**

Create `app/src/test/kotlin/com/kibble/auth/AuthBootstrapViewModelTest.kt`:

```kotlin
package com.kibble.auth

import app.cash.turbine.test
import com.kibble.core.common.KibbleResult
import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import java.util.UUID

class AuthBootstrapViewModelTest {

    @BeforeEach fun setMainDispatcher() = Dispatchers.setMain(UnconfinedTestDispatcher())
    @AfterEach fun resetMainDispatcher() = Dispatchers.resetMain()

    @Test
    fun `bootstrap success emits SignedIn`() = runTest {
        val repo = mockk<AuthRepository>()
        coEvery { repo.bootstrap() } returns KibbleResult.Success(
            AuthState.SignedIn(UUID.randomUUID(), isNewUser = false, onboardingComplete = false)
        )
        val vm = AuthBootstrapViewModel(repo)
        vm.state.test {
            // First emission may be Checking, then SignedIn
            val s = expectMostRecentItem()
            assertTrue(s is AuthState.SignedIn)
        }
    }

    @Test
    fun `bootstrap failure emits Error`() = runTest {
        val repo = mockk<AuthRepository>()
        coEvery { repo.bootstrap() } returns KibbleResult.Failure(IllegalStateException("network"))
        val vm = AuthBootstrapViewModel(repo)
        vm.state.test {
            val s = expectMostRecentItem()
            assertTrue(s is AuthState.Error)
        }
    }
}
```

- [ ] **Step 6: Run tests**

```bash
cd /Users/sdagguba/kibble-reorder/android
./gradlew :app:test
```
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
cd /Users/sdagguba/kibble-reorder
git add android/app/
git commit -m "feat(android/auth): bootstrap flow — Firebase user check → /auth/firebase → cache → route"
```

---

## Task 9: Bottom-nav scaffold + placeholder destinations

**Files:**
- Create: `app/src/main/kotlin/com/kibble/navigation/KibbleDestinations.kt`
- Create: `app/src/main/kotlin/com/kibble/navigation/KibbleBottomNav.kt`
- Create: `app/src/main/kotlin/com/kibble/navigation/KibbleNavHost.kt`
- Create: `app/src/main/kotlin/com/kibble/home/HomePlaceholderScreen.kt`
- Create: `app/src/main/kotlin/com/kibble/orders/OrdersPlaceholderScreen.kt`
- Create: `app/src/main/kotlin/com/kibble/settings/SettingsPlaceholderScreen.kt`
- Modify: `app/src/main/kotlin/com/kibble/MainActivity.kt`

- [ ] **Step 1: Destinations**

Create `app/src/main/kotlin/com/kibble/navigation/KibbleDestinations.kt`:

```kotlin
package com.kibble.navigation

sealed class TopLevelDestination(val route: String, val label: String) {
    data object Home : TopLevelDestination("home", "Home")
    data object Orders : TopLevelDestination("orders", "Orders")
    data object Settings : TopLevelDestination("settings", "Settings")

    companion object {
        val All = listOf(Home, Orders, Settings)
    }
}

object Routes {
    const val AUTH_BOOTSTRAP = "auth-bootstrap"
    const val SIGN_IN = "sign-in"
    const val ONBOARDING = "onboarding"
    const val MAIN = "main"
}
```

- [ ] **Step 2: Bottom nav**

Create `app/src/main/kotlin/com/kibble/navigation/KibbleBottomNav.kt`:

```kotlin
package com.kibble.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Inventory2
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.navigation.NavHostController
import androidx.navigation.compose.currentBackStackEntryAsState

@Composable
fun KibbleBottomNav(navController: NavHostController) {
    val current by navController.currentBackStackEntryAsState()
    val currentRoute = current?.destination?.route
    NavigationBar {
        TopLevelDestination.All.forEach { dest ->
            val selected = currentRoute == dest.route
            NavigationBarItem(
                selected = selected,
                onClick = {
                    navController.navigate(dest.route) {
                        popUpTo(navController.graph.startDestinationId) { saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                },
                icon = {
                    Icon(
                        imageVector = when (dest) {
                            TopLevelDestination.Home -> Icons.Outlined.Home
                            TopLevelDestination.Orders -> Icons.Outlined.Inventory2
                            TopLevelDestination.Settings -> Icons.Outlined.Settings
                        },
                        contentDescription = dest.label,
                    )
                },
                label = { Text(dest.label.uppercase()) },
            )
        }
    }
}
```

- [ ] **Step 3: NavHost**

Create `app/src/main/kotlin/com/kibble/navigation/KibbleNavHost.kt`:

```kotlin
package com.kibble.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.kibble.auth.AuthBootstrapScreen
import com.kibble.home.HomePlaceholderScreen
import com.kibble.orders.OrdersPlaceholderScreen
import com.kibble.settings.SettingsPlaceholderScreen

@Composable
fun KibbleNavHost(rootNavController: NavHostController = rememberNavController()) {
    NavHost(navController = rootNavController, startDestination = Routes.AUTH_BOOTSTRAP) {
        composable(Routes.AUTH_BOOTSTRAP) {
            AuthBootstrapScreen(
                onSignedIn = { signedIn ->
                    val target = if (signedIn.onboardingComplete) Routes.MAIN else Routes.ONBOARDING
                    rootNavController.navigate(target) { popUpTo(Routes.AUTH_BOOTSTRAP) { inclusive = true } }
                },
                onSignedOut = {
                    rootNavController.navigate(Routes.SIGN_IN) { popUpTo(Routes.AUTH_BOOTSTRAP) { inclusive = true } }
                },
            )
        }
        composable(Routes.SIGN_IN) {
            // Placeholder until Plan 2b-ii. Users land here when not signed in;
            // we'll replace with the welcome + Firebase login screen there.
            com.kibble.auth.AuthBootstrapScreen(
                onSignedIn = { rootNavController.navigate(Routes.MAIN) { popUpTo(Routes.SIGN_IN) { inclusive = true } } },
                onSignedOut = { /* no-op — Plan 2b-ii implements actual sign-in */ },
            )
        }
        composable(Routes.ONBOARDING) {
            // Placeholder until Plan 2b-ii. Allow navigating into MAIN for shell preview.
            HomePlaceholderScreen(title = "Onboarding (Plan 2b-ii)")
        }
        composable(Routes.MAIN) {
            MainShell()
        }
    }
}

@Composable
private fun MainShell() {
    val nav = rememberNavController()
    Scaffold(bottomBar = { KibbleBottomNav(nav) }) { padding ->
        NavHost(
            navController = nav,
            startDestination = TopLevelDestination.Home.route,
            modifier = Modifier.padding(padding),
        ) {
            composable(TopLevelDestination.Home.route) { HomePlaceholderScreen("Home") }
            composable(TopLevelDestination.Orders.route) { OrdersPlaceholderScreen() }
            composable(TopLevelDestination.Settings.route) { SettingsPlaceholderScreen() }
        }
    }
}
```

- [ ] **Step 4: Placeholder screens**

Create `app/src/main/kotlin/com/kibble/home/HomePlaceholderScreen.kt`:

```kotlin
package com.kibble.home

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier

@Composable
fun HomePlaceholderScreen(title: String = "Home") {
    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Text(title, style = MaterialTheme.typography.headlineLarge, color = MaterialTheme.colorScheme.primary)
    }
}
```

Create `app/src/main/kotlin/com/kibble/orders/OrdersPlaceholderScreen.kt` and `app/src/main/kotlin/com/kibble/settings/SettingsPlaceholderScreen.kt` with the same shape (different title strings: "Orders" and "Settings").

```kotlin
package com.kibble.orders

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier

@Composable
fun OrdersPlaceholderScreen() {
    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Text("Orders", style = MaterialTheme.typography.headlineLarge, color = MaterialTheme.colorScheme.primary)
    }
}
```

```kotlin
package com.kibble.settings

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier

@Composable
fun SettingsPlaceholderScreen() {
    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Text("Settings", style = MaterialTheme.typography.headlineLarge, color = MaterialTheme.colorScheme.primary)
    }
}
```

- [ ] **Step 5: Wire NavHost into MainActivity**

Replace `app/src/main/kotlin/com/kibble/MainActivity.kt`:

```kotlin
package com.kibble

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.kibble.core.ui.theme.KibbleTheme
import com.kibble.navigation.KibbleNavHost
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { KibbleApp() }
    }
}

@Composable
fun KibbleApp() {
    KibbleTheme {
        Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
            KibbleNavHost()
        }
    }
}
```

- [ ] **Step 6: Build**

```bash
cd /Users/sdagguba/kibble-reorder/android
./gradlew :app:assembleDebug
```
Expected: BUILD SUCCESSFUL.

- [ ] **Step 7: Commit**

```bash
cd /Users/sdagguba/kibble-reorder
git add android/app/
git commit -m "feat(android/nav): NavHost shell with bottom nav + placeholder Home/Orders/Settings"
```

---

## Task 10: End-to-end smoke test against running backend

- [ ] **Step 1: Bring up the backend**

```bash
cd /Users/sdagguba/kibble-reorder
docker compose up -d
cd backend
uvicorn app.main:app --reload --port 8000 &
sleep 3
curl -s http://localhost:8000/health
```
Expected: `{"status":"ok"}`.

- [ ] **Step 2: Install the app on emulator**

In a separate terminal:

```bash
cd /Users/sdagguba/kibble-reorder/android
./gradlew :app:installDebug
```

Then launch the app from the emulator. The app should:
1. Show splash with "Kibble" + spinner
2. Detect that no Firebase user is signed in
3. Route to the `SIGN_IN` placeholder (will become a real screen in Plan 2b-ii)

This proves: theme renders, navigation initializes, Firebase Auth SDK is wired, `/auth/firebase` is reachable when a token exists.

- [ ] **Step 3: Manual Firebase signed-in test**

In Firebase console, create a test user (`test@example.com` / `Test1234!`). Temporarily, in `MainActivity.onCreate` add a one-shot test sign-in:

```kotlin
import com.google.firebase.auth.ktx.auth
import com.google.firebase.ktx.Firebase
// ...
override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    Firebase.auth.signInWithEmailAndPassword("test@example.com", "Test1234!")
    enableEdgeToEdge()
    setContent { KibbleApp() }
}
```

Re-run the app. The bootstrap should now: detect Firebase user → fetch ID token → call `POST /auth/firebase` (10.0.2.2 maps to localhost from emulator) → parse `user_id` → cache `UserEntity` → since name/pincode are null, route to `ONBOARDING` placeholder.

Verify in the backend logs (uvicorn) that `POST /auth/firebase` and `GET /users/me` were both called and returned 200.

- [ ] **Step 4: Remove the temporary sign-in line**

Delete the `Firebase.auth.signInWithEmailAndPassword(...)` line from `MainActivity` — Plan 2b-ii will replace it with a real welcome screen.

- [ ] **Step 5: Commit any minor fixes**

If anything was tweaked during smoke testing, commit those changes:

```bash
cd /Users/sdagguba/kibble-reorder
git status
git add -A android/
git commit -m "fix(android): smoke-test adjustments"
```

---

## Definition of Done

- [ ] `./gradlew build` succeeds across all modules
- [ ] `./gradlew test` runs the unit tests in `:core:common`, `:core:database`, `:core:network`, `:app` and all pass (~10 tests total)
- [ ] App installs on an Android emulator (API 26+) and shows the Kibble splash + theme
- [ ] When a Firebase user is signed in, the app calls `POST /auth/firebase`, caches the user row in Room, and routes to the appropriate post-auth destination
- [ ] When no Firebase user is signed in, the app routes to the `SIGN_IN` placeholder
- [ ] Bottom nav switches between Home / Orders / Settings placeholders
- [ ] Light + dark theme both render with correct Deep Botanical colors
- [ ] No `google-services.json` is committed (gitignored)

---

## Notes for the Implementer

- **API base URL:** `BuildConfig.API_BASE_URL` is `http://10.0.2.2:8000/` for debug — that's the emulator's loopback to the host's `localhost:8000`. On a physical device, replace with the host's LAN IP.
- **Java version:** must be 17 to compile this project (toolchain pinned). Verify with `java -version`.
- **`google-services.json`:** the user must place this file at `android/app/google-services.json`. The `google-services` Gradle plugin reads it at build time. If missing, `:app:processDebugGoogleServices` will fail.
- **First Gradle build is slow:** downloads AGP, Kotlin, Compose BOM, Hilt, Firebase, Room, Retrofit, Robolectric. Subsequent builds use the cache.
- **Robolectric tests:** `:core:database` tests run on JVM via Robolectric. These tests are slower than pure JVM tests but faster than instrumented tests. If they hang on first run, ensure `testOptions.unitTests.isIncludeAndroidResources = true` is set.
- **Hilt + KSP:** if you see "InjectAdapter not generated" or similar, run `./gradlew :app:kspDebugKotlin --info` to debug. Most issues are Hilt module placement (must be in a module that applies the Hilt plugin).
- **Compose previews don't render fonts:** Google Fonts download fails in the IDE preview. Fonts work fine on the emulator/device.
- **Plan 2b-ii** picks up at the welcome screen and onboarding flow. **Plan 2b-iii** picks up the home screen, orders, settings, BLE service, and FCM.
