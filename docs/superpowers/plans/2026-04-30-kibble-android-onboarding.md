# Plan 2b-ii — Android Onboarding Flow

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the 9-step Onboarding flow on top of the foundation from Plan 2b-i. Ships an app where a new user can complete onboarding end-to-end (Firebase login → profile → dog → bin → calibrate → pack size → threshold → payment mode → preferred retailer login → delivery estimate) and arrives at the main app shell.

**Architecture:** New `:feature:onboarding` module. Single ViewModel per screen following the MVVM-with-sealed-intents pattern from the spec. An `OnboardingRepository` writes each step to the Plan 2a backend immediately so the user can resume mid-flow. Linear nav graph with a step indicator in the app bar. Per-retailer login flow: WebView for cookie capture; native form for credentials.

**Tech additions over 2b-i:** `androidx.compose.foundation.layout` only (no extra libs); `play-services-auth` for Google Sign-In; `accompanist-webview` for the WebView wrapper.

**Spec:** `/Users/sdagguba/sasank-playground/docs/superpowers/specs/2026-04-30-kibble-android-app-design.md` (Sections 9, 10)

**Repo:** `/Users/sdagguba/kibble-reorder/android/`

---

## Prerequisites

- Plan 2b-i executed; `./gradlew :app:assembleDebug` succeeds
- Firebase Auth has Email/Password and Phone providers enabled
- Firebase Auth has Google provider enabled and an OAuth Web Client ID is set
- The user added `play-services-auth` and `accompanist-webview` versions to `libs.versions.toml`

---

## File Structure (additions)

```
android/feature/onboarding/
├── build.gradle.kts
└── src/main/kotlin/com/kibble/feature/onboarding/
    ├── OnboardingRepository.kt
    ├── OnboardingNavHost.kt
    ├── OnboardingDestination.kt
    ├── components/
    │   ├── OnboardingScaffold.kt        (top app bar with step indicator + skip slot)
    │   ├── PrimaryButton.kt
    │   └── SectionHeader.kt
    ├── welcome/
    │   ├── WelcomeViewModel.kt
    │   ├── WelcomeIntent.kt
    │   ├── WelcomeState.kt
    │   └── WelcomeScreen.kt
    ├── profile/  (steps repeat the same shape)
    │   ├── ProfileViewModel.kt
    │   ├── ProfileIntent.kt
    │   ├── ProfileState.kt
    │   └── ProfileScreen.kt
    ├── dog/, container/, calibrate/, packsize/, threshold/, payment/
    ├── retailer/
    │   ├── RetailerCatalog.kt           (static list of supported retailers + login type per retailer)
    │   ├── RetailerPickerScreen.kt
    │   ├── CookieLoginScreen.kt          (WebView)
    │   ├── CredentialLoginScreen.kt
    │   └── RetailerLoginViewModel.kt
    └── delivery/
        ├── DeliveryEstimateViewModel.kt
        ├── DeliveryEstimateState.kt
        └── DeliveryEstimateScreen.kt
```

settings.gradle.kts adds: `include(":feature:onboarding")`

---

## Task 1: Module setup + OnboardingRepository

**Files:**
- Modify: `android/settings.gradle.kts` (add `:feature:onboarding`)
- Create: `feature/onboarding/build.gradle.kts`
- Create: `feature/onboarding/src/main/AndroidManifest.xml`
- Create: `feature/onboarding/src/main/kotlin/com/kibble/feature/onboarding/OnboardingRepository.kt`
- Create: `feature/onboarding/src/test/kotlin/com/kibble/feature/onboarding/OnboardingRepositoryTest.kt`

- [ ] **Step 1: Add module to settings**

Edit `android/settings.gradle.kts` — append:

```kotlin
include(":feature:onboarding")
```

- [ ] **Step 2: Module build script**

Create `android/feature/onboarding/build.gradle.kts`:

```kotlin
plugins {
    id("kibble.android.library")
    id("kibble.android.compose")
    id("kibble.android.hilt")
}

android {
    namespace = "com.kibble.feature.onboarding"
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
    implementation(libs.nav.compose)
    implementation(libs.hilt.navigation.compose)
    implementation(libs.compose.material.icons.extended)
    implementation(platform(libs.firebase.bom))
    implementation(libs.firebase.auth)
    implementation("com.google.android.gms:play-services-auth:21.2.0")
    implementation("androidx.webkit:webkit:1.12.1")

    testImplementation(libs.junit.jupiter)
    testImplementation(libs.coroutines.test)
    testImplementation(libs.turbine)
    testImplementation(libs.mockk)
    testRuntimeOnly("org.junit.jupiter:junit-jupiter-engine:5.11.3")
}

tasks.withType<Test> { useJUnitPlatform() }
```

- [ ] **Step 3: Manifest**

`feature/onboarding/src/main/AndroidManifest.xml`: `<manifest />`

- [ ] **Step 4: OnboardingRepository**

Create `OnboardingRepository.kt`:

