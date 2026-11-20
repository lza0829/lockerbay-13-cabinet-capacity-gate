import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import Bay from '../src/pages/Bay.vue'
import Ingest from '../src/pages/Ingest.vue'
import Proofs from '../src/pages/Proofs.vue'
import Reclaim from '../src/pages/Reclaim.vue'
import { api } from '../src/api.js'

const FULL_SNAP = {
  cabinet_id: 'CAB-A', known: true, label: '东门柜阵', site: '园区东门',
  capacity: 4, open_occupancies: 4, occupied_cells: 4, occupied: 4,
  free: 0, is_full: true, overfilled: false, consistent: true,
  holds: 2, last_hold: null,
}
const EMPTY_SNAP = {
  cabinet_id: 'CAB-B', known: true, label: '驿站侧柜', site: '北侧驿站',
  capacity: 2, open_occupancies: 1, occupied_cells: 1, occupied: 1,
  free: 1, is_full: false, overfilled: false, consistent: true,
  holds: 0, last_hold: null,
}
const HOLDS = [
  { id: 1, reason: 'cabinet_full', created_at: '2026-11-20T00:00:00Z', event_id: 'E8',
    batch_id: 'B-1', cabinet_id: 'CAB-A', cell_id: null, tracking_no: 'TN1006',
    occupied: 4, capacity: 4, open_occupancies: 4, occupied_cells: 4, free: 0 },
  { id: 2, reason: 'cabinet_full', created_at: '2026-11-20T00:00:00Z', event_id: 'E9',
    batch_id: 'B-1', cabinet_id: 'CAB-A', cell_id: 'CAB-A-02', tracking_no: 'TN1007',
    occupied: 4, capacity: 4, open_occupancies: 4, occupied_cells: 4, free: 0 },
]
const BAY = [
  { id: 'CAB-A', label: '东门柜阵', site: '园区东门', capacity: FULL_SNAP, cells: [
    { id: 'CAB-A-01', code: 'A01', size_code: 'S', status: 'occupied', occupancy: { tracking_no: 'TN1005' } },
    { id: 'CAB-A-02', code: 'A02', size_code: 'M', status: 'occupied', occupancy: { tracking_no: 'TN1006' } },
  ] },
  { id: 'CAB-B', label: '驿站侧柜', site: '北侧驿站', capacity: EMPTY_SNAP, cells: [
    { id: 'CAB-B-01', code: 'B01', size_code: 'M', status: 'occupied', occupancy: null },
  ] },
]

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(api, 'overview').mockResolvedValue({
    cells: 6, occupied: 5, free: 1, open_occupancies: 5,
    full_cabinets: 1, capacity_holds: 2,
  })
  vi.spyOn(api, 'capacity').mockResolvedValue({
    cabinets: [FULL_SNAP, EMPTY_SNAP],
    totals: { capacity: 6, occupied: 5, free: 1, full_cabinets: 1, overfilled_cabinets: 0, inconsistent_cabinets: 0, holds: 2 },
  })
  vi.spyOn(api, 'bay').mockResolvedValue(BAY)
  vi.spyOn(api, 'capacityHolds').mockResolvedValue(HOLDS)
  vi.spyOn(api, 'proofs').mockResolvedValue([])
  vi.spyOn(api, 'occupancies').mockResolvedValue([])
  vi.spyOn(api, 'events').mockResolvedValue([
    { id: 'E8', cabinet_id: 'CAB-A', cell_id: null, event_type: 'drop', event_ts: 't', tracking_no: 'TN1006', channel: 'primary' },
    { id: 'E9', cabinet_id: 'CAB-A', cell_id: 'CAB-A-02', event_type: 'drop', event_ts: 't', tracking_no: 'TN1007', channel: 'primary' },
  ])
})

describe('Bay', () => {
  it('shows per-cabinet occupied/capacity and full marker', async () => {
    const w = mount(Bay)
    await flushPromises()
    expect(w.text()).toContain('4 / 4')
    expect(w.text()).toContain('满柜')
    expect(w.text()).toContain('搁置 2')
    expect(w.text()).toContain('1 / 2')
    expect(w.find('.meter span.full').exists()).toBe(true)
  })
})

describe('Ingest', () => {
  it('tags held events with reason and snapshot', async () => {
    const w = mount(Ingest)
    await flushPromises()
    const rows = w.findAll('tbody tr')
    expect(rows[0].text()).toContain('cabinet_full')
    expect(rows[0].text()).toContain('4/4')
    expect(rows[1].text()).toContain('CAB-A-02')
    expect(rows[1].text()).toContain('cabinet_full')
  })
})

describe('Proofs', () => {
  it('renders capacity verification table with consistency status', async () => {
    const w = mount(Proofs)
    await flushPromises()
    expect(w.text()).toContain('柜级容量核证')
    expect(w.text()).toContain('CAB-A')
    expect(w.text()).toContain('满柜')
    expect(w.text()).toContain('正常')
    expect(w.text()).toContain('满柜 1 · 超容 0')
  })
})

describe('Reclaim', () => {
  it('renders holds with capacity snapshot columns', async () => {
    const w = mount(Reclaim)
    await flushPromises()
    expect(w.text()).toContain('cabinet_full')
    expect(w.text()).toContain('4/4')
    expect(w.text()).toContain('待分配')
    expect(w.text()).toContain('B-1')
  })
})
