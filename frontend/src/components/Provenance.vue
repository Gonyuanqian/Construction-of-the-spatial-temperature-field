<script setup lang="ts">
/**
 * 出处标记 —— 每个数字旁边都带三态之一（spec §七 主张 2）。
 *
 * 这个系统最不寻常的地方不是它算什么，是它**拒绝报数**（拱外不报、
 * z > 1.10 m 不报、任意点只有三种回答）。那就把「这个数是从哪来的」
 * 升成贯穿全站的一等公民，而不是一句脚注。
 *
 * ⚠️ 可见文本是 copy.ts 里 `PROV` 的一个字 —— 完整那句在 `title` 上。
 * 改这里以前它是整句，整页因此像注释密布的文档（spec §一 成因 6）。
 *
 * ⚠️ 三态说的是「这个数在管线里从哪来」；`charts/pick.ts` 那套
 * （实测 / 重建 / 无定义）说的是「这一格场有没有数」。两个轴，不许合并。
 */
import { computed } from 'vue'

import { PROV, type ProvKind } from '../design/copy'

const props = defineProps<{ kind: ProvKind }>()

const mark = computed(() => PROV[props.kind].mark)
const why = computed(() => PROV[props.kind].why)
</script>

<template>
  <span class="prov" :title="why">{{ mark }}</span>
</template>

<style scoped>
.prov {
  display: inline-block;
  padding: 0 4px;
  border: 1px solid var(--steel);
  border-radius: var(--radius);
  color: var(--ink-muted);
  font-size: var(--size-label);
  line-height: 1.5;
}
</style>
