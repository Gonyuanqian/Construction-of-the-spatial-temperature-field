<script setup lang="ts">
import Card from './Card.vue'
import Icon from './Icon.vue'
import { useRetainedTeleport } from '../composables/useRetainedTeleport'

defineProps<{ message: string }>()
const { target, disabled } = useRetainedTeleport('#shell-side')
const selectionRows = [
  ['时刻', '暂无'], ['位置', '待选点'], ['回答', '暂无构场结果'],
]
const queryRows = [['时刻', '暂无'], ['位置', '待查询'], ['回答', '暂无构场结果']]
</script>

<template>
  <Card class="empty-stage" aria-label="棚体三维温度场占位">
    <div class="empty-stage-head">
      <h3><Icon name="cube" />棚体三维温度场</h3>
      <span class="note">待构场</span>
      <div class="empty-modes"><button disabled>立体态</button><button disabled>切面态</button></div>
    </div>
    <div class="empty-canvas" role="status">
      <Icon name="cube" />
      <strong>等待构建温度场</strong>
      <p class="note">{{ message }}</p>
    </div>
    <div class="empty-scale" aria-label="温度色标暂无数据">
      <span>温度 / °C</span><span>暂无</span><i /><span>暂无</span>
    </div>
  </Card>

  <Teleport :to="target" :disabled="disabled">
    <Card class="empty-query">
      <h3><Icon name="search" />三维信息查询</h3>
      <table aria-label="画布选点读数">
        <tbody><tr v-for="row in selectionRows" :key="row[0]"><th>{{ row[0] }}</th><td>{{ row[1] }}</td></tr></tbody>
      </table>
      <fieldset disabled class="empty-query-input">
        <legend>查一个坐标</legend>
        <div class="query-inputs">
          <label v-for="axis in ['x', 'y', 'z']" :key="axis">{{ axis }} <input type="number" step="0.01" disabled></label>
          <button type="button" disabled>查询</button>
        </div>
      </fieldset>
      <p class="note">构场完成后可选点或输入坐标查询温度。</p>
      <table aria-label="坐标查询结果">
        <tbody><tr v-for="row in queryRows" :key="row[0]"><th>{{ row[0] }}</th><td>{{ row[1] }}</td></tr></tbody>
      </table>
    </Card>
  </Teleport>
</template>

<style scoped>
.empty-stage { position: relative; flex: 1 1 auto; min-height: 260px; display: flex; flex-direction: column; padding-right: 80px; border: 1px solid var(--interact); }
.empty-stage-head { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; padding-bottom: 12px; border-bottom: var(--rule); }
h3 { display: flex; align-items: center; gap: 8px; }
h3 :deep(.icon) { color: var(--edge); --icon-size: 25px; }
.empty-modes { display: flex; gap: 4px; margin-left: auto; }
.empty-modes button { font-size: var(--size-note); padding: 4px 12px; }
.empty-canvas { flex: 1 1 auto; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 32px 16px; text-align: center; background-image: linear-gradient(var(--steel) 1px, transparent 1px), linear-gradient(90deg, var(--steel) 1px, transparent 1px); background-size: 42px 42px; }
.empty-canvas :deep(.icon) { --icon-size: 64px; color: var(--ink-muted); opacity: 0.6; }
.empty-canvas strong { font-size: var(--size-h3); color: var(--ink-muted); }
.empty-canvas p { max-width: 32em; margin: 0; }
.empty-scale { position: absolute; right: 12px; top: 18px; bottom: 22px; width: 50px; display: flex; flex-direction: column; align-items: center; gap: 10px; color: var(--ink-muted); font-size: var(--size-note); }
.empty-scale i { width: 10px; flex: 1; border: var(--rule); border-radius: 4px; background: var(--card-2); }
.empty-query { flex: 1 0 auto; }
.empty-query h3 { padding-bottom: 14px; margin-bottom: 14px; border-bottom: 1px solid var(--interact); }
.empty-query table { width: 100%; table-layout: fixed; }
.empty-query th { width: 52px; padding: 12px 0; }
.empty-query td { color: var(--ink-muted); padding: 12px 0; overflow-wrap: anywhere; }
.empty-query-input { border: 0; padding: 0; margin: 28px 0 12px; min-width: 0; }
.empty-query-input legend { font-weight: var(--w-strong); margin-bottom: 10px; }
.query-inputs { display: flex; gap: 8px; align-items: center; }
.query-inputs label { display: flex; min-width: 0; align-items: center; gap: 4px; }
.query-inputs input { min-width: 0; width: 100%; }
.query-inputs button { flex: none; }
</style>
