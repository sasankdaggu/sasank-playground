# Plan 2b-iii — Android Main App + BLE + FCM

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Complete the Android app on top of Plans 2b-i and 2b-ii. Adds Home (kibble container hero + forecast chart), Orders (stub empty state), Settings (sectioned with retailer management), the BLE foreground service that reads the MokoSmart S02R sensor every 6 hours and on demand, and FCM push notifications with quiet-hours support.

**Architecture:** Three new feature modules (`:feature:home`, `:feature:orders`, `:feature:settings`) and one new service module (`:service:ble`). BLE service writes readings to Room; UI observes Room via repositories — UI never talks to the service directly. FCM `MessagingService` posts to a `low_stock` notification channel; quiet-hours filter applied client-side as a defensive layer.

**Tech additions:** `androidx.work:work-runtime-ktx`, `androidx.hilt:hilt-work`, `firebase-messaging-ktx`, MokoSmart S02R Android SDK (vendor-supplied AAR — placed at `android/libs/mokosmart-s02r-1.0.aar`).

**Spec:** `/Users/sdagguba/sasank-playground/docs/superpowers/specs/2026-04-30-kibble-android-app-design.md` (Sections 7, 10, 11)

---

## Prerequisites

- Plans 2b-i and 2b-ii complete and merged
- MokoSmart S02R SDK AAR placed at `android/libs/mokosmart-s02r-1.0.aar` (or its actual filename per vendor docs)
- A real MokoSmart S02R sensor available for hardware smoke testing
- FCM enabled in Firebase console with a valid `google-services.json`
- `BLUETOOTH_SCAN`, `BLUETOOTH_CONNECT`, `POST_NOTIFICATIONS`, `FOREGROUND_SERVICE` runtime permissions handled

---

## File Structure (additions)

```
android/
├── libs/mokosmart-s02r-1.0.aar
├── service/ble/
│   └── src/main/kotlin/com/kibble/service/ble/
│       ├── BleSensorClient.kt              (interface — wraps MokoSmart SDK)
│       ├── MokoSmartBleClient.kt           (real impl using vendor SDK)
│       ├── FakeBleClient.kt                (test/dev impl)
│       ├── BleForegroundService.kt
│       ├── BleReadWorker.kt                (WorkManager — 6h periodic)
│       ├── ReadingSyncWorker.kt            (uploads unsynced rows)
│       └── di/BleModule.kt
├── feature/home/
│   └── src/main/kotlin/com/kibble/feature/home/
│       ├── HomeViewModel.kt
│       ├── HomeIntent.kt
│       ├── HomeState.kt
│       ├── HomeScreen.kt
│       └── components/
│           ├── KibbleContainer.kt          (the hero illustration)
│           └── ForecastChart.kt            (the editorial single-curve chart)
├── feature/orders/
│   └── src/main/kotlin/com/kibble/feature/orders/OrdersScreen.kt
├── feature/settings/
│   └── src/main/kotlin/com/kibble/feature/settings/
│       ├── SettingsViewModel.kt
│       ├── SettingsState.kt
│       ├── SettingsIntent.kt
│       ├── SettingsScreen.kt
│       └── retailers/AddRetailerSheet.kt
└── app/src/main/kotlin/com/kibble/notifications/
    ├── KibbleMessagingService.kt
    └── NotificationChannels.kt
```

---

## Task 1: `:service:ble` module setup

- [ ] **Step 1: Add module to settings**

`settings.gradle.kts`: `include(":service:ble")`

- [ ] **Step 2: Module build script**

`service/ble/build.gradle.kts`:

```kotlin
plugins {
    id("kibble.android.library")
    id("kibble.android.hilt")
}

android {
    namespace = "com.kibble.service.ble"
    defaultConfig {
        consumerProguardFiles("consumer-rules.pro")
    }
}

dependencies {
    implementation(project(":core:common"))
    implementation(project(":core:network"))
    implementation(project(":core:database"))

    implementation(libs.androidx.core.ktx)
    implementation(libs.work.runtime.ktx)
    implementation(libs.hilt.work)
    ksp(libs.hilt.compiler)
    implementation(libs.coroutines.core)

    // Vendor SDK
    implementation(files("../../libs/mokosmart-s02r-1.0.aar"))

    testImplementation(libs.junit.jupiter)
    testImplementation(libs.coroutines.test)
    testImplementation(libs.mockk)
    testRuntimeOnly("org.junit.jupiter:junit-jupiter-engine:5.11.3")
}

tasks.withType<Test> { useJUnitPlatform() }
```

