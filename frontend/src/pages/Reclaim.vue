<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api.js'
const rows = ref([])
const q = ref([])
onMounted(async () => {
  rows.value = await api.occupancies()
  q.value = await api.capacityHolds()
})
</script>
<template>
  <div>
    <h1>回收</h1>
    <p class="sub">超时回收空桩待实现；此处展示占用账与容量裁决搁置（含当时 occupied/capacity 快照）。</p>
    <div class="panel">
      <h2 style="margin:0 0 .5rem;font-size:1rem">占用账</h2>
      <table>
        <thead><tr><th>占用</th><th>格口</th><th>运单</th><th>状态</th><th>开启</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td><code>{{ r.id }}</code></td>
            <td>{{ r.cell_id }}</td>
            <td>{{ r.tracking_no }}</td>
            <td>{{ r.status }}</td>
            <td>{{ r.opened_at }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="panel" style="margin-top:1rem">
      <h2 style="margin:0 0 .5rem;font-size:1rem">搁置</h2>
      <p v-if="!q.length" class="sub">暂无搁置。</p>
      <table v-else>
        <thead><tr><th>id</th><th>原因</th><th>柜机</th><th>事件</th><th>格口</th><th>容量快照</th><th>批次</th><th>时刻</th></tr></thead>
        <tbody>
          <tr v-for="item in q" :key="item.id">
            <td>{{ item.id }}</td>
            <td><span class="tag over">{{ item.reason }}</span></td>
            <td>{{ item.cabinet_id }}</td>
            <td><code>{{ item.event_id }}</code></td>
            <td>{{ item.cell_id || '待分配' }}</td>
            <td><code>{{ item.occupied ?? '—' }}/{{ item.capacity ?? '—' }}</code></td>
            <td><code>{{ item.batch_id || '—' }}</code></td>
            <td>{{ item.created_at }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
