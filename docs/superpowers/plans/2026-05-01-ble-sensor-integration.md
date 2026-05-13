# MokoSmart S02R BLE Sensor Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `FakeBleClient` stub with a real BLE implementation that connects to the MokoSmart S02R sensor, reads the distance value, and feeds it into the existing ReadingRepository → Room → backend pipeline.

**Architecture:** Android's native BLE GATT API is used directly (no vendor AAR required — the SDK is not publicly distributed). A new `SensorPairing` screen is inserted into onboarding between Container and Calibrate so the user selects their physical sensor and its MAC address is stored on the bin. `MokoSmartBleClient` uses `CompletableDeferred` to bridge the GATT callback API into coroutines.

**Tech Stack:** Android BluetoothLeScanner, BluetoothGatt, callbackFlow, CompletableDeferred, FastAPI PATCH endpoint.

---

## Prerequisites — Discover GATT UUIDs from the physical device

These steps require the physical S02R sensor and the nRF Connect app. Do them **before writing any code**.

- [ ] **Step 1: Install nRF Connect**

  Download nRF Connect for Mobile from the Play Store on any Android phone.

- [ ] **Step 2: Power on the S02R sensor**

  The device broadcasts BLE advertisements continuously when powered.

- [ ] **Step 3: Scan and connect**

  Open nRF Connect → Scanner tab → tap the S02R in the list → tap Connect.

- [ ] **Step 4: Browse the GATT table**

  Once connected, nRF Connect shows a list of services. Expand each one. Look for a characteristic whose value changes when you move an object in front of the sensor (or whose name includes "distance", "range", "TOF", or "measurement").

  Tap that characteristic → tap the **read** button (↓). Record:
  - **Service UUID** (e.g. `0000aa50-0000-1000-8000-00805f9b34fb`)
  - **Characteristic UUID** (e.g. `0000aa51-0000-1000-8000-00805f9b34fb`)
  - **Value format**: nRF Connect shows the raw bytes in hex. Move something close to the sensor, read again, compare the bytes — determine if it's a uint16 little-endian (most common for mm) or uint32.
  - **Unit**: if the hex reads `0x00F0` (240) when you hold something 240 mm away, it's mm. If it reads 24, it's cm (multiply × 10 to get mm).

  Write these values down — you will paste them into `SensorGattProfile.kt` in Task 1.

---

## File Structure

```
android/
├── service/ble/src/main/kotlin/com/kibble/service/ble/
│   ├── SensorGattProfile.kt          NEW — UUID constants from nRF Connect prereq
│   ├── BleDeviceScanner.kt           NEW — scans for nearby S02R devices
│   ├── MokoSmartBleClient.kt         REPLACE — full GATT implementation
│   └── di/BleModule.kt               MODIFY — swap binding to MokoSmartBleClient
├── feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/
│   ├── OnboardingNavHost.kt          MODIFY — insert SensorPairing between Container→Calibrate
│   ├── OnboardingRoutes.kt           MODIFY — add SENSOR_PAIRING route
│   └── sensorpairing/
│       ├── SensorPairingScreen.kt    NEW
│       └── SensorPairingViewModel.kt NEW
└── app/src/main/AndroidManifest.xml  MODIFY — add ACCESS_FINE_LOCATION (API < 31 compat)

backend/
└── app/
    ├── routers/ingest.py             MODIFY — add PATCH /bins/{bin_id}
    └── schemas/sensor.py             MODIFY — add BinPatchRequest schema
```

---

## Task 1: GATT profile constants + backend PATCH /bins/{id}

**Files:**
- Create: `android/service/ble/src/main/kotlin/com/kibble/service/ble/SensorGattProfile.kt`
- Modify: `backend/app/routers/ingest.py`
- Modify: `backend/app/schemas/sensor.py`

- [ ] **Step 1: Create SensorGattProfile.kt**

  Fill in the UUID values you recorded in the Prerequisites above.

  `android/service/ble/src/main/kotlin/com/kibble/service/ble/SensorGattProfile.kt`:

  ```kotlin
  package com.kibble.service.ble

  object SensorGattProfile {
      // Values from nRF Connect scan — see Plan 3 Prerequisites.
      // Replace these with the actual UUIDs printed on your nRF Connect screen.
      const val TOF_SERVICE_UUID = "PASTE_SERVICE_UUID_HERE"
      const val DISTANCE_CHAR_UUID = "PASTE_CHARACTERISTIC_UUID_HERE"

      // Set to true if the characteristic supports notifications (preferred over polling).
      // In nRF Connect, a notification-capable characteristic shows a ↑ button next to it.
      const val SUPPORTS_NOTIFY = false

      // Distance unit reported by the sensor.
      // Set to 1.0 if the sensor reports mm, or 10.0 if it reports cm.
      const val MM_SCALE_FACTOR = 1.0
  }
  ```