- [ ] **Step 3: BleSensorClient interface**

```kotlin
package com.kibble.service.ble

interface BleSensorClient {
    suspend fun connect(deviceId: String): Boolean
    suspend fun readDistanceMm(): Double?
    suspend fun disconnect()
}
```

- [ ] **Step 4: FakeBleClient (used in tests + dev builds without real sensor)**

```kotlin
package com.kibble.service.ble

import javax.inject.Inject
import kotlin.random.Random

class FakeBleClient @Inject constructor() : BleSensorClient {
    private var connected = false
    override suspend fun connect(deviceId: String): Boolean {
        connected = true
        return true
    }
    override suspend fun readDistanceMm(): Double? =
        if (connected) 100.0 + Random.nextDouble(0.0, 200.0) else null
    override suspend fun disconnect() { connected = false }
}
```

- [ ] **Step 5: MokoSmartBleClient (skeleton — implementer fills in vendor SDK calls)**

```kotlin
package com.kibble.service.ble

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject

class MokoSmartBleClient @Inject constructor(
    @ApplicationContext private val context: Context,
) : BleSensorClient {
    // TODO(vendor SDK integration): replace with actual MokoSmart S02R SDK calls.
    // Reference: SDK docs ship with the AAR. The SDK exposes a singleton like
    //   MokoSupport.getInstance().init(context); MokoSupport.connDevice(mac, callback)
    // Map the vendor's distance value (likely cm or mm) to mm.

    override suspend fun connect(deviceId: String): Boolean { TODO("vendor SDK call") }
    override suspend fun readDistanceMm(): Double? { TODO("vendor SDK call — return mm") }
    override suspend fun disconnect() { TODO("vendor SDK call") }
}
```

- [ ] **Step 6: BleModule (Hilt — choose impl by build type)**

```kotlin
package com.kibble.service.ble.di

import com.kibble.service.ble.BleSensorClient
import com.kibble.service.ble.FakeBleClient
import com.kibble.service.ble.MokoSmartBleClient
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class BleModule {
    // Switch to FakeBleClient binding for tests/dev.
    @Binds @Singleton
    abstract fun bindClient(impl: MokoSmartBleClient): BleSensorClient
}
```

- [ ] **Step 7: Commit**

```bash
cd /Users/sdagguba/kibble-reorder && git add android/ && git commit -m "feat(android/ble): module setup + BleSensorClient interface + Fake/MokoSmart impls"
```

---

## Task 2: BleForegroundService + ReadingRepository

**Files:**
- Create: `service/ble/.../BleForegroundService.kt`
- Create: `service/ble/.../ReadingRepository.kt`

- [ ] **Step 1: Foreground service**

```kotlin
package com.kibble.service.ble

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import javax.inject.Inject

@AndroidEntryPoint
class BleForegroundService : Service() {

    @Inject lateinit var readingRepository: ReadingRepository

    private val job = SupervisorJob()
    private val scope = CoroutineScope(job)

    override fun onCreate() {
        super.onCreate()
        startForeground(NOTIFICATION_ID, buildNotification())
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_READ_NOW) {
            scope.launch { readingRepository.readAndStore() }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        job.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun buildNotification(): Notification {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(CHANNEL_ID, "Kibble monitor", NotificationManager.IMPORTANCE_LOW)
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Kibble monitor active")
            .setContentText("Watching your kibble level")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    companion object {
        const val CHANNEL_ID = "kibble_monitor"
        const val NOTIFICATION_ID = 1001
        const val ACTION_READ_NOW = "com.kibble.ble.READ_NOW"
    }
}
```

- [ ] **Step 2: ReadingRepository**

