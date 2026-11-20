<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api.js'
const overview = ref(null)
const bay = ref([])
const capacity = ref(null)
onMounted(async () => {
  overview.value = await api.overview()
  capacity.value = await api.capacity()
  bay.value = await api.bay()
})
function capOf(id) {
  return capacity.value?.cabinets.find((c) => c.cabinet_id === id)
}
</script>
<template>
  <div>
    <h1>格阵</h1>
    <p class="sub">柜机格口占用态一眼可核；空闲 / 占用由装载事件物化，满柜后投柜进搁置。</p>
    <div class="stats" v-if="overview">
      <div class="stat"><b>{{ overview.cells }}</b><span>格口</span></div>
      <div class="stat"><b>{{ overview.occupied }}</b><span>占用</span></div>
      <div class="stat"><b>{{ overview.free }}</b><span>空闲</span></div>
      <div class="stat"><b>{{ overview.open_occupancies }}</b><span>开放占用账</span></div>
      <div class="stat"><b>{{ overview.full_cabinets ?? 0 }}</b><span>满柜柜机</span></div>
      <div class="stat"><b>{{ overview.capacity_holds ?? 0 }}</b><span>满柜搁置</span></div>
    </div>
    <section v-for="cab in bay" :key="cab.id" class="cabinet panel">
      <h2>
        {{ cab.label }}
        <small>{{ cab.id }} · {{ cab.site }}</small>
        <span class="cap" :class="{ full: capOf(cab.id)?.is_full }" v-if="capOf(cab.id)">
          {{ capOf(cab.id).occupied }} / {{ capOf(cab.id).capacity }}
          <template v-if="capOf(cab.id).is_full">· 满柜</template>
          <template v-if="capOf(cab.id).holds"> · 搁置 {{ capOf(cab.id).holds }}</template>
        </span>
      </h2>
      <div class="meter" v-if="capOf(cab.id)">
        <span
          :style="{ width: `${capOf(cab.id).capacity ? (capOf(cab.id).occupied / capOf(cab.id).capacity) * 100 : 0}%` }"
          :class="{ full: capOf(cab.id).is_full, over: capOf(cab.id).overfilled }"
        />
      </div>
      <div class="grid">
        <div v-for="cell in cab.cells" :key="cell.id" class="cell" :class="cell.status">
          <div>
            <div class="code">{{ cell.code }}</div>
            <div class="meta">{{ cell.size_code }} · {{ cell.status === 'occupied' ? '占用' : '空闲' }}</div>
          </div>
          <div class="meta" v-if="cell.status === 'occupied' && cell.occupancy?.tracking_no">{{ cell.occupancy.tracking_no }}</div>
          <span class="dot" />
        </div>
      </div>
    </section>
  </div>
</template>
