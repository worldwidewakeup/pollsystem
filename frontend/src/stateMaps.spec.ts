import { describe, it, expect } from 'vitest'
import { stateMapFor, topTwoParties } from './stateMaps'

describe('which results pages link to a state map', () => {
  it("a state's 2026 midterm ballots do: district and statewide", () => {
    expect(stateMapFor('2026 Midterm Washington District 2', '2026 Midterm')).toEqual({ name: 'Washington', code: 'WA' })
    expect(stateMapFor('2026 Midterm · Washington: Supreme Court & statewide measures', '2026 Midterm')).toEqual({ name: 'Washington', code: 'WA' })
    expect(stateMapFor('2026 Midterm Oregon District 4', '2026 Midterm')).toEqual({ name: 'Oregon', code: 'OR' })
    expect(stateMapFor('2026 Midterm · Idaho: statewide races & measures', '2026 Midterm')).toEqual({ name: 'Idaho', code: 'ID' })
    expect(stateMapFor('2026 Midterm Alaska', '2026 Midterm')).toEqual({ name: 'Alaska', code: 'AK' })
    expect(stateMapFor('2026 Midterm New York District 14', '2026 Midterm')).toEqual({ name: 'New York', code: 'NY' })
    expect(stateMapFor('2026 Midterm West Virginia District 2', '2026 Midterm')).toEqual({ name: 'West Virginia', code: 'WV' })
    expect(stateMapFor('2026 Midterm Virginia District 2', '2026 Midterm')).toEqual({ name: 'Virginia', code: 'VA' })
  })
  it('follows the cycle (V47): 2028 General ballots once the cycle is 2028, not 2026 ones', () => {
    expect(stateMapFor('2028 General Washington District 2', '2028 General')).toEqual({ name: 'Washington', code: 'WA' })
    expect(stateMapFor('2026 Midterm Washington District 2', '2028 General')).toBeNull()
    expect(stateMapFor('2026 Midterm Washington District 2', null)).toBeNull()
  })
  it("others don't: other states, other polls, a look-alike name", () => {
    expect(stateMapFor('2026 Midterm District of Columbia District 1', '2026 Midterm')).toBeNull()
    expect(stateMapFor('Washington parks questionnaire', '2026 Midterm')).toBeNull()
    expect(stateMapFor('2026 Midterm Washingtonia', '2026 Midterm')).toBeNull()
    expect(stateMapFor(undefined, '2026 Midterm')).toBeNull()
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