```kotlin
package com.kibble.service.ble

import com.kibble.core.database.dao.BinDao
import com.kibble.core.database.dao.SensorReadingDao
import com.kibble.core.database.entity.SensorReadingEntity
import com.kibble.core.network.KibbleApi
import com.kibble.core.network.dto.SensorReadingRequest
import kotlinx.coroutines.flow.firstOrNull
import java.time.Instant
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ReadingRepository @Inject constructor(
    private val client: BleSensorClient,
    private val binDao: BinDao,
    private val sensorDao: SensorReadingDao,
    private val api: KibbleApi,
) {
    suspend fun readAndStore() {
        // Pick the active bin. For Plan 2 (single-bin app), take the first.
        val bin = binDao.observeForUser(UUID.fromString("00000000-0000-0000-0000-000000000000")).firstOrNull()?.firstOrNull()
            ?: return
        client.connect(bin.sensorDeviceId)
        val mm = client.readDistanceMm() ?: return.also { client.disconnect() }
        client.disconnect()

        val reading = SensorReadingEntity(
            id = UUID.randomUUID(), binId = bin.id, distanceMm = mm,
            timestamp = System.currentTimeMillis(), synced = false,
        )
        sensorDao.upsert(reading)

        // Try sync immediately
        runCatching {
            api.postReading(bin.id.toString(), SensorReadingRequest(mm, Instant.ofEpochMilli(reading.timestamp).toString()))
            sensorDao.markSynced(reading.id)
        }
    }
}
```

- [ ] **Step 3: Manifest entry**

In `service/ble/src/main/AndroidManifest.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.BLUETOOTH_SCAN" android:usesPermissionFlags="neverForLocation"/>
    <uses-permission android:name="android.permission.BLUETOOTH_CONNECT"/>
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE"/>
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_CONNECTED_DEVICE"/>
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>

    <application>
        <service
            android:name=".BleForegroundService"
            android:foregroundServiceType="connectedDevice"
            android:exported="false"/>
    </application>
</manifest>
```

- [ ] **Step 4: Test**

```kotlin
package com.kibble.service.ble

// Test that ReadingRepository: connects → reads → writes to Room → POSTs to API → marks synced.
// Use FakeBleClient + mockk for DAOs and KibbleApi.
```

(Implementer writes the actual test; the rest of the suite uses a similar pattern.)

- [ ] **Step 5: Commit**

```bash
git add android/ && git commit -m "feat(android/ble): foreground service + ReadingRepository (read → Room → sync)"
```

---

## Task 3: BleReadWorker + ReadingSyncWorker (WorkManager)

**Files:**
- Create: `service/ble/.../BleReadWorker.kt`
- Create: `service/ble/.../ReadingSyncWorker.kt`
- Modify: `app/.../KibbleApplication.kt` (schedule the periodic worker after onboarding completes)

- [ ] **Step 1: Periodic read worker**

```kotlin
package com.kibble.service.ble

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject

@HiltWorker
class BleReadWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val readingRepository: ReadingRepository,
) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        return runCatching { readingRepository.readAndStore() }
            .map { Result.success() }
            .getOrDefault(Result.retry())
    }
}
```

- [ ] **Step 2: Sync worker (uploads any unsynced readings)**

```kotlin
package com.kibble.service.ble

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.kibble.core.database.dao.SensorReadingDao
import com.kibble.core.network.KibbleApi
import com.kibble.core.network.dto.SensorReadingRequest
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.time.Instant

@HiltWorker
class ReadingSyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val sensorDao: SensorReadingDao,
    private val api: KibbleApi,
) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val pending = sensorDao.unsynced()
        for (reading in pending) {
            runCatching {
                api.postReading(
                    reading.binId.toString(),
                    SensorReadingRequest(reading.distanceMm, Instant.ofEpochMilli(reading.timestamp).toString()),
                )
                sensorDao.markSynced(reading.id)
            }.onFailure { return Result.retry() }
        }
        return Result.success()
    }
}
```

- [ ] **Step 3: Schedule from KibbleApplication**

