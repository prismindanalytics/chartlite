package com.chartlite.app.sms

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony

/**
 * Receives incoming SMS messages and checks if they're encrypted clinical records.
 * Stores them for later decryption by the provider.
 */
class SMSReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return

        val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent)
        for (message in messages) {
            val body = message.messageBody ?: continue
            if (SMSEncryption.looksLikeClinicalSMS(body)) {
                // Store for later decryption
                // In a full implementation, this would save to a pending-SMS table
                val prefs = context.getSharedPreferences("pending_sms", Context.MODE_PRIVATE)
                val existing = prefs.getStringSet("messages", mutableSetOf()) ?: mutableSetOf()
                val updated = existing.toMutableSet()
                updated.add("${message.originatingAddress}|${System.currentTimeMillis()}|$body")
                // Cap retained messages so the set can't grow without bound —
                // drop oldest first (entries embed an epoch-ms timestamp).
                val capped = if (updated.size > MAX_PENDING) {
                    updated.sortedByDescending { it.split("|").getOrNull(1)?.toLongOrNull() ?: 0L }
                        .take(MAX_PENDING)
                        .toSet()
                } else updated
                prefs.edit().putStringSet("messages", capped).apply()
            }
        }
    }

    companion object {
        private const val MAX_PENDING = 50
    }
}
