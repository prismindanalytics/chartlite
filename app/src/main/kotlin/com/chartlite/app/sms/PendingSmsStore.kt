package com.chartlite.app.sms

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * Encrypted, bounded storage for clinical SMS messages received in the background.
 *
 * The SMS body is encrypted by the wire protocol, but the sender and timestamp are
 * still health-data metadata. Keeping the complete envelope in ordinary preferences
 * exposed that metadata in app backups/debug extractions on older installations.
 */
object PendingSmsStore {
    private const val SECURE_PREFS = "pending_sms_secure"
    private const val LEGACY_PREFS = "pending_sms"
    private const val MESSAGES_KEY = "messages"
    private const val MAX_PENDING = 50

    fun getMessages(context: Context): Set<String> {
        val appContext = context.applicationContext
        val secure = securePreferences(appContext)
        migrateLegacyIfNeeded(appContext, secure)
        return secure.getStringSet(MESSAGES_KEY, emptySet())?.toSet() ?: emptySet()
    }

    fun addMessage(context: Context, sender: String?, timestamp: Long, body: String) {
        val appContext = context.applicationContext
        val secure = securePreferences(appContext)
        migrateLegacyIfNeeded(appContext, secure)

        val updated = (secure.getStringSet(MESSAGES_KEY, emptySet()) ?: emptySet())
            .toMutableSet()
            .apply { add("${sender.orEmpty()}|$timestamp|$body") }
        val capped = updated
            .sortedByDescending { it.split("|").getOrNull(1)?.toLongOrNull() ?: 0L }
            .take(MAX_PENDING)
            .toSet()

        // A BroadcastReceiver can be killed as soon as onReceive returns. Commit
        // synchronously so a clinical message is not lost between RAM and disk.
        check(secure.edit().putStringSet(MESSAGES_KEY, capped).commit()) {
            "Unable to persist incoming clinical SMS"
        }
    }

    private fun securePreferences(context: Context): SharedPreferences {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        return EncryptedSharedPreferences.create(
            context,
            SECURE_PREFS,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }

    private fun migrateLegacyIfNeeded(context: Context, secure: SharedPreferences) {
        val legacy = context.getSharedPreferences(LEGACY_PREFS, Context.MODE_PRIVATE)
        val legacyMessages = legacy.getStringSet(MESSAGES_KEY, emptySet())?.toSet().orEmpty()
        if (legacyMessages.isEmpty()) return

        val existing = secure.getStringSet(MESSAGES_KEY, emptySet())?.toSet().orEmpty()
        val merged = (existing + legacyMessages)
            .sortedByDescending { it.split("|").getOrNull(1)?.toLongOrNull() ?: 0L }
            .take(MAX_PENDING)
            .toSet()
        if (secure.edit().putStringSet(MESSAGES_KEY, merged).commit()) {
            legacy.edit().clear().commit()
        }
    }
}