```kotlin
package com.kibble

import android.app.Application
import androidx.hilt.work.HiltWorkerFactory
import androidx.work.Configuration
import androidx.work.Constraints
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import com.kibble.service.ble.BleReadWorker
import com.kibble.service.ble.ReadingSyncWorker
import dagger.hilt.android.HiltAndroidApp
import java.util.concurrent.TimeUnit
import javax.inject.Inject

@HiltAndroidApp
class KibbleApplication : Application(), Configuration.Provider {
    @Inject lateinit var workerFactory: HiltWorkerFactory

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder().setWorkerFactory(workerFactory).build()

    override fun onCreate() {
        super.onCreate()
        scheduleWorkers()
    }

    private fun scheduleWorkers() {
        val wm = WorkManager.getInstance(this)

        wm.enqueueUniquePeriodicWork(
            "ble-read",
            androidx.work.ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<BleReadWorker>(6, TimeUnit.HOURS).build(),
        )

        wm.enqueueUniquePeriodicWork(
            "reading-sync",
            androidx.work.ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<ReadingSyncWorker>(15, TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build(),
        )
    }
}
```

- [ ] **Step 4: Commit**

```bash
git add android/ && git commit -m "feat(android/ble): WorkManager periodic readers + sync worker"
```

---

## Task 4: `:feature:home` — Home screen with hero illustration + forecast chart

**Files:**
- Create: `feature/home/...` per file structure above

- [ ] **Step 1: Module setup** — same shape as `:feature:onboarding`

- [ ] **Step 2: HomeState / HomeIntent**

```kotlin
package com.kibble.feature.home

import com.kibble.core.network.dto.ForecastResponse
import com.kibble.core.database.entity.SensorReadingEntity

data class HomeState(
    val isLoading: Boolean = true,
    val levelPct: Double? = null,
    val daysRemaining: Int? = null,
    val nextRefillDate: String? = null,
    val forecast: ForecastResponse? = null,
    val latestReading: SensorReadingEntity? = null,
    val bleConnected: Boolean = false,
    val lowStock: Boolean = false,
    val statusWord: String = "Steady", // Steady | Falling | Climbing | Learning
    val error: String? = null,
)

sealed class HomeIntent {
    data object OnTapReadNow : HomeIntent()
    data object OnRefresh : HomeIntent()
    data class OnToggleAutoOrder(val enabled: Boolean) : HomeIntent()
}
```

- [ ] **Step 3: HomeViewModel**

```kotlin
package com.kibble.feature.home

import android.content.Context
import android.content.Intent
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.kibble.core.database.dao.BinDao
import com.kibble.core.database.dao.SensorReadingDao
import com.kibble.core.database.dao.UserDao
import com.kibble.core.network.KibbleApi
import com.kibble.service.ble.BleForegroundService
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class HomeViewModel @Inject constructor(
    @ApplicationContext private val context: Context,
    private val userDao: UserDao,
    private val binDao: BinDao,
    private val sensorDao: SensorReadingDao,
    private val api: KibbleApi,
) : ViewModel() {

    private val _state = MutableStateFlow(HomeState())
    val state = _state.asStateFlow()

    init {
        viewModelScope.launch { observe() }
    }

    private suspend fun observe() {
        val user = userDao.first() ?: return
        val bin = binDao.observeForUser(user.id).firstOrNull()?.firstOrNull() ?: return
        sensorDao.observeLatest(bin.id).collect { latest ->
            // Refresh forecast each time a new reading arrives
            val forecast = runCatching { api.getForecast(bin.id.toString()) }.getOrNull()
            _state.value = _state.value.copy(
                isLoading = false,
                latestReading = latest,
                forecast = forecast,
                levelPct = forecast?.historical?.lastOrNull()?.level_pct,
                lowStock = (forecast?.historical?.lastOrNull()?.level_pct ?: 100.0) <= (forecast?.reorder_threshold_pct ?: 20),
                statusWord = computeStatus(forecast),
            )
        }
    }

    fun handle(intent: HomeIntent) {
        when (intent) {
            HomeIntent.OnTapReadNow -> {
                val intent = Intent(context, BleForegroundService::class.java).apply {
                    action = BleForegroundService.ACTION_READ_NOW
                }
                context.startForegroundService(intent)
            }
            HomeIntent.OnRefresh -> viewModelScope.launch { observe() }
            is HomeIntent.OnToggleAutoOrder -> {
                // wires to user.auto_order_enabled — Plan 2b-iii leaves this as no-op for now
            }
        }
    }

    private fun computeStatus(f: com.kibble.core.network.dto.ForecastResponse?): String {
        if (f == null || f.status == "insufficient_data") return "Learning"
        // Compare last 7-day actual slope vs. forecast slope. Simple heuristic:
        val recent = f.historical.takeLast(7)
        if (recent.size < 2) return "Steady"
        val actualSlope = (recent.first().level_pct - recent.last().level_pct) / recent.size
        val expectedSlope = ((f.forecast.firstOrNull()?.level_pct ?: 0.0) - (f.forecast.lastOrNull()?.level_pct ?: 0.0)) / f.forecast.size.coerceAtLeast(1)
        return when {
            actualSlope > expectedSlope * 1.2 -> "Falling"
            actualSlope < expectedSlope * 0.8 -> "Climbing"
            else -> "Steady"
        }
    }
}
```

