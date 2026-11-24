<script setup lang="ts">
import type {Activity} from '../api/assistant'
defineProps<{activities:readonly Activity[];running:boolean}>()
const labels:Record<string,string>={running:'进行中',completed:'已完成',failed:'未完成',interrupted:'已中断',cancelled:'已取消'}
</script>
<template>
  <details v-if="activities.length" class="execution-activity" :open="running">
    <summary>执行记录 · {{ activities.length }} 项</summary>
    <ol><li v-for="activity in activities" :key="`${activity.kind}:${activity.id}`">
      <span>{{ activity.kind==='tool' ? '工具' : '模型' }} · {{ activity.label }}</span>
      <small :class="activity.status">{{ labels[activity.status] }}<template v-if="activity.evidence_count!==undefined"> · {{ activity.evidence_count }} 条依据</template></small>
    </li></ol>
  </details>
</template>
<style scoped>
.execution-activity{font-size:12px;color:#8791a3;margin:0 8px 18px;padding:0 12px;border-left:2px solid #e4e9fb}
summary{cursor:pointer;width:fit-content}ol{list-style:none;padding:0;margin:10px 0}li{display:flex;flex-wrap:wrap;gap:8px;justify-content:space-between;padding:3px 0}small{color:#8d98aa}.running{color:#4d6bfe}.failed,.interrupted{color:#b27b57}
</style>