```kotlin
package com.kibble.feature.onboarding

import com.kibble.core.common.KibbleResult
import com.kibble.core.common.kibbleRunCatching
import com.kibble.core.database.dao.BinDao
import com.kibble.core.database.dao.DogDao
import com.kibble.core.database.dao.UserDao
import com.kibble.core.database.entity.BinEntity
import com.kibble.core.database.entity.DogEntity
import com.kibble.core.network.KibbleApi
import com.kibble.core.network.dto.*
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class OnboardingRepository @Inject constructor(
    private val api: KibbleApi,
    private val userDao: UserDao,
    private val dogDao: DogDao,
    private val binDao: BinDao,
) {
    suspend fun saveProfile(userId: UUID, name: String, pincode: String): KibbleResult<Unit> = kibbleRunCatching {
        api.patchUser(userId.toString(), UserPatchRequest(name = name, pincode = pincode))
        val current = userDao.observe(userId).let { /* one-shot read via direct query */ }
        userDao.upsert(
            userDao.first()!!.copy(name = name, pincode = pincode)
        )
    }

    suspend fun createDog(userId: UUID, name: String, breed: String?, brand: String, product: String): KibbleResult<UUID> = kibbleRunCatching {
        val dog = api.createDog(userId.toString(), DogCreateRequest(name, breed, brand, product))
        val dogId = UUID.fromString(dog.id)
        dogDao.upsert(DogEntity(id = dogId, userId = userId, name = name, breed = breed, kibbleBrand = brand, kibbleProductName = product))
        dogId
    }

    suspend fun createBin(userId: UUID, dogId: UUID, sensorDeviceId: String, capacityKg: Double): KibbleResult<UUID> = kibbleRunCatching {
        val bin = api.createBin(userId.toString(), BinCreateRequest(dogId.toString(), sensorDeviceId, capacityKg))
        val binId = UUID.fromString(bin.id)
        binDao.upsert(BinEntity(
            id = binId, userId = userId, dogId = dogId, sensorDeviceId = sensorDeviceId,
            containerCapacityKg = capacityKg, calibrationState = bin.calibration_state,
            emptyCalibrationMm = bin.empty_calibration_mm, fullCalibrationMm = bin.full_calibration_mm,
        ))
        binId
    }

    suspend fun calibrateEmpty(binId: UUID, distanceMm: Double): KibbleResult<Unit> = kibbleRunCatching {
        val bin = api.calibrateEmpty(binId.toString(), CalibrateEmptyRequest(distanceMm))
        // refresh local copy
        binDao.upsert(BinEntity(
            id = UUID.fromString(bin.id), userId = UUID.fromString(/* fetched separately */ ""),
            dogId = UUID.fromString(bin.dog_id), sensorDeviceId = bin.sensor_device_id,
            containerCapacityKg = bin.container_capacity_kg, calibrationState = bin.calibration_state,
            emptyCalibrationMm = bin.empty_calibration_mm, fullCalibrationMm = bin.full_calibration_mm,
        ))
    }

    suspend fun savePreferences(userId: UUID, packSize: String?, threshold: Int?, paymentMode: String?): KibbleResult<Unit> = kibbleRunCatching {
        api.patchUser(userId.toString(), UserPatchRequest(
            pack_size_preference = packSize,
            reorder_threshold_pct = threshold,
            payment_mode = paymentMode,
        ))
    }

    suspend fun saveRetailerSession(userId: UUID, retailer: String, type: String, blob: String, expiresAt: String? = null): KibbleResult<Unit> = kibbleRunCatching {
        val req = if (type == "cookie")
            RetailerSessionRequest(retailer = retailer, type = "cookie", session_blob = blob, expires_at = expiresAt)
        else
            RetailerSessionRequest(retailer = retailer, type = "credentials", credentials_blob = blob)
        api.createRetailerSession(userId.toString(), req)
    }

    suspend fun completeOnboarding(userId: UUID): KibbleResult<Unit> = kibbleRunCatching {
        userDao.upsert(userDao.first()!!.copy(onboardingComplete = true))
    }
}
```

- [ ] **Step 5: Test**

Create `OnboardingRepositoryTest.kt` with happy-path and failure tests for `saveProfile` (using mockk for `KibbleApi` and `UserDao`).

```kotlin
package com.kibble.feature.onboarding

import com.kibble.core.common.KibbleResult
import com.kibble.core.database.dao.BinDao
import com.kibble.core.database.dao.DogDao
import com.kibble.core.database.dao.UserDao
import com.kibble.core.database.entity.UserEntity
import com.kibble.core.network.KibbleApi
import com.kibble.core.network.dto.UserDto
import com.kibble.core.network.dto.UserPatchRequest
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.util.UUID

class OnboardingRepositoryTest {
    private val api = mockk<KibbleApi>(relaxed = true)
    private val userDao = mockk<UserDao>(relaxed = true)
    private val dogDao = mockk<DogDao>(relaxed = true)
    private val binDao = mockk<BinDao>(relaxed = true)
    private val repo = OnboardingRepository(api, userDao, dogDao, binDao)

    @Test
    fun `saveProfile patches API and updates local cache`() = runTest {
        val uid = UUID.randomUUID()
        coEvery { api.patchUser(any(), any()) } returns UserDto(uid.toString(), "x@y.com", "Sasank", "560001", 20, "90pct", 4.0f, "best_value")
        coEvery { userDao.first() } returns UserEntity(uid, "fb-1", "x@y.com", null, null)
        val result = repo.saveProfile(uid, "Sasank", "560001")
        assertTrue(result is KibbleResult.Success)
        coVerify { api.patchUser(uid.toString(), UserPatchRequest(name = "Sasank", pincode = "560001")) }
    }
}
```