- [ ] **Step 4: KibbleContainer Composable (the hero)**

`components/KibbleContainer.kt`:

```kotlin
package com.kibble.feature.home.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.unit.dp

@Composable
fun KibbleContainer(
    levelPct: Double,
    lowStock: Boolean,
    primaryColor: Color,
    sageColor: Color,
    fillColor: Color,
    warningColor: Color,
    modifier: Modifier = Modifier,
) {
    Canvas(modifier = modifier.size(width = 200.dp, height = 240.dp)) {
        val w = size.width
        val h = size.height
        val bodyTop = h * 0.30f
        val bodyBottom = h * 0.94f
        val bodyLeft = w * 0.20f
        val bodyRight = w * 0.80f
        val cornerR = 24f

        val bodyPath = Path().apply {
            moveTo(bodyLeft, bodyTop + cornerR)
            quadraticBezierTo(bodyLeft, bodyTop, bodyLeft + cornerR, bodyTop)
            lineTo(bodyRight - cornerR, bodyTop)
            quadraticBezierTo(bodyRight, bodyTop, bodyRight, bodyTop + cornerR)
            lineTo(bodyRight, bodyBottom - cornerR)
            quadraticBezierTo(bodyRight, bodyBottom, bodyRight - cornerR, bodyBottom)
            lineTo(bodyLeft + cornerR, bodyBottom)
            quadraticBezierTo(bodyLeft, bodyBottom, bodyLeft, bodyBottom - cornerR)
            close()
        }

        // Body fill (sage)
        drawPath(bodyPath, color = sageColor)
        // Body outline
        drawPath(bodyPath, color = primaryColor, style = Stroke(width = 4f))

        // Fill clipped to body
        clipPath(bodyPath) {
            val fillTop = bodyBottom - (bodyBottom - bodyTop) * (levelPct.toFloat() / 100f).coerceIn(0f, 1f)
            drawRect(
                color = if (lowStock) warningColor else fillColor,
                topLeft = Offset(bodyLeft, fillTop),
                size = Size(bodyRight - bodyLeft, bodyBottom - fillTop),
            )
        }

        // Lid (forest)
        drawRoundRect(
            color = primaryColor,
            topLeft = Offset(bodyLeft - 8f, bodyTop - 28f),
            size = Size((bodyRight - bodyLeft) + 16f, 28f),
            cornerRadius = androidx.compose.ui.geometry.CornerRadius(8f),
        )

        // Knob
        drawOval(
            color = Color(0xFF98D2BF),
            topLeft = Offset(w / 2 - 16f, bodyTop - 36f),
            size = Size(32f, 14f),
        )
    }
}
```

- [ ] **Step 5: ForecastChart Composable (single editorial S-curve)**

`components/ForecastChart.kt`:

