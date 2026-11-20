<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api.js'
const proofs = ref([])
const capacity = ref([])
const totals = ref(null)
onMounted(async () => {
  proofs.value = await api.proofs()
  const cap = await api.capacity()
  capacity.value = cap.cabinets
  totals.value = cap.totals
})
</script>
<template>
  <div>
    <h1>核账</h1>
    <p class="sub">柜级容量核证（只读）+ 占用核证列表；容量与占用账对不上会在此显红。</p>
    <div class="panel" style="margin-bottom:1rem">
      <h2 style="margin:0 0 .5rem;font-size:1rem">柜级容量核证</h2>
      <table>
        <thead>
          <tr><th>柜机</th><th>occupied</th><th>capacity</th><th>free</th><th>开放占用</th><th>占用格</th><th>状态</th><th>搁置</th></tr>
        </thead>
        <tbody>
          <tr v-for="c in capacity" :key="c.cabinet_id">
            <td><code>{{ c.cabinet_id }}</code></td>
            <td><b>{{ c.occupied }}</b></td>
            <td>{{ c.capacity }}</td>
            <td>{{ c.free }}</td>
            <td>{{ c.open_occupancies }}</td>
            <td>{{ c.occupied_cells }}</td>
            <td>
              <span v-if="c.overfilled" class="tag over">超容</span>
              <span v-else-if="!c.consistent" class="tag over">账态不一致</span>
              <span v-else-if="c.is_full" class="tag over">满柜</span>
              <span v-else class="tag">正常</span>
            </td>
            <td>{{ c.holds }}</td>
          </tr>
        </tbody>
        <tfoot v-if="totals">
          <tr>
            <th>合计</th><th>{{ totals.occupied }}</th><th>{{ totals.capacity }}</th><th>{{ totals.free }}</th>
            <th colspan="2"></th>
            <th>满柜 {{ totals.full_cabinets }} · 超容 {{ totals.overfilled_cabinets }}</th>
            <th>{{ totals.holds }}</th>
          </tr>
        </tfoot>
      </table>
    </div>
    <div class="panel" style="overflow:auto">
      <h2 style="margin:0 0 .5rem;font-size:1rem">占用核证</h2>
      <table>
        <thead><tr><th>占用</th><th>格口</th><th>运单</th><th>开启</th><th>事件</th></tr></thead>
        <tbody>
          <tr v-for="p in proofs" :key="p.id">
            <td><code>{{ p.occupancy_id }}</code></td>
            <td>{{ p.cell_id }}</td>
            <td>{{ p.tracking_no }}</td>
            <td>{{ p.opened_at }}</td>
            <td><code>{{ p.event_ids_json }}</code></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