- [ ] **Step 6: Run tests**

```bash
cd /Users/sdagguba/kibble-reorder/android && ./gradlew :feature:onboarding:test
```
Expected: 1 passed.

- [ ] **Step 7: Commit**

```bash
cd /Users/sdagguba/kibble-reorder && git add android/ && git commit -m "feat(android/onboarding): module setup + OnboardingRepository"
```

---

## Task 2: Onboarding scaffold + nav host + step indicator

- [ ] **Step 1: Onboarding destinations**

Create `OnboardingDestination.kt`:

```kotlin
package com.kibble.feature.onboarding

object OnboardingRoutes {
    const val WELCOME = "ob/welcome"
    const val PROFILE = "ob/profile"
    const val DOG = "ob/dog"
    const val CONTAINER = "ob/container"
    const val CALIBRATE = "ob/calibrate"
    const val PACKSIZE = "ob/packsize"
    const val THRESHOLD = "ob/threshold"
    const val PAYMENT = "ob/payment"
    const val RETAILER = "ob/retailer"
    const val DELIVERY = "ob/delivery"
}

val OnboardingStepCount = 9

fun stepNumberForRoute(route: String?): Int = when (route) {
    OnboardingRoutes.WELCOME -> 1
    OnboardingRoutes.PROFILE -> 2
    OnboardingRoutes.DOG -> 3
    OnboardingRoutes.CONTAINER -> 4
    OnboardingRoutes.CALIBRATE -> 5
    OnboardingRoutes.PACKSIZE -> 6
    OnboardingRoutes.THRESHOLD -> 7
    OnboardingRoutes.PAYMENT -> 8
    OnboardingRoutes.RETAILER -> 8
    OnboardingRoutes.DELIVERY -> 9
    else -> 0
}
```

- [ ] **Step 2: OnboardingScaffold**

Create `components/OnboardingScaffold.kt`:

```kotlin
package com.kibble.feature.onboarding.components

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun OnboardingScaffold(
    stepLabel: String?,
    onBack: (() -> Unit)? = null,
    onSkip: (() -> Unit)? = null,
    primaryAction: (@Composable () -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    if (stepLabel != null) Text(stepLabel, style = MaterialTheme.typography.labelMedium)
                },
                navigationIcon = {
                    if (onBack != null) {
                        IconButton(onClick = onBack) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                        }
                    }
                },
                actions = {
                    if (onSkip != null) TextButton(onClick = onSkip) { Text("Skip") }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                ),
            )
        },
        bottomBar = {
            if (primaryAction != null) {
                Surface(color = MaterialTheme.colorScheme.background) {
                    Box(modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 16.dp)) {
                        primaryAction()
                    }
                }
            }
        },
        containerColor = MaterialTheme.colorScheme.background,
    ) { padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 24.dp).padding(top = 8.dp),
            content = content,
        )
    }
}
```

- [ ] **Step 3: PrimaryButton**

Create `components/PrimaryButton.kt`:

```kotlin
package com.kibble.feature.onboarding.components

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, enabled: Boolean = true, modifier: Modifier = Modifier) {
    Button(
        onClick = onClick,
        enabled = enabled,
        shape = CircleShape,
        contentPadding = ButtonDefaults.ContentPadding,
        modifier = modifier.fillMaxWidth().padding(vertical = 4.dp),
    ) {
        Text(text.uppercase(), style = MaterialTheme.typography.labelLarge)
    }
}
```

- [ ] **Step 4: OnboardingNavHost**

Create `OnboardingNavHost.kt`:

```kotlin
package com.kibble.feature.onboarding

import androidx.compose.runtime.Composable
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
// Per-step screens imported from feature modules:
import com.kibble.feature.onboarding.welcome.WelcomeScreen
import com.kibble.feature.onboarding.profile.ProfileScreen
import com.kibble.feature.onboarding.dog.DogScreen
import com.kibble.feature.onboarding.container.ContainerScreen
import com.kibble.feature.onboarding.calibrate.CalibrateScreen
import com.kibble.feature.onboarding.packsize.PackSizeScreen
import com.kibble.feature.onboarding.threshold.ThresholdScreen
import com.kibble.feature.onboarding.payment.PaymentScreen
import com.kibble.feature.onboarding.retailer.RetailerPickerScreen
import com.kibble.feature.onboarding.delivery.DeliveryEstimateScreen

@Composable
fun OnboardingNavHost(onComplete: () -> Unit) {
    val nav = rememberNavController()
    NavHost(navController = nav, startDestination = OnboardingRoutes.WELCOME) {
        composable(OnboardingRoutes.WELCOME) { WelcomeScreen(onSignedIn = { nav.navigate(OnboardingRoutes.PROFILE) }) }
        composable(OnboardingRoutes.PROFILE) { ProfileScreen(onNext = { nav.navigate(OnboardingRoutes.DOG) }) }
        composable(OnboardingRoutes.DOG) { DogScreen(onNext = { nav.navigate(OnboardingRoutes.CONTAINER) }) }
        composable(OnboardingRoutes.CONTAINER) { ContainerScreen(onNext = { nav.navigate(OnboardingRoutes.CALIBRATE) }) }
        composable(OnboardingRoutes.CALIBRATE) { CalibrateScreen(onNext = { nav.navigate(OnboardingRoutes.PACKSIZE) }) }
        composable(OnboardingRoutes.PACKSIZE) { PackSizeScreen(onNext = { nav.navigate(OnboardingRoutes.THRESHOLD) }) }
        composable(OnboardingRoutes.THRESHOLD) { ThresholdScreen(onNext = { nav.navigate(OnboardingRoutes.PAYMENT) }) }
        composable(OnboardingRoutes.PAYMENT) { PaymentScreen(onNext = { nav.navigate(OnboardingRoutes.RETAILER) }) }
        composable(OnboardingRoutes.RETAILER) { RetailerPickerScreen(onNext = { nav.navigate(OnboardingRoutes.DELIVERY) }) }
        composable(OnboardingRoutes.DELIVERY) { DeliveryEstimateScreen(onComplete = onComplete) }
    }
}
```

- [ ] **Step 5: Wire into app NavHost**

Modify `app/src/main/kotlin/com/kibble/navigation/KibbleNavHost.kt` — replace the `ONBOARDING` placeholder:

```kotlin
import com.kibble.feature.onboarding.OnboardingNavHost
// ...
composable(Routes.ONBOARDING) {
    OnboardingNavHost(onComplete = {
        rootNavController.navigate(Routes.MAIN) {
            popUpTo(Routes.ONBOARDING) { inclusive = true }
        }
    })
}
```

Also add `implementation(project(":feature:onboarding"))` to `app/build.gradle.kts` dependencies.

- [ ] **Step 6: Build (will fail until per-screen Composables exist; fine — placeholders coming next)**

Skip build verification at this step. Commit:

```bash
cd /Users/sdagguba/kibble-reorder && git add android/ && git commit -m "feat(android/onboarding): nav host scaffold + step indicator + primary button"
```

---

## Task 3: Welcome screen with Firebase phone OTP + Google Sign-In

**Files:**
- Create: `welcome/WelcomeState.kt`, `WelcomeIntent.kt`, `WelcomeViewModel.kt`, `WelcomeScreen.kt`

- [ ] **Step 1: State + Intent**

```kotlin
package com.kibble.feature.onboarding.welcome

sealed class WelcomeIntent {
    data class StartPhoneFlow(val phoneE164: String) : WelcomeIntent()
    data class VerifyOtp(val code: String) : WelcomeIntent()
    data class SignInWithGoogleIdToken(val idToken: String) : WelcomeIntent()
}

data class WelcomeState(
    val isLoading: Boolean = false,
    val phoneSent: Boolean = false,
    val verificationId: String? = null,
    val signedIn: Boolean = false,
    val error: String? = null,
)
```

- [ ] **Step 2: ViewModel**

```kotlin
package com.kibble.feature.onboarding.welcome

import android.app.Activity
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.GoogleAuthProvider
import com.google.firebase.auth.PhoneAuthCredential
import com.google.firebase.auth.PhoneAuthOptions
import com.google.firebase.auth.PhoneAuthProvider
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import java.util.concurrent.TimeUnit
import javax.inject.Inject

@HiltViewModel
class WelcomeViewModel @Inject constructor(
    private val firebaseAuth: FirebaseAuth,
) : ViewModel() {
    private val _state = MutableStateFlow(WelcomeState())
    val state = _state.asStateFlow()

    fun startPhoneFlow(activity: Activity, phoneE164: String) {
        _state.value = _state.value.copy(isLoading = true, error = null)
        val opts = PhoneAuthOptions.newBuilder(firebaseAuth)
            .setPhoneNumber(phoneE164)
            .setTimeout(60L, TimeUnit.SECONDS)
            .setActivity(activity)
            .setCallbacks(object : PhoneAuthProvider.OnVerificationStateChangedCallbacks() {
                override fun onCodeSent(verificationId: String, token: PhoneAuthProvider.ForceResendingToken) {
                    _state.value = _state.value.copy(isLoading = false, phoneSent = true, verificationId = verificationId)
                }
                override fun onVerificationCompleted(credential: PhoneAuthCredential) {
                    signInWithCredential(credential)
                }
                override fun onVerificationFailed(e: com.google.firebase.FirebaseException) {
                    _state.value = _state.value.copy(isLoading = false, error = e.message)
                }
            }).build()
        PhoneAuthProvider.verifyPhoneNumber(opts)
    }

    fun verifyOtp(code: String) {
        val verificationId = _state.value.verificationId ?: return
        val credential = PhoneAuthProvider.getCredential(verificationId, code)
        signInWithCredential(credential)
    }

    fun signInWithGoogleIdToken(idToken: String) {
        val credential = GoogleAuthProvider.getCredential(idToken, null)
        signInWithCredential(credential)
    }

    private fun signInWithCredential(credential: com.google.firebase.auth.AuthCredential) {
        viewModelScope.launch {
            _state.value = _state.value.copy(isLoading = true)
            runCatching { firebaseAuth.signInWithCredential(credential).await() }
                .onSuccess { _state.value = _state.value.copy(isLoading = false, signedIn = true) }
                .onFailure { _state.value = _state.value.copy(isLoading = false, error = it.message) }
        }
    }
}
```