```kotlin
package com.kibble.feature.home.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import com.kibble.core.network.dto.ForecastPoint

@Composable
fun ForecastChart(
    historical: List<ForecastPoint>,
    forecast: List<ForecastPoint>,
    forestColor: Color,
    modifier: Modifier = Modifier,
) {
    Canvas(modifier = modifier.fillMaxWidth().height(140.dp)) {
        val w = size.width
        val h = size.height
        val all = historical + forecast
        if (all.size < 2) return@Canvas

        val maxPct = 100f
        val xStep = w / (all.size - 1)

        // Subtle left axis
        drawLine(forestColor.copy(alpha = 0.18f), Offset(2f, 6f), Offset(2f, h - 10f), strokeWidth = 1f)

        val path = Path()
        all.forEachIndexed { i, point ->
            val x = i * xStep
            val y = h - (point.level_pct.toFloat() / maxPct) * (h - 16f) - 8f
            if (i == 0) path.moveTo(x, y) else {
                val prev = all[i - 1]
                val px = (i - 1) * xStep
                val py = h - (prev.level_pct.toFloat() / maxPct) * (h - 16f) - 8f
                // Smooth cubic
                path.cubicTo(px + xStep * 0.4f, py, x - xStep * 0.4f, y, x, y)
            }
        }
        drawPath(path, color = forestColor, style = Stroke(width = 4f, cap = androidx.compose.ui.graphics.StrokeCap.Round))
    }
}
```

- [ ] **Step 6: HomeScreen**

```kotlin
package com.kibble.feature.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.kibble.core.network.dto.ForecastPoint
import com.kibble.feature.home.components.ForecastChart
import com.kibble.feature.home.components.KibbleContainer

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(viewModel: HomeViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            CenterAlignedTopAppBar(
                title = { Text("Kibble", style = MaterialTheme.typography.titleLarge.copy(fontStyle = FontStyle.Italic)) },
                colors = TopAppBarDefaults.centerAlignedTopAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = MaterialTheme.colorScheme.onPrimary,
                ),
            )
        },
        containerColor = MaterialTheme.colorScheme.background,
    ) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding).padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {

            KibbleContainer(
                levelPct = state.levelPct ?: 0.0,
                lowStock = state.lowStock,
                primaryColor = MaterialTheme.colorScheme.primary,
                sageColor = MaterialTheme.colorScheme.secondaryContainer,
                fillColor = MaterialTheme.colorScheme.primary,
                warningColor = MaterialTheme.colorScheme.tertiary,
            )
            Spacer(Modifier.height(8.dp))
            Text(
                "${state.levelPct?.toInt() ?: "--"}%",
                style = MaterialTheme.typography.displayLarge,
                color = if (state.lowStock) MaterialTheme.colorScheme.tertiary else MaterialTheme.colorScheme.primary,
            )
            Text(
                state.daysRemaining?.let { "About $it days of food left" } ?: "Calibrating…",
                style = MaterialTheme.typography.headlineSmall,
            )
            Spacer(Modifier.height(24.dp))

            // Forecast card
            Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("CONSUMPTION FORECAST", style = MaterialTheme.typography.labelSmall, modifier = Modifier.weight(1f))
                        Text(state.statusWord, style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.primary)
                    }
                    Spacer(Modifier.height(12.dp))
                    ForecastChart(
                        historical = state.forecast?.historical ?: emptyList(),
                        forecast = state.forecast?.forecast ?: emptyList(),
                        forestColor = MaterialTheme.colorScheme.primary,
                    )
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                        Text("Today", style = MaterialTheme.typography.bodySmall)
                        Text("Halfway", style = MaterialTheme.typography.bodySmall)
                        Text("Empty", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            Spacer(Modifier.height(16.dp))
            Button(
                onClick = { viewModel.handle(HomeIntent.OnTapReadNow) },
                modifier = Modifier.fillMaxWidth(),
            ) { Text("READ NOW") }
        }
    }
}
```

- [ ] **Step 7: Wire into MainShell** — replace the Home placeholder with `HomeScreen()`

- [ ] **Step 8: Commit**

---

## Task 5: `:feature:orders` — Empty state stub

**Files:**
- Create: `feature/orders/build.gradle.kts`
- Create: `feature/orders/src/main/kotlin/com/kibble/feature/orders/OrdersScreen.kt`

