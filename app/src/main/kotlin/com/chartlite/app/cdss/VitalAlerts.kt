package com.chartlite.app.cdss

import com.chartlite.app.model.AlertSeverity
import com.chartlite.app.model.CDSSAlert
import com.chartlite.app.model.VitalSigns

class VitalAlerts {

    /**
     * Age band for pulse / respiratory-rate / systolic-BP thresholds.
     * Normal ranges follow the PALS reference tables; the critical bounds are
     * the widely taught "severely abnormal" margins around them. Hypotension
     * (sbpHypo) uses the PALS rule: <70 infant, <70 + 2×age (1–10 y) — a late,
     * decompensated sign in children, so it alerts CRITICAL directly.
     */
    private data class AgeBand(
        val hrLow: Int, val hrHigh: Int, val hrCritLow: Int, val hrCritHigh: Int,
        val rrLow: Int, val rrHigh: Int, val rrCritLow: Int, val rrCritHigh: Int,
        val sbpHypo: Int
    )

    /**
     * Check vital signs against age-appropriate thresholds.
     *
     * @param ageMonths patient age in months, or null when unknown. Null and
     *   ≥ 144 months (12 y) use the adult thresholds — identical to the
     *   historical behavior of this checker.
     */
    fun check(vitals: VitalSigns, ageMonths: Int? = null): List<CDSSAlert> {
        val band = pediatricBand(ageMonths)
        return if (band == null) checkAdult(vitals) else checkPediatric(vitals, band)
    }

    private fun pediatricBand(ageMonths: Int?): AgeBand? = when {
        ageMonths == null || ageMonths >= 144 -> null // unknown or ≥12 y → adult
        ageMonths < 12 -> AgeBand(100, 160, 80, 205, 30, 53, 20, 70, sbpHypo = 70)
        ageMonths < 36 -> AgeBand(90, 150, 70, 190, 22, 37, 15, 60, sbpHypo = 70 + 2 * (ageMonths / 12))
        ageMonths < 72 -> AgeBand(80, 140, 65, 185, 20, 28, 12, 50, sbpHypo = 70 + 2 * (ageMonths / 12))
        else -> AgeBand(70, 120, 60, 170, 18, 25, 10, 45, sbpHypo = 70 + 2 * minOf(ageMonths / 12, 10))
    }

    private fun checkPediatric(vitals: VitalSigns, band: AgeBand): List<CDSSAlert> {
        val alerts = mutableListOf<CDSSAlert>()

        vitals.systolicBP?.let { sbp ->
            when {
                sbp < band.sbpHypo -> alerts.add(critical("Systolic BP $sbp mmHg is hypotensive for age (threshold ${band.sbpHypo})"))
                sbp > 200 -> alerts.add(critical("Systolic BP $sbp mmHg is critically high"))
                sbp > 160 -> alerts.add(warning("Systolic BP $sbp mmHg is high for a child"))
                else -> {}
            }
        }

        // Low diastolic is age/percentile-dependent in children (an infant DBP
        // of 40 is normal) — only the extreme high side alerts.
        vitals.diastolicBP?.let { dbp ->
            when {
                dbp > 120 -> alerts.add(critical("Diastolic BP $dbp mmHg is critically high"))
                dbp > 100 -> alerts.add(warning("Diastolic BP $dbp mmHg is high for a child"))
                else -> {}
            }
        }

        vitals.temperature?.let { temp ->
            when {
                temp < 35.0f || temp > 40.0f -> alerts.add(critical("Temperature ${temp}°C is critically abnormal"))
                temp < 35.5f || temp > 38.5f -> alerts.add(warning("Temperature ${temp}°C is outside normal range"))
                else -> {}
            }
        }

        vitals.pulse?.let { hr ->
            when {
                hr < band.hrCritLow || hr > band.hrCritHigh -> alerts.add(critical("Pulse $hr bpm is critically abnormal for age"))
                hr < band.hrLow || hr > band.hrHigh -> alerts.add(warning("Pulse $hr bpm is outside normal range for age (${band.hrLow}–${band.hrHigh})"))
                else -> {}
            }
        }

        vitals.oxygenSaturation?.let { spo2 ->
            when {
                spo2 < 90 -> alerts.add(critical("SpO2 $spo2% is critically low"))
                spo2 < 94 -> alerts.add(warning("SpO2 $spo2% is below normal"))
                else -> {}
            }
        }

        vitals.respiratoryRate?.let { rr ->
            when {
                rr < band.rrCritLow || rr > band.rrCritHigh -> alerts.add(critical("Respiratory rate $rr is critically abnormal for age"))
                rr < band.rrLow || rr > band.rrHigh -> alerts.add(warning("Respiratory rate $rr is outside normal range for age (${band.rrLow}–${band.rrHigh})"))
                else -> {}
            }
        }

        return alerts
    }

    private fun checkAdult(vitals: VitalSigns): List<CDSSAlert> {
        val alerts = mutableListOf<CDSSAlert>()

        vitals.systolicBP?.let { sbp ->
            when {
                sbp < 70 || sbp > 200 -> alerts.add(critical("Systolic BP $sbp mmHg is critically abnormal"))
                sbp < 90 || sbp > 160 -> alerts.add(warning("Systolic BP $sbp mmHg is outside normal range"))
            }
        }

        vitals.diastolicBP?.let { dbp ->
            when {
                dbp < 40 || dbp > 120 -> alerts.add(critical("Diastolic BP $dbp mmHg is critically abnormal"))
                dbp < 50 || dbp > 100 -> alerts.add(warning("Diastolic BP $dbp mmHg is outside normal range"))
            }
        }

        vitals.temperature?.let { temp ->
            when {
                temp < 35.0f || temp > 40.0f -> alerts.add(critical("Temperature ${temp}°C is critically abnormal"))
                temp < 35.5f || temp > 38.5f -> alerts.add(warning("Temperature ${temp}°C is outside normal range"))
            }
        }

        vitals.pulse?.let { hr ->
            when {
                hr < 40 || hr > 150 -> alerts.add(critical("Pulse $hr bpm is critically abnormal"))
                hr < 50 || hr > 120 -> alerts.add(warning("Pulse $hr bpm is outside normal range"))
            }
        }

        vitals.oxygenSaturation?.let { spo2 ->
            when {
                spo2 < 90 -> alerts.add(critical("SpO2 $spo2% is critically low"))
                spo2 < 94 -> alerts.add(warning("SpO2 $spo2% is below normal"))
            }
        }

        vitals.respiratoryRate?.let { rr ->
            when {
                rr < 8 || rr > 30 -> alerts.add(critical("Respiratory rate $rr is critically abnormal"))
                rr < 12 || rr > 20 -> alerts.add(warning("Respiratory rate $rr is outside normal range"))
            }
        }

        return alerts
    }

    private fun critical(message: String) = CDSSAlert(
        severity = AlertSeverity.CRITICAL,
        category = "Vitals",
        message = message,
        relatedField = "vitals"
    )

    private fun warning(message: String) = CDSSAlert(
        severity = AlertSeverity.WARNING,
        category = "Vitals",
        message = message,
        relatedField = "vitals"
    )
}
