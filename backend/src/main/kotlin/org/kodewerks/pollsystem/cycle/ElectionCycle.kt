package org.kodewerks.pollsystem.cycle

import org.kodewerks.pollsystem.security.AppUserDetails
import org.kodewerks.pollsystem.superadmin.GlobalFlagService
import org.springframework.http.HttpStatus
import org.springframework.security.core.annotation.AuthenticationPrincipal
import org.springframework.stereotype.Service
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PutMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RestController
import org.springframework.web.server.ResponseStatusException
import java.time.LocalDate

enum class ElectionKind(val titleWord: String) { MIDTERM("Midterm"), GENERAL("General") }

/**
 * The current election cycle (V47, decided 2026-11-20). Ballot titles start
 * with [titlePrefix]: "2026 Midterm · Washington: …" (statewide),
 * "2026 Midterm Washington District 2", "2026 Midterm Alaska" (one seat).
 */
data class ElectionCycleDto(val year: Int, val date: LocalDate, val kind: ElectionKind) {
    val titlePrefix: String get() = "$year ${kind.titleWord}"

    companion object {
        /** A federal election year's kind: presidential years divide by 4. */
        fun kindOf(year: Int): ElectionKind = if (year % 4 == 0) ElectionKind.GENERAL else ElectionKind.MIDTERM

        /** "2026 Midterm", "2028 General": the title prefix of any cycle's ballots, from its year. */
        fun prefixFor(year: Int): String = "$year ${kindOf(year).titleWord}"
    }
}

data class SetElectionCycleRequest(val year: Int, val date: LocalDate, val kind: ElectionKind)

@Service
class ElectionCycleService(private val flags: GlobalFlagService) {
    fun current(): ElectionCycleDto = flags.current().let {
        ElectionCycleDto(it.electionYear, it.electionDate, runCatching { ElectionKind.valueOf(it.electionKind) }.getOrDefault(ElectionKind.MIDTERM))
    }
}

@RestController
class ElectionCycleController(private val cycle: ElectionCycleService, private val flags: GlobalFlagService) {

    /** Public: the map pages and the results page read it. */
    @GetMapping("/api/election-cycle")
    fun get(): ElectionCycleDto = cycle.current()

    /** SUPER (the /api/super namespace): switch the site to a new cycle. */
    @PutMapping("/api/super/flags/election-cycle")
    fun set(@RequestBody body: SetElectionCycleRequest, @AuthenticationPrincipal principal: AppUserDetails): ElectionCycleDto {
        if (body.year !in 2000..2100) throw bad("The year must be between 2000 and 2100")
        if (body.date.year != body.year) throw bad("Election day must be in ${body.year}")
        // Federal elections fall in even years; midterms are the ones between presidential years.
        if (body.year % 2 != 0) throw bad("Federal elections are in even years")
        val presidential = body.year % 4 == 0
        if (presidential && body.kind == ElectionKind.MIDTERM) throw bad("${body.year} is a presidential year: choose General")
        if (!presidential && body.kind == ElectionKind.GENERAL) throw bad("${body.year} is a midterm year: choose Midterm")
        flags.setElectionCycle(body.year, body.date, body.kind.name, principal.user.id)
        return cycle.current()
    }

    private fun bad(msg: String) = ResponseStatusException(HttpStatus.BAD_REQUEST, msg)
}
