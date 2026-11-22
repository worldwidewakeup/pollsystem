// The current election cycle (V47, 2026-11-20): year, election day, kind and
// the ballot-title prefix ("2026 Midterm"). Loaded once per page load and
// shared; null until it arrives (or if it can't be loaded).
import { ref, type Ref } from 'vue'
import axios from 'axios'

export interface ElectionCycle {
  year: number
  date: string
  kind: 'MIDTERM' | 'GENERAL'
  titlePrefix: string
}

const cycle = ref<ElectionCycle | null>(null)
let loading: Promise<void> | null = null

export function useElectionCycle(): Ref<ElectionCycle | null> {
  if (!loading) {
    loading = axios.get<ElectionCycle>('/api/election-cycle')
      .then(r => { cycle.value = r.data })
      .catch(() => { loading = null })   // try again on the next page that asks
  }
  return cycle
}

/** The cycle once it has loaded (null if it can't be). */
export async function loadElectionCycle(): Promise<ElectionCycle | null> {
  useElectionCycle()
  try { await loading } catch { /* null below */ }
  return cycle.value
}

/** After a super changes it on the dashboard. */
export function setElectionCycle(next: ElectionCycle) {
  cycle.value = next
}
