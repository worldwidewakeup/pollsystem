-- V47__election_cycle_setting.sql
-- The current election cycle (decided 2026-11-20): the year, election day and
-- kind (MIDTERM or GENERAL, i.e. presidential) the site's ballots belong to.
-- Ballot titles start "<year> Midterm" or "<year> General"; the state maps and
-- the results page's map link find a state's ballots by that prefix. A super
-- changes it on the Super dashboard when a new cycle's ballots are loaded.
-- Preparing the next cycle (scripts/election-cycle/) doesn't need it changed:
-- the scripts read their own per-cycle file.
ALTER TABLE app_flags
    ADD COLUMN election_year INT NOT NULL DEFAULT 2026 CHECK (election_year BETWEEN 2000 AND 2100),
    ADD COLUMN election_date DATE NOT NULL DEFAULT DATE '2026-11-03',
    ADD COLUMN election_kind VARCHAR(10) NOT NULL DEFAULT 'MIDTERM' CHECK (election_kind IN ('MIDTERM', 'GENERAL'));