- [ ] **Step 2: Add BinPatchRequest schema to backend**

  Append to `backend/app/schemas/sensor.py`:

  ```python
  class BinPatchRequest(BaseModel):
      sensor_device_id: str | None = None

      @field_validator("sensor_device_id")
      @classmethod
      def not_empty(cls, v: str | None) -> str | None:
          if v is not None and not v.strip():
              raise ValueError("sensor_device_id cannot be empty")
          return v
  ```

  Add `from pydantic import BaseModel, field_validator` if not already imported in `sensor.py`. Check the existing imports first.

- [ ] **Step 3: Write the failing test for PATCH /bins/{id}**

  `backend/tests/test_ingest.py` — append:

  ```python
  async def test_patch_bin_sensor_device_id(client, auth_headers, seeded_bin):
      resp = await client.patch(
          f"/bins/{seeded_bin['id']}",
          json={"sensor_device_id": "AA:BB:CC:DD:EE:FF"},
          headers=auth_headers,
      )
      assert resp.status_code == 200
      assert resp.json()["sensor_device_id"] == "AA:BB:CC:DD:EE:FF"

  async def test_patch_bin_rejects_empty_device_id(client, auth_headers, seeded_bin):
      resp = await client.patch(
          f"/bins/{seeded_bin['id']}",
          json={"sensor_device_id": ""},
          headers=auth_headers,
      )
      assert resp.status_code == 422
  ```

