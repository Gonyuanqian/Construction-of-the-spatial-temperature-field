<script setup lang="ts">
import { computed } from 'vue'
import type { RegionCatalog, RegionInput } from '../api/regions'
const props = defineProps<{ modelValue: RegionInput; catalog: RegionCatalog | null; disabled?: boolean; archive?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: RegionInput] }>()
const districts = computed(() => props.catalog?.cities.find(c => c.code === props.modelValue.city_code)?.districts ?? [])
function city(event: Event) { emit('update:modelValue', { province_code: '220000', city_code: (event.target as HTMLSelectElement).value }) }
function district(event: Event) { emit('update:modelValue', { province_code: '220000', city_code: props.modelValue.city_code, ...((event.target as HTMLSelectElement).value ? { district_code: (event.target as HTMLSelectElement).value } : {}) }) }
</script>
<template>
  <div class="region-picker">
    <span class="province-label">吉林省</span>
    <label>市（州）<select aria-label="市（州）" :value="modelValue.city_code" :disabled="disabled || !catalog" required @change="city"><option value="">请选择市（州）</option><option v-for="item in catalog?.cities" :key="item.code" :value="item.code">{{ item.name }}</option></select></label>
    <label>区县<select aria-label="区县" :value="modelValue.district_code ?? ''" :disabled="disabled || !modelValue.city_code" @change="district"><option value="">{{ archive ? '全市默认档案' : '未细分区县' }}</option><option v-for="item in districts" :key="item.code" :value="item.code">{{ item.name }}</option></select></label>
  </div>
</template>
<style scoped>
.region-picker { display: flex; align-items: end; gap: 10px; min-width: 0; flex-wrap: wrap; }.province-label { font-size: var(--size-note); color: var(--ink-muted); padding-bottom: 11px; }.region-picker label { display: grid; gap: 5px; font-size: var(--size-note); min-width: 130px; flex: 1; }.region-picker select { min-height: 38px; width: 100%; padding: 7px 9px; border: var(--rule); border-radius: var(--radius); background: var(--card); color: var(--ink); font: inherit; }
</style>
