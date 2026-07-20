package com.chartlite.app.ui.components

import android.bluetooth.BluetoothManager
import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.chartlite.app.ui.theme.*

/**
 * Three-tier connectivity indicator.
 *
 * - RED: Offline — Tier 1 Active (on-device only) — always visible
 * - AMBER: Bluetooth Available — Tier 2 Ready (peer sync)
 * - GREEN: Connected — Tier 3 Active
 *
 * Uses ConnectivityManager.NetworkCallback for event-driven updates instead of polling.
 * Checks NET_CAPABILITY_VALIDATED to avoid false positives on captive portals.
 */
@Composable
fun TierIndicator() {
    val context = LocalContext.current
    var tier by remember { mutableStateOf(detectTier(context)) }

    // Event-driven connectivity monitoring via NetworkCallback
    DisposableEffect(Unit) {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) {
                tier = detectTier(context)
            }
            override fun onLost(network: Network) {
                tier = detectTier(context)
            }
            override fun onAvailable(network: Network) {
                tier = detectTier(context)
            }
        }
        val request = NetworkRequest.Builder()
            .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .build()
        cm?.registerNetworkCallback(request, callback)

        onDispose {
            cm?.unregisterNetworkCallback(callback)
        }
    }

    val (dotColor, label) = when (tier) {
        ConnectivityTier.OFFLINE -> AlertRed to "Offline. Local only"
        ConnectivityTier.BLUETOOTH -> WarningAmber to "Bluetooth available"
        ConnectivityTier.CONNECTED -> BrandGreen to "Connected"
    }

    val animatedColor by animateColorAsState(targetValue = dotColor, label = "tier_dot")

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(Neutral100)
            .padding(horizontal = 16.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center
    ) {
        Box(
            modifier = Modifier
                .size(8.dp)
                .clip(CircleShape)
                .background(animatedColor)
        )
        Spacer(Modifier.width(8.dp))
        Text(
            label,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Medium,
            color = Neutral700
        )
    }
}

enum class ConnectivityTier { OFFLINE, BLUETOOTH, CONNECTED }

internal fun detectTier(context: Context): ConnectivityTier {
    val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
    val network = cm?.activeNetwork
    val caps = network?.let { cm.getNetworkCapabilities(it) }
    // NET_CAPABILITY_VALIDATED ensures we're not behind a captive portal
    val hasValidatedInternet = caps?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true &&
            caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)

    if (hasValidatedInternet) return ConnectivityTier.CONNECTED

    // Check Bluetooth
    val btManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
    val btEnabled = try { btManager?.adapter?.isEnabled == true } catch (_: SecurityException) { false }

    if (btEnabled) return ConnectivityTier.BLUETOOTH

    return ConnectivityTier.OFFLINE
}
