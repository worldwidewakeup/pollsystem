-- V49__district_counties_per_cycle.sql
-- District <-> county rows belong to an election year (decided 2026-11-22):
-- when a state's lines change, the new cycle gets its own rows and the old
-- cycle's ballots keep theirs, so a county search for a 2026 ballot uses the
-- 2026 lines even after 2028's are loaded. Existing rows are 2026's.
-- (State maps are kept per cycle the same way: frontend/public/maps/<year>/XX.json.)
ALTER TABLE district_counties ADD COLUMN election_year INT NOT NULL DEFAULT 2026;
ALTER TABLE district_counties ALTER COLUMN election_year DROP DEFAULT;
ALTER TABLE district_counties DROP CONSTRAINT district_counties_pkey;
ALTER TABLE district_counties ADD PRIMARY KEY (election_year, plan, state_id, district, county_id);
DROP INDEX IF EXISTS idx_district_counties_county;
CREATE INDEX idx_district_counties_county ON district_counties(county_id, election_year);
