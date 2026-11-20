<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api.js'
const events = ref([])
const report = ref(null)
const holds = ref([])
async function load() {
  events.value = await api.events()
  holds.value = await api.capacityHolds()
}
async function run() { report.value = await api.ingest(); await load() }
onMounted(load)
function heldEvent(id) {
  return holds.value.find((h) => h.event_id === id)
}
</script>
<template>
  <div>
    <h1>装载</h1>
    <p class="sub">投柜 / 取件事件进入主通道；柜机满容后该柜投柜一律进搁置，不再开新占用。</p>
    <p><button @click="run">跑一批夹具</button></p>
    <div v-if="report" class="panel" style="margin-bottom:1rem">
      <div class="stats" style="margin:0">
        <div class="stat"><b>{{ report.accepted }}</b><span>接受事件</span></div>
        <div class="stat"><b>{{ report.materialized }}</b><span>物化占用</span></div>
        <div class="stat"><b>{{ report.held }}</b><span>满柜搁置</span></div>
        <div class="stat"><b>{{ report.awaiting_allocation }}</b><span>待分配</span></div>
      </div>
      <p class="sub" style="margin:.75rem 0 0">批次 <code>{{ report.batch_id }}</code> · 共 {{ report.total }} 条</p>
    </div>
    <div class="panel" style="overflow:auto">
      <table>
        <thead><tr><th>事件</th><th>类型</th><th>格口</th><th>运单</th><th>时刻</th><th>裁决</th></tr></thead>
        <tbody>
          <tr v-for="e in events" :key="e.id">
            <td><code>{{ e.id }}</code></td>
            <td>{{ e.event_type }}</td>
            <td>{{ e.cell_id || '—' }}</td>
            <td>{{ e.tracking_no || '—' }}</td>
            <td>{{ e.event_ts }}</td>
            <td>
              <span v-if="heldEvent(e.id)" class="tag over">
                搁置 · {{ heldEvent(e.id).reason }}
                <template v-if="heldEvent(e.id).occupied != null">
                  （{{ heldEvent(e.id).occupied }}/{{ heldEvent(e.id).capacity }}）
                </template>
              </span>
              <span v-else-if="e.event_type === 'drop' && !e.cell_id" class="tag">待分配</span>
              <span v-else class="muted">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
