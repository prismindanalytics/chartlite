package com.chartlite.app.sms

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import android.util.Log

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
                try {
                    PendingSmsStore.addMessage(
                        context = context,
                        sender = message.originatingAddress,
                        timestamp = System.currentTimeMillis(),
                        body = body
                    )
                } catch (e: Exception) {
                    // Never fall back to plaintext storage. Log only the failure
                    // class — not sender, timestamp, or clinical payload.
                    Log.e("SMSReceiver", "Unable to store clinical SMS securely", e)
                }
            }
        }
    }
}