- [ ] **Step 3: Welcome screen**

```kotlin
package com.kibble.feature.onboarding.welcome

import android.app.Activity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.kibble.feature.onboarding.components.PrimaryButton

@Composable
fun WelcomeScreen(
    onSignedIn: () -> Unit,
    viewModel: WelcomeViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current

    LaunchedEffect(state.signedIn) {
        if (state.signedIn) onSignedIn()
    }

    var phone by remember { mutableStateOf("") }
    var otp by remember { mutableStateOf("") }

    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(modifier = Modifier.fillMaxSize().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Spacer(Modifier.weight(1f))
            // Hero placeholder block — replace with real illustration in design pass
            Box(modifier = Modifier.fillMaxWidth().height(220.dp).clip(RoundedCornerShape(24.dp)).background(MaterialTheme.colorScheme.secondaryContainer))
            Spacer(Modifier.height(32.dp))
            Text("Kibble", style = MaterialTheme.typography.displayMedium.copy(fontStyle = FontStyle.Italic), color = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.height(16.dp))
            Text("Never run out of dog food again.", style = MaterialTheme.typography.headlineSmall)
            Spacer(Modifier.weight(1f))

            if (!state.phoneSent) {
                OutlinedTextField(
                    value = phone,
                    onValueChange = { phone = it },
                    label = { Text("Phone (e.g. +91...)") },
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(16.dp))
                PrimaryButton("Continue with phone", onClick = {
                    viewModel.startPhoneFlow(context as Activity, phone)
                }, enabled = phone.length >= 10 && !state.isLoading)
            } else {
                OutlinedTextField(
                    value = otp,
                    onValueChange = { otp = it },
                    label = { Text("Enter OTP") },
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(16.dp))
                PrimaryButton("Verify", onClick = { viewModel.verifyOtp(otp) }, enabled = otp.length >= 6 && !state.isLoading)
            }

            if (state.error != null) {
                Text(state.error!!, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}
```

(Google Sign-In integration deferred to a follow-up step; phone OTP is enough to unblock onboarding.)

- [ ] **Step 4: Build + commit**

```bash
cd /Users/sdagguba/kibble-reorder/android && ./gradlew :feature:onboarding:assembleDebug
cd /Users/sdagguba/kibble-reorder && git add android/ && git commit -m "feat(android/onboarding): welcome screen with Firebase phone OTP"
```

---

## Tasks 4–10: Onboarding steps 2–9

These tasks all follow the same MVVM pattern: `<step>State.kt` (immutable data class), `<step>Intent.kt` (sealed actions), `<step>ViewModel.kt` (`@HiltViewModel` reading the previous state from Room or savedState, calling `OnboardingRepository`, emitting state via `MutableStateFlow`), and `<step>Screen.kt` (Composable using `OnboardingScaffold` + form inputs + `PrimaryButton`).

For each step below, the implementer:
1. Creates the state, intent, viewmodel, and screen files
2. Writes a ViewModel test asserting that the relevant `OnboardingRepository` method is called on the "Continue" intent
3. Builds and commits

### Task 4: Profile (name + pincode)

- Headline (Noto Serif h2): "Hello! What should we call you?"
- Two `OutlinedTextField`: full name (Manrope), pincode (numeric keyboard, validate 6 digits)
- Continue → `repo.saveProfile(userId, name, pincode)` → `onNext()`
- Test: ViewModel calls `repo.saveProfile` exactly once on `OnContinue`

### Task 5: Dog (name + breed + brand + product)

- Headline: "Who are we feeding?"
- 4 fields: dog name, breed (optional), kibble brand (autocomplete from a static list), kibble product (free text)
- Continue → `repo.createDog(...)` → save returned `dogId` to a savedState handle → `onNext()`
- Test: ViewModel calls `repo.createDog` and stores `dogId`

### Task 6: Container (capacity slider)

- Headline: "How big is your kibble bin?"
- `Slider` 1f..25f, default 10f, large Noto Serif rendering of selected value
- Continue → `repo.createBin(userId, dogId, sensorDeviceId = "PENDING-BLE", capacityKg = slider.value.toDouble())` → save `binId` → `onNext()`
- Note: `sensorDeviceId` is a placeholder; Plan 2b-iii's BLE service updates it after pairing. Include a TODO comment in the screen file referencing Plan 2b-iii Task 3.
- Test: ViewModel calls `repo.createBin` with correct capacity

### Task 7: Calibrate (empty)

