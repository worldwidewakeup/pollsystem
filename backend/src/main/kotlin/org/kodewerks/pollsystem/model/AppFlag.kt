package org.kodewerks.pollsystem.model

import jakarta.persistence.Column
import jakarta.persistence.Entity
import jakarta.persistence.Id
import jakarta.persistence.Table
import java.time.Instant

/**
 * Singleton row (id is always 1, guarded by a CHECK constraint) holding
 * global platform flags. See V21.
 */
@Entity
@Table(name = "app_flags")
data class AppFlag(
    @Id
    val id: Int = 1,

    @Column(name = "polls_disabled", nullable = false)
    val pollsDisabled: Boolean = false,

    @Column(name = "updated_at", nullable = false)
    val updatedAt: Instant = Instant.now(),

    @Column(name = "updated_by")
    val updatedBy: Long? = null,

    /** Local development only (V35): the results privacy threshold override; null = configured. */
    @Column(name = "results_threshold")
    val resultsThreshold: Int? = null,

    /** Moderation (V45): BLOCK or WARN for listed words outside comments; null = configured. */
    @Column(name = "text_mode")
    val textMode: String? = null,

    /** The current election cycle (V47): its year, election day and kind (MIDTERM or GENERAL). */
    @Column(name = "election_year", nullable = false)
    val electionYear: Int = 2026,

    @Column(name = "election_date", nullable = false)
    val electionDate: java.time.LocalDate = java.time.LocalDate.of(2026, 11, 3),

    @Column(name = "election_kind", nullable = false)
    val electionKind: String = "MIDTERM"
)
