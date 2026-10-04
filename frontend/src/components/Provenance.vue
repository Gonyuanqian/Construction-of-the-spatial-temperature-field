<script setup lang="ts">
/**
 * 出处标记 —— 每个数字旁边都带三态之一（spec §七 主张 2）。
 *
 * 这个系统最不寻常的地方不是它算什么，是它**拒绝报数**（拱外不报、
 * z > 1.10 m 不报、任意点只有三种回答）。那就把「这个数是从哪来的」
 * 升成贯穿全站的一等公民，而不是一句脚注。
 */
import { computed } from 'vue'

const props = defineProps<{ kind: 'pack' | 'live' | 'test' }>()

const WHY: Record<typeof props.kind, string> = {
  pack: '随标定包（标定当时算好、写在包里的数）',
  live: '现场重算（这次请求现算出来的数）',
  test: '只有验收测试守（界面上不校验，靠后端测试钉住的数）',
}

const text = computed(() => WHY[props.kind])
</script>

<template>
  <span class="prov" :title="text">{{ text }}</span>
</template>

<style scoped>
.prov {
  color: var(--ink-muted);
  font-size: var(--size-note);
  white-space: nowrap;
}
</style>