```kotlin
package com.kibble.feature.orders

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import androidx.compose.ui.text.font.FontStyle

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun OrdersScreen() {
    Scaffold(
        topBar = {
            CenterAlignedTopAppBar(
                title = { Text("Kibble", style = MaterialTheme.typography.titleLarge.copy(fontStyle = FontStyle.Italic)) },
                colors = TopAppBarDefaults.centerAlignedTopAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = MaterialTheme.colorScheme.onPrimary,
                ),
            )
        },
        containerColor = MaterialTheme.colorScheme.background,
    ) { padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).padding(40.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Box(modifier = Modifier.size(220.dp).clip(CircleShape).background(MaterialTheme.colorScheme.secondaryContainer))
            Spacer(Modifier.height(40.dp))
            Text("Auto-order activates soon", style = MaterialTheme.typography.headlineSmall)
            Spacer(Modifier.height(16.dp))
            Text(
                "We're learning Buddy's eating pattern. As soon as we know your kibble's rhythm, we'll find the best deal and arrange the next refill — right on time.",
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}
```

Wire into MainShell. Commit.

---

## Task 6: `:feature:settings` — sectioned settings + Add Retailer sheet

**Files:**
- Create: `feature/settings/...` per file structure

This task is large but follows the existing pattern. Provide:

- `SettingsState` with all the fields (threshold, payment mode, pack size, retailers, quiet hours)
- `SettingsViewModel` that observes Room (for current user) + calls `KibbleApi` on changes
- `SettingsScreen` — sectioned `LazyColumn` with sage cards per section
- `AddRetailerSheet` — `ModalBottomSheet` reusing `RetailerCatalog` and `CookieLoginScreen`/`CredentialLoginScreen` from `:feature:onboarding` (declare `:feature:onboarding` as a dependency or extract those into a shared `:feature:retailer` module — extracting is cleaner; do that as a refactor)

Commit.

---

## Task 7: FCM integration

**Files:**
- Create: `app/src/main/kotlin/com/kibble/notifications/NotificationChannels.kt`
- Create: `app/src/main/kotlin/com/kibble/notifications/KibbleMessagingService.kt`
- Modify: `app/src/main/AndroidManifest.xml`

- [ ] **Step 1: NotificationChannels**

```kotlin
package com.kibble.notifications

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build

object NotificationChannels {
    const val LOW_STOCK = "low_stock"
    const val SENSOR_DISCONNECTED = "sensor_disconnected"
    const val FOREGROUND = "kibble_monitor"

    fun ensure(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val mgr = context.getSystemService(NotificationManager::class.java)
        mgr.createNotificationChannel(NotificationChannel(LOW_STOCK, "Low stock alerts", NotificationManager.IMPORTANCE_HIGH))
        mgr.createNotificationChannel(NotificationChannel(SENSOR_DISCONNECTED, "Sensor disconnected", NotificationManager.IMPORTANCE_DEFAULT))
    }
}
```

- [ ] **Step 2: KibbleMessagingService**

```kotlin
package com.kibble.notifications

import android.app.PendingIntent
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.kibble.MainActivity
import com.kibble.R
import dagger.hilt.android.AndroidEntryPoint
import java.time.LocalTime
import java.time.ZoneId

@AndroidEntryPoint
class KibbleMessagingService : FirebaseMessagingService() {

    override fun onCreate() {
        super.onCreate()
        NotificationChannels.ensure(this)
    }

    override fun onMessageReceived(message: RemoteMessage) {
        // Quiet-hours filter (defensive — backend already honors them)
        if (insideQuietHours()) return

        val data = message.data
        val channel = when (data["type"]) {
            "low_stock" -> NotificationChannels.LOW_STOCK
            "sensor_disconnected" -> NotificationChannels.SENSOR_DISCONNECTED
            else -> NotificationChannels.LOW_STOCK
        }
        val title = message.notification?.title ?: data["title"] ?: "Kibble"
        val body = message.notification?.body ?: data["body"] ?: ""

        val intent = Intent(this, MainActivity::class.java).apply { flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP }
        val pi = PendingIntent.getActivity(this, 0, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

        val notification = NotificationCompat.Builder(this, channel)
            .setSmallIcon(R.drawable.ic_kibble_notification)
            .setContentTitle(title)
            .setContentText(body)
            .setAutoCancel(true)
            .setContentIntent(pi)
            .build()

        NotificationManagerCompat.from(this).notify(System.currentTimeMillis().toInt(), notification)
    }

    override fun onNewToken(token: String) {
        // TODO(Plan 2b-iii follow-up): POST the FCM token to the backend so it can target this device.
    }

    private fun insideQuietHours(): Boolean {
        // Reads quiet hours from local cache; defaults to 22:00–08:00 IST.
        val zone = ZoneId.of("Asia/Kolkata")
        val now = LocalTime.now(zone)
        val start = LocalTime.of(22, 0)
        val end = LocalTime.of(8, 0)
        return if (start.isBefore(end)) now.isAfter(start) && now.isBefore(end)
        else now.isAfter(start) || now.isBefore(end)
    }
}
```

