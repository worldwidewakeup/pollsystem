-- V46__district_counties.sql
-- Congressional district ↔ county, for search only (decided 2026-11-20).
-- A state's district ballots ("2026 Midterm Washington District 2") keep their
-- statewide area, so results and voting rules don't change; these rows only let
-- a county search find the districts that touch the county. A county split
-- between districts has one row per district, whole = FALSE.
--
-- plan names the map: CD119 = the districts of the 119th Congress (in use for
-- the 2026 elections where a state didn't redraw). When a state's map changes,
-- load the new plan's rows and drop the old ones for that state.
-- Source: Census tab20_cd11920_county20_natl.txt, via scripts/maps/district-counties.py.

CREATE TABLE district_counties (
    plan      VARCHAR(20) NOT NULL,
    state_id  BIGINT NOT NULL REFERENCES states(id),
    district  INT NOT NULL CHECK (district >= 1),
    county_id BIGINT NOT NULL REFERENCES counties(id),
    whole     BOOLEAN NOT NULL,
    PRIMARY KEY (plan, state_id, district, county_id)
);
CREATE INDEX idx_district_counties_county ON district_counties(county_id);

-- Washington (2022 map, unchanged for 2026).
INSERT INTO district_counties (plan, state_id, district, county_id, whole)
SELECT 'CD119', s.id, v.district, c.id, v.whole
FROM (VALUES
    ('WA', 'Adams', 4, FALSE),
    ('WA', 'Adams', 5, FALSE),
    ('WA', 'Asotin', 5, TRUE),
    ('WA', 'Benton', 4, TRUE),
    ('WA', 'Chelan', 8, TRUE),
    ('WA', 'Clallam', 6, TRUE),
    ('WA', 'Clark', 3, TRUE),
    ('WA', 'Columbia', 5, TRUE),
    ('WA', 'Cowlitz', 3, TRUE),
    ('WA', 'Douglas', 4, FALSE),
    ('WA', 'Douglas', 8, FALSE),
    ('WA', 'Ferry', 5, TRUE),
    ('WA', 'Franklin', 4, FALSE),
    ('WA', 'Franklin', 5, FALSE),
    ('WA', 'Garfield', 5, TRUE),
    ('WA', 'Grant', 4, TRUE),
    ('WA', 'Grays Harbor', 6, TRUE),
    ('WA', 'Island', 2, TRUE),
    ('WA', 'Jefferson', 6, TRUE),
    ('WA', 'King', 1, FALSE),
    ('WA', 'King', 7, FALSE),
    ('WA', 'King', 8, FALSE),
    ('WA', 'King', 9, FALSE),
    ('WA', 'Kitsap', 6, TRUE),
    ('WA', 'Kittitas', 8, TRUE),
    ('WA', 'Klickitat', 4, TRUE),
    ('WA', 'Lewis', 3, TRUE),
    ('WA', 'Lincoln', 5, TRUE),
    ('WA', 'Mason', 6, TRUE),
    ('WA', 'Okanogan', 4, TRUE),
    ('WA', 'Pacific', 3, TRUE),
    ('WA', 'Pend Oreille', 5, TRUE),
    ('WA', 'Pierce', 6, FALSE),
    ('WA', 'Pierce', 8, FALSE),
    ('WA', 'Pierce', 10, FALSE),
    ('WA', 'San Juan', 2, TRUE),
    ('WA', 'Skagit', 2, TRUE),
    ('WA', 'Skamania', 3, TRUE),
    ('WA', 'Snohomish', 1, FALSE),
    ('WA', 'Snohomish', 2, FALSE),
    ('WA', 'Snohomish', 8, FALSE),
    ('WA', 'Spokane', 5, TRUE),
    ('WA', 'Stevens', 5, TRUE),
    ('WA', 'Thurston', 3, FALSE),
    ('WA', 'Thurston', 10, FALSE),
    ('WA', 'Wahkiakum', 3, TRUE),
    ('WA', 'Walla Walla', 5, TRUE),
    ('WA', 'Whatcom', 2, TRUE),
    ('WA', 'Whitman', 5, TRUE),
    ('WA', 'Yakima', 4, TRUE)
) AS v(st, county, district, whole)
JOIN states s ON s.initial = v.st
JOIN counties c ON c.state_id = s.id AND c.name = v.county;
