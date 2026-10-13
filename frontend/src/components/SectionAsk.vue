<script setup lang="ts">
/**
 * 断面那一档的「问数」卡：三个坐标框 + 吸附说明 + 一次查询的结果。
 *
 * ⚠️ **判定不在这一层**：吸附走 `scene/hover.ts::snapIndex`（越界回 `null`、
 * 平手取小下标），回答走 `charts/pick.ts::interpretPick` / `pickText` ——
 * 三条都是全前端唯一那处（硬约束 1），由 `LiveView` 调好再把结果传进来。
 * 这一层只管三个输入框与那张表，所以它连 `api/types` 都不用 import。
 */
import { computed, ref } from 'vue'

defineProps<{
  /** 上一次查询的答案；`null` = 还没查过，或者上一次无解。 */
  answer: { where: string; text: string } | null
  /** 上一次查询的错误话；空串 = 没错。 */
  error: string
  /** 这一档能问的范围说明（`LiveView` 用载荷的 `x` / `z` 端点拼好传进来）。 */
  note: string
}>()

const emit = defineEmits<{ query: [q: { x: number; y: number; z: number }] }>()

const x = ref<number | ''>('')
const y = ref<number | ''>('')
const z = ref<number | ''>('')

/**
 * ⚠️ 拿到的值**是 `number | ''`，不是字符串**：`<input type="number">` 上
 * Vue 的 `v-model` 自己会做数字转换（`looseToNumber`），清空时给的是空串。
 * 空串不能当 0（`Number('') === 0`），所以先把它挑出来。
 * 与 `VolumeView.vue` 里那一处同一个形状 —— 那一处不动（页③ 共用），
 * 这一处是它在新组件里的第二份**输入处理**，不是第二份判定。
 */
const num = (v: number | ''): number =>
  typeof v === 'string' ? (v.trim() === '' ? Number.NaN : Number(v)) : v

const parsed = computed(() => {
  const n = [num(x.value), num(y.value), num(z.value)]
  return n.every((v) => Number.isFinite(v)) ? { x: n[0]!, y: n[1]!, z: n[2]! } : null
})

function run(): void {
  if (parsed.value) emit('query', parsed.value)
}
</script>

<template>
  <div class="ask">
    <div class="row">
      <label>x <input v-model="x" type="number" step="0.01"></label>
      <label>y <input v-model="y" type="number" step="0.01"></label>
      <label>z <input v-model="z" type="number" step="0.01"></label>
    </div>
    <p class="note">
      三个断面落在固定的棚位上，格点也不是连续的。查询<strong>吸附到最近的格点</strong>，
      不插值；吸附后的坐标会在下面写出来。{{ note }}
    </p>
    <button type="button" :disabled="!parsed" @click="run">查询</button>
    <p v-if="error" role="alert" class="alert">{{ error }}</p>
    <table v-if="answer">
      <tbody>
        <tr><th>位置</th><td class="num">{{ answer.where }}</td></tr>
        <tr><th>回答</th><td>{{ answer.text }}</td></tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
/* ⚠️ 这一段是从 `VolumeView.vue` 的「查一个坐标」那一块**照抄形状**的
   （页③ 那一份不动，因为那是共用件、改了页③ 就变）。样式不共用：
   两处的宽度约束不一样（这一处在 390px 的右栏里，那一处在 18rem 的栏里）。
   ⚠️ 这个文件里**不许**再写一份分段控件的样式：`guards.test.ts` 那条焦点环守卫
   是把所有**定义了分段控件样式**的 `.vue` 扫出来、再与三个文件名对账；
   第四个名字当场红，而红的是 `guards.test.ts`，指的不是这里。 */
.row { display: flex; gap: var(--gap-s); align-items: center; flex-wrap: wrap; }
.row label { display: inline-flex; align-items: center; gap: 4px; font-size: var(--size-note); }
input[type='number'] { width: 6.5em; font: inherit; }
.alert { color: var(--leaf); border-left: 3px solid var(--leaf); padding-left: var(--gap-s); }
</style>