- [ ] **Step 3: Manifest entry**

In `app/src/main/AndroidManifest.xml`:

```xml
<service
    android:name=".notifications.KibbleMessagingService"
    android:exported="false">
    <intent-filter>
        <action android:name="com.google.firebase.MESSAGING_EVENT" />
    </intent-filter>
</service>

<meta-data
    android:name="com.google.firebase.messaging.default_notification_channel_id"
    android:value="low_stock" />
```

Provide a placeholder `app/src/main/res/drawable/ic_kibble_notification.xml` (24×24 monochrome forest silhouette of a kibble piece) — the implementer creates a vector drawable.

- [ ] **Step 4: Commit**

---

## Task 8: End-to-end smoke test

- [ ] **Step 1: Bring up backend, install fresh app on emulator + complete onboarding**
- [ ] **Step 2: Pair with a real MokoSmart S02R sensor**
- [ ] **Step 3: Verify BLE foreground service starts and reads after 6 hours (or trigger via "Read now")**
- [ ] **Step 4: Verify Home screen updates with new readings**
- [ ] **Step 5: Trigger a low-stock FCM from backend (manual curl) and verify push appears with correct channel + body**
- [ ] **Step 6: Test quiet hours by adjusting system time to 23:00 IST and confirming no notification surfaces**
- [ ] **Step 7: Final commit + tag release v0.1.0**

```bash
cd /Users/sdagguba/kibble-reorder && git tag v0.1.0 && git push origin v0.1.0
```

---

## Definition of Done

- [ ] BLE service runs as a foreground service with the expected notification
- [ ] WorkManager schedules `BleReadWorker` every 6 hours and `ReadingSyncWorker` every 15 minutes
- [ ] Home screen renders the kibble container hero, the editorial single-curve forecast chart, and the dynamic Steady/Falling/Climbing/Learning status word
- [ ] "Read now" button triggers an immediate read via `BleForegroundService`
- [ ] Orders screen renders the empty-state stub with kibble-appropriate copy
- [ ] Settings screen renders all sections, persists preference changes, and supports adding/removing retailers
- [ ] FCM low-stock pushes arrive on the `low_stock` channel and respect quiet hours
- [ ] App tested with a real MokoSmart S02R sensor end-to-end

---

## Notes for the Implementer

- **MokoSmart SDK:** the exact API depends on the AAR vendor docs. The skeleton in `MokoSmartBleClient.kt` has `TODO`s where the implementer wires the actual SDK calls. The vendor SDK typically exposes a singleton entry point with `init(context)`, `connDevice(mac, callback)`, `getDistance(callback)` patterns. Map the returned distance unit to mm.
- **WorkManager + Hilt:** requires `@HiltAndroidApp` on Application + `Configuration.Provider` interface implementation + `HiltWorkerFactory` injection. Already wired in Task 3. If `HiltWorkerFactory` doesn't inject, ensure the `androidx.hilt:hilt-work` dependency is in the right module.
- **FCM token registration:** in production you POST the token to the backend so the server can target the device. We deferred that endpoint here because Plan 2a doesn't define it. Add `POST /users/{id}/fcm-tokens` in a follow-up.
- **Notification icon:** Android requires a monochrome silhouette. A green-tinted color icon won't render correctly. Make `ic_kibble_notification` a single-color vector drawable.
- **Quiet-hours timezone:** hard-coded `Asia/Kolkata` here — Plan 2a stores the user's timezone via `PATCH /users/{id}/quiet-hours`, so update the messaging service to read the cached timezone from Room in a follow-up.
- **The hero illustration in `KibbleContainer.kt`** is a Canvas approximation of the visual companion mockup. It's not pixel-perfect — for production polish, replace with a Lottie animation or a designed SVG/vector drawable.
