import { describe, it, expect } from 'vitest'
import { stateMapFor, topTwoParties } from './stateMaps'

describe('which results pages link to a state map', () => {
  it("a state's 2026 midterm ballots do: district and statewide", () => {
    expect(stateMapFor('2026 Midterm Washington District 2')).toEqual({ name: 'Washington', code: 'WA', year: 2026 })
    expect(stateMapFor('2026 Midterm · Washington: Supreme Court & statewide measures')).toEqual({ name: 'Washington', code: 'WA', year: 2026 })
    expect(stateMapFor('2026 Midterm Oregon District 4')).toEqual({ name: 'Oregon', code: 'OR', year: 2026 })
    expect(stateMapFor('2026 Midterm · Idaho: statewide races & measures')).toEqual({ name: 'Idaho', code: 'ID', year: 2026 })
    expect(stateMapFor('2026 Midterm Alaska')).toEqual({ name: 'Alaska', code: 'AK', year: 2026 })
    expect(stateMapFor('2026 Midterm New York District 14')).toEqual({ name: 'New York', code: 'NY', year: 2026 })
    expect(stateMapFor('2026 Midterm West Virginia District 2')).toEqual({ name: 'West Virginia', code: 'WV', year: 2026 })
    expect(stateMapFor('2026 Midterm Virginia District 2')).toEqual({ name: 'Virginia', code: 'VA', year: 2026 })
  })
  it('any cycle, with its year (maps are per cycle, 2026-11-22)', () => {
    expect(stateMapFor('2028 General Washington District 2')).toEqual({ name: 'Washington', code: 'WA', year: 2028 })
    expect(stateMapFor('2026 Midterm Washington District 2')?.year).toBe(2026)
    expect(stateMapFor('2030 Midterm Wyoming')).toEqual({ name: 'Wyoming', code: 'WY', year: 2030 })
  })
  it("others don't: other states, other polls, a look-alike name", () => {
    expect(stateMapFor('2026 Midterm District of Columbia District 1')).toBeNull()
    expect(stateMapFor('Washington parks questionnaire')).toBeNull()
    expect(stateMapFor('2026 Midterm Washingtonia')).toBeNull()
    expect(stateMapFor(undefined)).toBeNull()
  })
})

describe('top 2: the two leading parties', () => {
  it("adds up a party's candidates, so two Democrats are one Dem share", () => {
    expect(topTwoParties([
      { party: 'DEM', pct: 40 }, { party: 'DEM', pct: 25 }, { party: 'REP', pct: 30 }, { party: 'OTHER', pct: 5 },
    ])).toEqual([['DEM', 65], ['REP', 30]])
  })
  it('shows one party when only one ran, and breaks ties Dem, Rep, Ind, Other', () => {
    expect(topTwoParties([{ party: 'DEM', pct: 70 }, { party: 'DEM', pct: 30 }])).toEqual([['DEM', 100]])
    expect(topTwoParties([{ party: 'OTHER', pct: 50 }, { party: 'REP', pct: 50 }])).toEqual([['REP', 50], ['OTHER', 50]])
  })
})