- [ ] **Step 4: Run tests to confirm they fail**

  ```bash
  cd /Users/sdagguba/kibble-reorder/backend
  source .venv/bin/activate
  pytest tests/test_ingest.py::test_patch_bin_sensor_device_id tests/test_ingest.py::test_patch_bin_rejects_empty_device_id -v
  ```

  Expected: FAIL — `404 Not Found` (route doesn't exist yet).

- [ ] **Step 5: Add PATCH /bins/{bin_id} to backend**

  Check existing imports at the top of `backend/app/routers/ingest.py`. The file already imports `BinCalibrationResponse` etc from `app.schemas.sensor`. Add `BinPatchRequest` to that import.

  Then add this route after the existing `calibrate_full` route:

  ```python
  @router.patch("/bins/{bin_id}", response_model=BinResponse)
  async def patch_bin(
      bin_id: uuid.UUID,
      payload: BinPatchRequest,
      db: AsyncSession = Depends(get_db),
      current_user: User = Depends(get_current_user),
  ):
      bin_ = await _load_owned_bin(bin_id, db, current_user)
      if payload.sensor_device_id is not None:
          bin_.sensor_device_id = payload.sensor_device_id
      await db.commit()
      await db.refresh(bin_)
      return bin_
  ```

  You'll also need `BinResponse` imported. Check what's already imported from `app.schemas.bin` — if `BinResponse` isn't there, add it.

- [ ] **Step 6: Run tests to confirm they pass**

  ```bash
  pytest tests/test_ingest.py::test_patch_bin_sensor_device_id tests/test_ingest.py::test_patch_bin_rejects_empty_device_id -v
  ```

  Expected: PASS.

- [ ] **Step 7: Add API method on Android**

  In `android/core/network/src/main/kotlin/com/kibble/core/network/dto/BinDto.kt`, append:

  ```kotlin
  @Serializable
  data class BinPatchRequest(val sensor_device_id: String)
  ```

  In `android/core/network/src/main/kotlin/com/kibble/core/network/KibbleApi.kt`, add:

  ```kotlin
  @PATCH("bins/{id}")
  suspend fun patchBin(@Path("id") binId: String, @Body body: BinPatchRequest): BinDto
  ```

- [ ] **Step 8: Commit**

  ```bash
  cd /Users/sdagguba/kibble-reorder
  git add android/ backend/
  git commit -m "feat(ble): GATT profile constants + PATCH /bins/{id} endpoint"
  ```

---

## Task 2: BLE device scanner

**Files:**
- Create: `android/service/ble/src/main/kotlin/com/kibble/service/ble/BleDeviceScanner.kt`
- Create: `android/service/ble/src/test/kotlin/com/kibble/service/ble/BleDeviceScannerTest.kt`

- [ ] **Step 1: Create BleDeviceScanner.kt**

  `android/service/ble/src/main/kotlin/com/kibble/service/ble/BleDeviceScanner.kt`:

  ```kotlin
  package com.kibble.service.ble

  import android.bluetooth.BluetoothManager
  import android.bluetooth.le.ScanCallback
  import android.bluetooth.le.ScanFilter
  import android.bluetooth.le.ScanResult
  import android.bluetooth.le.ScanSettings
  import android.content.Context
  import dagger.hilt.android.qualifiers.ApplicationContext
  import kotlinx.coroutines.channels.awaitClose
  import kotlinx.coroutines.delay
  import kotlinx.coroutines.flow.Flow
  import kotlinx.coroutines.flow.callbackFlow
  import javax.inject.Inject
  import javax.inject.Singleton

  data class ScannedDevice(val name: String?, val address: String, val rssi: Int)

  @Singleton
  class BleDeviceScanner @Inject constructor(
      @ApplicationContext private val context: Context,
  ) {
      fun scan(timeoutMs: Long = 10_000L): Flow<List<ScannedDevice>> = callbackFlow {
          val bluetoothManager = context.getSystemService(BluetoothManager::class.java)
          val scanner = bluetoothManager.adapter.bluetoothLeScanner
          val found = mutableMapOf<String, ScannedDevice>()

          val callback = object : ScanCallback() {
              override fun onScanResult(callbackType: Int, result: ScanResult) {
                  found[result.device.address] = ScannedDevice(
                      name = result.device.name,
                      address = result.device.address,
                      rssi = result.rssi,
                  )
                  trySend(found.values.sortedByDescending { it.rssi })
              }
          }

          val filters = listOf(ScanFilter.Builder().setDeviceName("S02R").build())
          val settings = ScanSettings.Builder()
              .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
              .build()

          scanner.startScan(filters, settings, callback)
          delay(timeoutMs)
          scanner.stopScan(callback)
          close()

          awaitClose { scanner.stopScan(callback) }
      }
  }
  ```

- [ ] **Step 2: Compile to verify no errors**

  ```bash
  cd /Users/sdagguba/kibble-reorder/android
  ./gradlew :service:ble:compileDebugKotlin
  ```

  Expected: BUILD SUCCESSFUL.

- [ ] **Step 3: Commit**

  ```bash
  cd /Users/sdagguba/kibble-reorder
  git add android/
  git commit -m "feat(ble): BleDeviceScanner — scans for nearby S02R devices"
  ```

---

## Task 3: MokoSmartBleClient — full GATT implementation

**Files:**
- Modify: `android/service/ble/src/main/kotlin/com/kibble/service/ble/MokoSmartBleClient.kt`

The existing file has `TODO("vendor SDK call")` stubs. This task replaces it entirely with Android's native GATT API.

- [ ] **Step 1: Replace MokoSmartBleClient.kt**

  `android/service/ble/src/main/kotlin/com/kibble/service/ble/MokoSmartBleClient.kt`:

  ```kotlin
  package com.kibble.service.ble

  import android.bluetooth.BluetoothDevice
  import android.bluetooth.BluetoothGatt
  import android.bluetooth.BluetoothGattCallback
  import android.bluetooth.BluetoothGattCharacteristic
  import android.bluetooth.BluetoothManager
  import android.bluetooth.BluetoothProfile
  import android.content.Context
  import android.os.Build
  import dagger.hilt.android.qualifiers.ApplicationContext
  import kotlinx.coroutines.CompletableDeferred
  import kotlinx.coroutines.withTimeoutOrNull
  import java.util.UUID
  import javax.inject.Inject

  class MokoSmartBleClient @Inject constructor(
      @ApplicationContext private val context: Context,
  ) : BleSensorClient {

      private var gatt: BluetoothGatt? = null
      private var connectDeferred: CompletableDeferred<Boolean>? = null
      private var readDeferred: CompletableDeferred<Double?>? = null

      private val gattCallback = object : BluetoothGattCallback() {

          override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
              when (newState) {
                  BluetoothProfile.STATE_CONNECTED -> gatt.discoverServices()
                  BluetoothProfile.STATE_DISCONNECTED -> connectDeferred?.complete(false)
              }
          }

          override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
              connectDeferred?.complete(status == BluetoothGatt.GATT_SUCCESS)
          }

          // Android 13+ (API 33) uses the new signature with value: ByteArray
          override fun onCharacteristicRead(
              gatt: BluetoothGatt,
              characteristic: BluetoothGattCharacteristic,
              value: ByteArray,
              status: Int,
          ) {
              handleRead(characteristic.uuid, value, status)
          }

          // Android 12 and below uses the deprecated single-arg version
          @Suppress("DEPRECATION")
          override fun onCharacteristicRead(
              gatt: BluetoothGatt,
              characteristic: BluetoothGattCharacteristic,
              status: Int,
          ) {
              if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
                  handleRead(characteristic.uuid, characteristic.value ?: ByteArray(0), status)
              }
          }
      }

      private fun handleRead(uuid: UUID, value: ByteArray, status: Int) {
          if (uuid != UUID.fromString(SensorGattProfile.DISTANCE_CHAR_UUID)) return
          if (status != BluetoothGatt.GATT_SUCCESS || value.size < 2) {
              readDeferred?.complete(null)
              return
          }
          // Little-endian uint16, then scaled to mm
          val raw = ((value[1].toInt() and 0xFF) shl 8) or (value[0].toInt() and 0xFF)
          readDeferred?.complete(raw.toDouble() * SensorGattProfile.MM_SCALE_FACTOR)
      }

      override suspend fun connect(deviceId: String): Boolean {
          val adapter = context.getSystemService(BluetoothManager::class.java).adapter
          val device = adapter.getRemoteDevice(deviceId)
          connectDeferred = CompletableDeferred()
          gatt = device.connectGatt(context, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
          return withTimeoutOrNull(10_000) { connectDeferred!!.await() } ?: false
      }

      override suspend fun readDistanceMm(): Double? {
          val g = gatt ?: return null
          val service = g.getService(UUID.fromString(SensorGattProfile.TOF_SERVICE_UUID)) ?: return null
          val char = service.getCharacteristic(UUID.fromString(SensorGattProfile.DISTANCE_CHAR_UUID)) ?: return null
          readDeferred = CompletableDeferred()
          @Suppress("DEPRECATION")
          g.readCharacteristic(char)
          return withTimeoutOrNull(5_000) { readDeferred!!.await() }
      }

      override suspend fun disconnect() {
          gatt?.disconnect()
          gatt?.close()
          gatt = null
      }
  }
  ```

- [ ] **Step 2: Compile to verify**

  ```bash
  cd /Users/sdagguba/kibble-reorder/android
  ./gradlew :service:ble:compileDebugKotlin
  ```

  Expected: BUILD SUCCESSFUL.

- [ ] **Step 3: Commit**

  ```bash
  cd /Users/sdagguba/kibble-reorder
  git add android/
  git commit -m "feat(ble): MokoSmartBleClient — native GATT implementation"
  ```

---

## Task 4: Runtime BLE permissions

**Files:**
- Modify: `android/app/src/main/AndroidManifest.xml`
- Create: `android/feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/sensorpairing/BlePermissionScreen.kt`

Android 12+ (API 31+) requires `BLUETOOTH_SCAN` and `BLUETOOTH_CONNECT` as runtime permissions. Older Android requires `ACCESS_FINE_LOCATION` for BLE scanning. Both are already declared in the `:service:ble` manifest; we also need them in the app manifest and we need to request them at runtime before showing the scanner.

- [ ] **Step 1: Add ACCESS_FINE_LOCATION to app manifest**

  In `android/app/src/main/AndroidManifest.xml`, add inside `<manifest>` before `<application>`:

  ```xml
  <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"
      android:maxSdkVersion="30"/>
  ```

  This declares the legacy location permission only on Android ≤ 11. On Android 12+, the service manifest's `BLUETOOTH_SCAN`/`BLUETOOTH_CONNECT` declarations are merged in automatically.

- [ ] **Step 2: Create BlePermissionScreen.kt**

  `android/feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/sensorpairing/BlePermissionScreen.kt`:

  ```kotlin
  package com.kibble.feature.onboarding.sensorpairing

  import android.Manifest
  import android.os.Build
  import androidx.activity.compose.rememberLauncherForActivityResult
  import androidx.activity.result.contract.ActivityResultContracts
  import androidx.compose.foundation.layout.Spacer
  import androidx.compose.foundation.layout.fillMaxWidth
  import androidx.compose.foundation.layout.height
  import androidx.compose.material3.MaterialTheme
  import androidx.compose.material3.Text
  import androidx.compose.runtime.Composable
  import androidx.compose.ui.Modifier
  import androidx.compose.ui.unit.dp
  import com.kibble.feature.onboarding.components.OnboardingScaffold
  import com.kibble.feature.onboarding.components.PrimaryButton

  @Composable
  fun BlePermissionScreen(onGranted: () -> Unit) {
      val permissions = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
          arrayOf(
              Manifest.permission.BLUETOOTH_SCAN,
              Manifest.permission.BLUETOOTH_CONNECT,
          )
      } else {
          arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
      }

      val launcher = rememberLauncherForActivityResult(
          ActivityResultContracts.RequestMultiplePermissions()
      ) { results ->
          if (results.values.all { it }) onGranted()
      }

      OnboardingScaffold(
          stepLabel = "Step 5 of 10",
          primaryAction = {
              PrimaryButton(
                  text = "Allow Bluetooth access",
                  onClick = { launcher.launch(permissions) },
                  enabled = true,
              )
          },
      ) {
          Text("Find your sensor", style = MaterialTheme.typography.headlineMedium)
          Spacer(Modifier.height(8.dp))
          Text(
              "Kibble uses Bluetooth to read your bin's distance sensor. Allow access to continue.",
              style = MaterialTheme.typography.bodyMedium,
              modifier = Modifier.fillMaxWidth(),
          )
      }
  }
  ```

- [ ] **Step 3: Compile**

  ```bash
  cd /Users/sdagguba/kibble-reorder/android
  ./gradlew :feature:onboarding:compileDebugKotlin
  ```

  Expected: BUILD SUCCESSFUL.

- [ ] **Step 4: Commit**

  ```bash
  cd /Users/sdagguba/kibble-reorder
  git add android/
  git commit -m "feat(ble): runtime BLE permission screen"
  ```

---

## Task 5: Sensor pairing screen in onboarding

**Files:**
- Create: `android/feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/sensorpairing/SensorPairingScreen.kt`
- Create: `android/feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/sensorpairing/SensorPairingViewModel.kt`
- Modify: `android/feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/OnboardingNavHost.kt`
- Modify: `android/feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/OnboardingRoutes.kt`
- Modify: `android/feature/onboarding/build.gradle.kts` (add `:service:ble` dep)

- [ ] **Step 1: Add `:service:ble` dependency to onboarding module**

  In `android/feature/onboarding/build.gradle.kts`, inside `dependencies { }`:

  ```kotlin
  implementation(project(":service:ble"))
  ```

- [ ] **Step 2: Add SENSOR_PAIRING route**

  Open `android/feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/OnboardingRoutes.kt`. It currently has a set of `const val` route strings. Add:

  ```kotlin
  const val BLE_PERMISSION = "ble_permission"
  const val SENSOR_PAIRING = "sensor_pairing"
  ```

- [ ] **Step 3: Create SensorPairingViewModel.kt**

  `android/feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/sensorpairing/SensorPairingViewModel.kt`:

  ```kotlin
  package com.kibble.feature.onboarding.sensorpairing

  import androidx.lifecycle.ViewModel
  import androidx.lifecycle.viewModelScope
  import com.kibble.core.common.KibbleResult
  import com.kibble.core.database.dao.BinDao
  import com.kibble.core.database.dao.UserDao
  import com.kibble.core.network.KibbleApi
  import com.kibble.core.network.dto.BinPatchRequest
  import com.kibble.service.ble.BleDeviceScanner
  import com.kibble.service.ble.ScannedDevice
  import dagger.hilt.android.lifecycle.HiltViewModel
  import kotlinx.coroutines.flow.MutableStateFlow
  import kotlinx.coroutines.flow.asStateFlow
  import kotlinx.coroutines.flow.firstOrNull
  import kotlinx.coroutines.launch
  import java.util.UUID
  import javax.inject.Inject

  data class SensorPairingState(
      val scanning: Boolean = false,
      val devices: List<ScannedDevice> = emptyList(),
      val pairing: Boolean = false,
      val paired: Boolean = false,
      val error: String? = null,
  )

  @HiltViewModel
  class SensorPairingViewModel @Inject constructor(
      private val scanner: BleDeviceScanner,
      private val userDao: UserDao,
      private val binDao: BinDao,
      private val api: KibbleApi,
  ) : ViewModel() {

      private val _state = MutableStateFlow(SensorPairingState())
      val state = _state.asStateFlow()

      fun startScan() {
          viewModelScope.launch {
              _state.value = _state.value.copy(scanning = true, devices = emptyList(), error = null)
              scanner.scan().collect { devices ->
                  _state.value = _state.value.copy(devices = devices)
              }
              _state.value = _state.value.copy(scanning = false)
          }
      }

      fun selectDevice(device: ScannedDevice) {
          viewModelScope.launch {
              _state.value = _state.value.copy(pairing = true, error = null)
              val user = userDao.first()
              if (user == null) {
                  _state.value = _state.value.copy(pairing = false, error = "Not signed in")
                  return@launch
              }
              val bin = binDao.observeForUser(user.id).firstOrNull()?.firstOrNull()
              if (bin == null) {
                  _state.value = _state.value.copy(pairing = false, error = "No bin found — go back")
                  return@launch
              }
              runCatching {
                  val updated = api.patchBin(bin.id.toString(), BinPatchRequest(sensor_device_id = device.address))
                  binDao.upsert(bin.copy(sensorDeviceId = updated.sensor_device_id))
                  _state.value = _state.value.copy(pairing = false, paired = true)
              }.onFailure { e ->
                  _state.value = _state.value.copy(pairing = false, error = e.message)
              }
          }
      }
  }
  ```

- [ ] **Step 4: Create SensorPairingScreen.kt**

  `android/feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/sensorpairing/SensorPairingScreen.kt`:

  ```kotlin
  package com.kibble.feature.onboarding.sensorpairing

  import androidx.compose.foundation.clickable
  import androidx.compose.foundation.layout.Column
  import androidx.compose.foundation.layout.Row
  import androidx.compose.foundation.layout.Spacer
  import androidx.compose.foundation.layout.fillMaxWidth
  import androidx.compose.foundation.layout.height
  import androidx.compose.foundation.layout.padding
  import androidx.compose.foundation.layout.size
  import androidx.compose.foundation.lazy.LazyColumn
  import androidx.compose.foundation.lazy.items
  import androidx.compose.material3.CircularProgressIndicator
  import androidx.compose.material3.HorizontalDivider
  import androidx.compose.material3.MaterialTheme
  import androidx.compose.material3.Surface
  import androidx.compose.material3.Text
  import androidx.compose.runtime.Composable
  import androidx.compose.runtime.LaunchedEffect
  import androidx.compose.runtime.getValue
  import androidx.compose.ui.Alignment
  import androidx.compose.ui.Modifier
  import androidx.compose.ui.unit.dp
  import androidx.hilt.navigation.compose.hiltViewModel
  import androidx.lifecycle.compose.collectAsStateWithLifecycle
  import com.kibble.feature.onboarding.components.OnboardingScaffold
  import com.kibble.feature.onboarding.components.PrimaryButton

  @Composable
  fun SensorPairingScreen(
      onNext: () -> Unit,
      viewModel: SensorPairingViewModel = hiltViewModel(),
  ) {
      val state by viewModel.state.collectAsStateWithLifecycle()
      LaunchedEffect(state.paired) { if (state.paired) onNext() }
      LaunchedEffect(Unit) { viewModel.startScan() }

      OnboardingScaffold(
          stepLabel = "Step 5 of 10",
          primaryAction = {
              PrimaryButton(
                  text = if (state.scanning) "Scanning…" else "Scan again",
                  onClick = { viewModel.startScan() },
                  enabled = !state.scanning && !state.pairing,
              )
          },
      ) {
          Text("Select your sensor", style = MaterialTheme.typography.headlineMedium)
          Spacer(Modifier.height(8.dp))
          Text(
              "Make sure the S02R sensor is powered on and within range.",
              style = MaterialTheme.typography.bodyMedium,
          )
          Spacer(Modifier.height(24.dp))

          if (state.scanning && state.devices.isEmpty()) {
              CircularProgressIndicator(modifier = Modifier.align(Alignment.CenterHorizontally))
          }

          if (state.devices.isNotEmpty()) {
              Surface(
                  color = MaterialTheme.colorScheme.surfaceVariant,
                  shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp),
                  modifier = Modifier.fillMaxWidth(),
              ) {
                  LazyColumn {
                      items(state.devices) { device ->
                          Row(
                              modifier = Modifier
                                  .fillMaxWidth()
                                  .clickable(enabled = !state.pairing) { viewModel.selectDevice(device) }
                                  .padding(horizontal = 16.dp, vertical = 12.dp),
                              verticalAlignment = Alignment.CenterVertically,
                          ) {
                              Column(modifier = Modifier.weight(1f)) {
                                  Text(device.name ?: "Unknown device", style = MaterialTheme.typography.bodyLarge)
                                  Text(device.address, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.outline)
                              }
                              Text("${device.rssi} dBm", style = MaterialTheme.typography.bodySmall)
                              if (state.pairing) {
                                  Spacer(Modifier.size(8.dp))
                                  CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp)
                              }
                          }
                          HorizontalDivider()
                      }
                  }
              }
          }

          if (state.error != null) {
              Spacer(Modifier.height(8.dp))
              Text(state.error!!, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
          }
      }
  }
  ```

- [ ] **Step 5: Insert into OnboardingNavHost**

  Open `android/feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/OnboardingNavHost.kt`.

  Add these imports at the top:

  ```kotlin
  import com.kibble.feature.onboarding.sensorpairing.BlePermissionScreen
  import com.kibble.feature.onboarding.sensorpairing.SensorPairingScreen
  ```

  Replace the `CONTAINER → CALIBRATE` navigation with this sequence (add two new composable destinations between them):

  ```kotlin
  composable(OnboardingRoutes.CONTAINER) {
      ContainerScreen(onNext = { nav.navigate(OnboardingRoutes.BLE_PERMISSION) })
  }
  composable(OnboardingRoutes.BLE_PERMISSION) {
      BlePermissionScreen(onGranted = { nav.navigate(OnboardingRoutes.SENSOR_PAIRING) })
  }
  composable(OnboardingRoutes.SENSOR_PAIRING) {
      SensorPairingScreen(onNext = { nav.navigate(OnboardingRoutes.CALIBRATE) })
  }
  composable(OnboardingRoutes.CALIBRATE) {
      CalibrateScreen(onNext = { nav.navigate(OnboardingRoutes.PACKSIZE) })
  }
  ```

- [ ] **Step 6: Build**

  ```bash
  cd /Users/sdagguba/kibble-reorder/android
  ./gradlew :feature:onboarding:compileDebugKotlin :app:assembleDebug
  ```

  Expected: BUILD SUCCESSFUL.

- [ ] **Step 7: Commit**

  ```bash
  cd /Users/sdagguba/kibble-reorder
  git add android/
  git commit -m "feat(ble): sensor pairing screen in onboarding (step 5)"
  ```

---

## Task 6: Swap BleModule binding to MokoSmartBleClient

**Files:**
- Modify: `android/service/ble/src/main/kotlin/com/kibble/service/ble/di/BleModule.kt`

- [ ] **Step 1: Replace FakeBleClient binding**

  `android/service/ble/src/main/kotlin/com/kibble/service/ble/di/BleModule.kt`:

  ```kotlin
  package com.kibble.service.ble.di

  import com.kibble.service.ble.BleSensorClient
  import com.kibble.service.ble.MokoSmartBleClient
  import dagger.Binds
  import dagger.Module
  import dagger.hilt.InstallIn
  import dagger.hilt.components.SingletonComponent
  import javax.inject.Singleton

  @Module
  @InstallIn(SingletonComponent::class)
  abstract class BleModule {
      @Binds @Singleton
      abstract fun bindClient(impl: MokoSmartBleClient): BleSensorClient
  }
  ```

- [ ] **Step 2: Build + install**

  ```bash
  cd /Users/sdagguba/kibble-reorder/android
  ./gradlew :app:assembleDebug
  ~/Library/Android/sdk/platform-tools/adb install -r app/build/outputs/apk/debug/app-debug.apk
  ```

  Expected: BUILD SUCCESSFUL, install Success.

- [ ] **Step 3: Commit**

  ```bash
  cd /Users/sdagguba/kibble-reorder
  git add android/
  git commit -m "feat(ble): activate MokoSmartBleClient — swap out FakeBleClient"
  ```

---

## Task 7: End-to-end smoke test (manual — requires physical sensor)

- [ ] **Step 1: Clear app data on emulator / device**

  Either uninstall and reinstall, or go to Settings → Apps → Kibble → Clear Storage.

- [ ] **Step 2: Run the backend**

  ```bash
  cd /Users/sdagguba/kibble-reorder/backend
  source .venv/bin/activate
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
  ```

- [ ] **Step 3: Complete onboarding on a real Android device (not emulator)**

  The emulator has no BLE hardware. Install the APK on a physical Android phone via:

  ```bash
  ~/Library/Android/sdk/platform-tools/adb -d install -r \
    /Users/sdagguba/kibble-reorder/android/app/build/outputs/apk/debug/app-debug.apk
  ```

  (`-d` targets a USB-connected physical device instead of the emulator.)

- [ ] **Step 4: Go through onboarding to the BLE permission screen**

  Tap "Allow Bluetooth access" — Android permission dialog should appear. Grant it.

- [ ] **Step 5: Power on the S02R sensor and select it**

  The S02R device should appear in the list within a few seconds. Tap it. The app patches the bin's sensor_device_id on the backend and navigates to Calibrate.

  Verify in the backend logs:
  ```
  PATCH /bins/{id} 200
  ```

- [ ] **Step 6: Complete calibrate step**

  Place the sensor above the empty bin. Tap "SET EMPTY LEVEL". Verify backend logs show:
  ```
  POST /bins/{id}/calibrate/empty 200
  ```

- [ ] **Step 7: Tap READ NOW on the Home screen**

  The app starts `BleForegroundService` with `ACTION_READ_NOW`. The service calls `ReadingRepository.readAndStore()` which:
  1. Calls `MokoSmartBleClient.connect(mac)` → GATT connect
  2. Calls `readDistanceMm()` → reads the TOF characteristic
  3. Disconnects
  4. Writes a `SensorReadingEntity` to Room
  5. POSTs to `POST /bins/{id}/readings`

  Verify in backend logs:
  ```
  POST /bins/{id}/readings 201
  ```

  Verify the Home screen updates — the kibble level % and container illustration should reflect the new reading within a few seconds (the ViewModel's `sensorDao.observeLatest(bin.id)` flow will emit).

- [ ] **Step 8: Final commit + tag**

  ```bash
  cd /Users/sdagguba/kibble-reorder
  git tag v0.2.0-ble
  git commit --allow-empty -m "chore: BLE sensor integration smoke tested end-to-end"
  ```

---

## Definition of Done

- [ ] `SensorGattProfile.kt` contains the real UUIDs discovered from the physical S02R via nRF Connect
- [ ] `MokoSmartBleClient` connects, reads, and disconnects without crashing on a real Android device
- [ ] Onboarding shows the BLE permission screen and sensor pairing screen; tapping the S02R updates `bin.sensor_device_id` on the backend
- [ ] "READ NOW" on the Home screen triggers a real GATT read and the new reading appears in the UI and in the backend DB
- [ ] `FakeBleClient` is no longer the active binding

---

## Notes for the Implementer

- **nRF Connect is non-negotiable.** You cannot fill in `SensorGattProfile.kt` without scanning the physical device first. The entire plan depends on Task 1 prerequisite. Don't skip it.

- **Emulator has no BLE.** All physical testing (Tasks 4–7) must run on a real Android phone connected via USB. The emulator build is fine for verifying compilation, but BLE won't work there.

- **`PENDING-BLE` in the DB.** If you've already completed onboarding before this plan, your bin has `sensor_device_id = "PENDING-BLE"` on the backend. You'll need to either: (a) clear app data and re-run onboarding through the new pairing screen, or (b) manually call `PATCH /bins/{id}` with the real MAC via curl after the plan is done.

- **ByteArray parsing.** The plan assumes little-endian uint16 (two bytes, LSB first). If nRF Connect shows your distance value in a different format (e.g. a single byte, or big-endian, or uint32), adjust `handleRead()` in `MokoSmartBleClient.kt` accordingly. The nRF Connect raw bytes view shows exactly the bytes you'll receive.

- **GATT connection on Android 12+.** Some Android 12 devices require that you call `gatt.requestMtu(512)` inside `onConnectionStateChange` before `discoverServices()` — otherwise discovery can time out. If you see connection timeouts, add `gatt.requestMtu(512)` before `gatt.discoverServices()`.

- **`BLUETOOTH_SCAN` `neverForLocation` flag.** The service manifest already declares `android:usesPermissionFlags="neverForLocation"` which tells the OS this scan is not for location purposes — this avoids the location permission dialog on Android 12+.