- Headline: "Let's calibrate your bin."
- Body: "Empty your kibble bin completely, then place the sensor on the inside of the lid."
- Sage circle illustration with a hand placing a sensor disc (use `Canvas` to draw a simple circle + dot for now; replace with real illustration later)
- Primary button: "Set empty level"
- On click: prompt for distance in mm via a slider 50..400mm or trust a default 250mm. (For Plan 2b-ii, allow numeric entry; Plan 2b-iii's BLE service will replace this with a live read.)
- Continue → `repo.calibrateEmpty(binId, distanceMm)` → `onNext()`
- Skip link: "I'll do this later" → `onNext()` without calibrating
- Test: ViewModel calls `repo.calibrateEmpty` with correct mm

### Task 8: Pack size preference

- Headline: "Which pack size suits you?"
- 4 cards (`OutlinedCard`): 3kg, 5kg, 10kg, **Best value** (selected by default)
- Selecting a card sets the local state; Continue → `repo.savePreferences(userId, packSize=selected, threshold=null, paymentMode=null)` → `onNext()`

### Task 9: Reorder threshold

- Headline: "When should we reorder?"
- `Slider` 5..50 step 5, default 20, dynamic body line: "We'll order when about 4 days of food remains." (recompute days = 10 * (threshold / 20.0))
- Continue → `repo.savePreferences(userId, threshold=slider.toInt())` → `onNext()`

### Task 10: Payment mode

- Headline: "How autonomous should we go?"
- Two cards: "90% autonomous" (default — "We'll prep the order; you confirm.") and "100% autonomous" (subhead: "Use a prepaid wallet — fully hands-off.")
- Continue → `repo.savePreferences(userId, paymentMode=selected)` → `onNext()`

For each of Tasks 4–10:
- [ ] Create the 4 files (State, Intent, ViewModel, Screen) following the same shape as Welcome
- [ ] Write a ViewModel test
- [ ] Build the module
- [ ] Commit with message `feat(android/onboarding): step <N> — <screen name>`

---

## Task 11: Step 8 — Preferred retailer login (cookie + credentials hybrid)

**Files:**
- Create: `retailer/RetailerCatalog.kt`
- Create: `retailer/RetailerPickerScreen.kt`
- Create: `retailer/CookieLoginScreen.kt`
- Create: `retailer/CredentialLoginScreen.kt`
- Create: `retailer/RetailerLoginViewModel.kt`

- [ ] **Step 1: Retailer catalog**

```kotlin
package com.kibble.feature.onboarding.retailer

enum class LoginType { COOKIE, CREDENTIALS }

data class Retailer(
    val id: String,
    val displayName: String,
    val category: String, // "Marketplace" | "Pet specialists" | "Quick commerce" | "D2C"
    val loginType: LoginType,
    val loginUrl: String? = null, // for cookie capture
)

object RetailerCatalog {
    val all = listOf(
        Retailer("supertails", "Supertails", "Pet specialists", LoginType.COOKIE, "https://supertails.com/account/login"),
        Retailer("huft", "HUFT", "Pet specialists", LoginType.COOKIE, "https://www.headsupfortails.com/customer/account/login"),
        Retailer("amazon", "Amazon.in", "Marketplace", LoginType.CREDENTIALS),
        Retailer("blinkit", "Blinkit", "Quick commerce", LoginType.CREDENTIALS),
        Retailer("zepto", "Zepto", "Quick commerce", LoginType.CREDENTIALS),
        Retailer("instamart", "Swiggy Instamart", "Quick commerce", LoginType.CREDENTIALS),
        Retailer("henlo", "Henlo", "D2C", LoginType.COOKIE, "https://henlo.pet/account/login"),
        Retailer("drools", "Drools", "D2C", LoginType.COOKIE, "https://drools.in/account/login"),
        Retailer("pawlicious", "Pawlicious", "D2C", LoginType.COOKIE, "https://pawlicious.in/account/login"),
    )
}
```

- [ ] **Step 2: RetailerPickerScreen**

A grid of cards grouped by category. Selecting a card routes to either CookieLoginScreen (if loginType==COOKIE) or CredentialLoginScreen (if loginType==CREDENTIALS). Use `LazyColumn` with section headers in Manrope label-sm.

```kotlin
package com.kibble.feature.onboarding.retailer

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.kibble.feature.onboarding.components.OnboardingScaffold

@Composable
fun RetailerPickerScreen(onNext: () -> Unit) {
    var selected by remember { mutableStateOf<Retailer?>(null) }
    var showLogin by remember { mutableStateOf(false) }

    if (showLogin && selected != null) {
        when (selected!!.loginType) {
            LoginType.COOKIE -> CookieLoginScreen(retailer = selected!!, onSuccess = onNext, onCancel = { showLogin = false })
            LoginType.CREDENTIALS -> CredentialLoginScreen(retailer = selected!!, onSuccess = onNext, onCancel = { showLogin = false })
        }
        return
    }

    OnboardingScaffold(stepLabel = "Step 8 of 9") {
        Text("Where do you usually shop?", style = MaterialTheme.typography.headlineMedium)
        Spacer(Modifier.height(8.dp))
        Text("Pick your preferred retailer. We'll add others when we find a better deal.", style = MaterialTheme.typography.bodyMedium)
        Spacer(Modifier.height(24.dp))
        LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.weight(1f)) {
            RetailerCatalog.all.groupBy { it.category }.forEach { (category, retailers) ->
                item { Text(category.uppercase(), style = MaterialTheme.typography.labelSmall) }
                items(retailers) { r ->
                    Card(
                        shape = RoundedCornerShape(16.dp),
                        modifier = Modifier.fillMaxWidth().clickable {
                            selected = r
                            showLogin = true
                        }
                    ) {
                        Row(modifier = Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text(r.displayName, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                            Text(
                                if (r.loginType == LoginType.COOKIE) "COOKIE SIGN-IN" else "CREDENTIALS SIGN-IN",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
        }
    }
}
```

- [ ] **Step 3: CookieLoginScreen (WebView capture)**

```kotlin
package com.kibble.feature.onboarding.retailer

import android.annotation.SuppressLint
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.hilt.navigation.compose.hiltViewModel

@SuppressLint("SetJavaScriptEnabled")
@Composable
fun CookieLoginScreen(
    retailer: Retailer,
    onSuccess: () -> Unit,
    onCancel: () -> Unit,
    viewModel: RetailerLoginViewModel = hiltViewModel(),
) {
    Column(modifier = Modifier.fillMaxSize()) {
        TopAppBar(
            title = { Text("Sign in to ${retailer.displayName}") },
            actions = { TextButton(onClick = onCancel) { Text("Cancel") } },
        )
        AndroidView(
            modifier = Modifier.weight(1f),
            factory = { ctx ->
                WebView(ctx).apply {
                    settings.javaScriptEnabled = true
                    settings.domStorageEnabled = true
                    webViewClient = object : WebViewClient() {
                        override fun onPageFinished(view: WebView?, url: String?) {
                            super.onPageFinished(view, url)
                            // Heuristic: when the user lands on a "/account" or similar logged-in page,
                            // we capture cookies and finish.
                            if (url != null && (url.contains("/account") || url.contains("/orders") || url.contains("/profile"))) {
                                val cookieJar = CookieManager.getInstance().getCookie(retailer.loginUrl ?: url) ?: ""
                                if (cookieJar.isNotEmpty()) {
                                    viewModel.saveCookieSession(retailer.id, cookieJar) { ok ->
                                        if (ok) onSuccess()
                                    }
                                }
                            }
                        }
                    }
                    loadUrl(retailer.loginUrl ?: "https://example.com")
                }
            },
        )
    }
}
```

- [ ] **Step 4: CredentialLoginScreen**

```kotlin
package com.kibble.feature.onboarding.retailer

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.kibble.feature.onboarding.components.OnboardingScaffold
import com.kibble.feature.onboarding.components.PrimaryButton

@Composable
fun CredentialLoginScreen(
    retailer: Retailer,
    onSuccess: () -> Unit,
    onCancel: () -> Unit,
    viewModel: RetailerLoginViewModel = hiltViewModel(),
) {
    var login by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    OnboardingScaffold(
        stepLabel = "Step 8 of 9",
        onBack = onCancel,
        primaryAction = {
            PrimaryButton("Sign in to ${retailer.displayName}", onClick = {
                viewModel.saveCredentialSession(retailer.id, login, password) { ok ->
                    if (ok) onSuccess()
                }
            }, enabled = login.isNotBlank() && password.isNotBlank())
        }
    ) {
        Text("Sign in to ${retailer.displayName}", style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(8.dp))
        Text("We'll use these credentials only to check prices and place orders you approve. Stored encrypted. You can revoke any time.", style = MaterialTheme.typography.bodyMedium)
        Spacer(Modifier.height(24.dp))
        OutlinedTextField(value = login, onValueChange = { login = it }, label = { Text("Email or phone") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(16.dp))
        OutlinedTextField(
            value = password, onValueChange = { password = it },
            label = { Text("Password") },
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(),
        )
    }
}
```

- [ ] **Step 5: RetailerLoginViewModel**

```kotlin
package com.kibble.feature.onboarding.retailer

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.kibble.core.common.KibbleResult
import com.kibble.core.database.dao.UserDao
import com.kibble.feature.onboarding.OnboardingRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import javax.inject.Inject

@HiltViewModel
class RetailerLoginViewModel @Inject constructor(
    private val repo: OnboardingRepository,
    private val userDao: UserDao,
    private val json: Json,
) : ViewModel() {

    fun saveCookieSession(retailer: String, cookieJar: String, onResult: (Boolean) -> Unit) {
        viewModelScope.launch {
            val user = userDao.first() ?: return@launch onResult(false)
            val result = repo.saveRetailerSession(user.id, retailer, "cookie", cookieJar)
            onResult(result is KibbleResult.Success)
        }
    }

    fun saveCredentialSession(retailer: String, login: String, password: String, onResult: (Boolean) -> Unit) {
        viewModelScope.launch {
            val user = userDao.first() ?: return@launch onResult(false)
            val payload = json.encodeToString(mapOf("email" to login, "password" to password))
            val result = repo.saveRetailerSession(user.id, retailer, "credentials", payload)
            onResult(result is KibbleResult.Success)
        }
    }
}
```

- [ ] **Step 6: Build + commit**

```bash
cd /Users/sdagguba/kibble-reorder/android && ./gradlew :feature:onboarding:assembleDebug
cd /Users/sdagguba/kibble-reorder && git add android/ && git commit -m "feat(android/onboarding): step 8 — preferred retailer login (cookie WebView + credentials)"
```

---

## Task 12: Step 9 — Delivery estimate + onboarding completion

**Files:**
- Create: `delivery/DeliveryEstimateState.kt`, `DeliveryEstimateViewModel.kt`, `DeliveryEstimateScreen.kt`

- [ ] **Step 1: State**

```kotlin
package com.kibble.feature.onboarding.delivery

data class DeliveryEstimateState(
    val isLoading: Boolean = true,
    val estimates: List<RetailerEstimate> = emptyList(),
    val deferred: Boolean = false, // true when Plan 3 endpoint not yet available
    val error: String? = null,
)

data class RetailerEstimate(val retailer: String, val days: Int)
```

- [ ] **Step 2: ViewModel**

```kotlin
package com.kibble.feature.onboarding.delivery

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.kibble.core.database.dao.UserDao
import com.kibble.feature.onboarding.OnboardingRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class DeliveryEstimateViewModel @Inject constructor(
    private val repo: OnboardingRepository,
    private val userDao: UserDao,
) : ViewModel() {
    private val _state = MutableStateFlow(DeliveryEstimateState())
    val state = _state.asStateFlow()

    init {
        viewModelScope.launch {
            // Plan 3 endpoint not implemented; mark deferred and continue.
            _state.value = _state.value.copy(isLoading = false, deferred = true)
        }
    }

    fun finish(onComplete: () -> Unit) {
        viewModelScope.launch {
            val user = userDao.first()
            if (user != null) repo.completeOnboarding(user.id)
            onComplete()
        }
    }
}
```

- [ ] **Step 3: Screen**

```kotlin
package com.kibble.feature.onboarding.delivery

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.kibble.feature.onboarding.components.OnboardingScaffold
import com.kibble.feature.onboarding.components.PrimaryButton

@Composable
fun DeliveryEstimateScreen(
    onComplete: () -> Unit,
    viewModel: DeliveryEstimateViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    OnboardingScaffold(
        stepLabel = "Step 9 of 9",
        primaryAction = { PrimaryButton("Finish setup", onClick = { viewModel.finish(onComplete) }) }
    ) {
        Text("Last step — checking delivery.", style = MaterialTheme.typography.headlineMedium)
        Spacer(Modifier.height(8.dp))
        Text(
            if (state.deferred) "We'll confirm delivery details when your first reorder is placed."
            else "This may take a moment.",
            style = MaterialTheme.typography.bodyMedium,
        )
        Spacer(Modifier.height(24.dp))
        if (state.isLoading) CircularProgressIndicator()
    }
}
```

- [ ] **Step 4: Build + commit**

```bash
cd /Users/sdagguba/kibble-reorder/android && ./gradlew :feature:onboarding:assembleDebug
cd /Users/sdagguba/kibble-reorder && git add android/ && git commit -m "feat(android/onboarding): step 9 — delivery estimate + onboarding completion"
```

---

## Task 13: End-to-end smoke test

- [ ] **Step 1: Bring up backend + emulator**
- [ ] **Step 2: Sign up a fresh test user via Firebase phone OTP**
- [ ] **Step 3: Walk through all 9 onboarding steps**
- [ ] **Step 4: Verify backend received correct calls** (check uvicorn logs)
- [ ] **Step 5: Confirm app routes to MAIN after delivery step finishes**
- [ ] **Step 6: Commit any tweaks**

---

## Definition of Done

- [ ] All 9 onboarding screens render with Deep Botanical theme
- [ ] User can complete onboarding end-to-end on emulator
- [ ] Each step persists to backend via `OnboardingRepository`
- [ ] Step 8 supports both cookie-WebView and credential-form flows
- [ ] Step 9 gracefully shows the Plan 3 deferred state
- [ ] `./gradlew :feature:onboarding:test` passes (~15 ViewModel tests)
- [ ] `./gradlew :app:assembleDebug` builds the full app

---

## Notes for the Implementer

- **Each step's MVVM scaffold is identical:** state class, intent sealed class, ViewModel with `MutableStateFlow`, Composable using `OnboardingScaffold` + `PrimaryButton`. Don't fight the pattern.
- **`OnboardingScaffold`'s step indicator** uses Manrope label-sm: `"Step <n> of 9"`. Pass it as the `stepLabel` parameter.
- **Saving binId / dogId between screens:** stash in a small `SavedStateHandle`-backed `OnboardingProgressRepository` if needed, or read from Room (the latter is simpler since each step writes to the backend, which echoes back into Room via the repository).
- **WebView cookie capture is brittle.** The heuristic in CookieLoginScreen (route to /account = success) works for most retailers but Amazon needs a different signal (the URL changes to amazon.in homepage post-login). Add per-retailer success URL patterns to `RetailerCatalog` if needed.
- **Google Sign-In** is deferred — phone OTP works for India and is enough for Plan 2b-ii. Add Google Sign-In in a follow-up.
