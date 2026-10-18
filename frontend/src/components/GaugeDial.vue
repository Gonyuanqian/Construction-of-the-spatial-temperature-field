<script setup lang="ts">
/**
 * 圆环仪表。**通用展示件**：它不认识页⑤，也不认识温度 ——
 * 只收一个 0–1 的比例、一行已经格式化好的读数、一句标签，以及弧的颜色。
 *
 * 比例由**调用者**按载荷的 `vmin` / `vmax` / `mean` 算出来（那一处有一条
 * 注释说明为什么那不是「前端算温度」）；颜色也是调用者用
 * `charts/scale.ts` 的 `valueToColor` 取好的 —— 于是「环」与「色标」
 * 在同一屏上不可能各按一套（规格书 §三 D6 的原话：
 * **环就是一条弯过来的色标**）。
 *
 * ⚠️ `r` 与周长是这一层的**几何常量**，不是数据。
 */
import { computed } from 'vue'

const props = defineProps<{
  /** 0–1。调用者已经夹过范围。 */
  frac: number
  /** 环心里那行读数（已格式化）。 */
  valueText: string
  /** 环下面那行标签。 */
  label: string
  /** 弧的颜色。空串 = 还没数，兜一个主色。 */
  arcColor?: string
  /** 圆环直径（px）。 */
  size?: number
}>()

const R = 34
const CIRC = 2 * Math.PI * R
/** SVG 的 `stroke-dasharray`：先把 `frac` 那一截实上，剩下的空着（虚长 = 周长）。 */
const dash = computed(() => `${(CIRC * props.frac).toFixed(2)} ${CIRC.toFixed(2)}`)
</script>

<template>
  <div class="dial" :style="{ '--dial-size': `${props.size ?? 104}px` }">
    <svg viewBox="0 0 88 88" :width="props.size ?? 104" :height="props.size ?? 104" role="img"
         :aria-label="`${label} ${valueText}`">
      <circle class="track" cx="44" cy="44" :r="R" />
      <!-- ⚠️ 颜色走 `:style` 而不是 `stroke=` 属性：SVG 的表现属性不认
           `var()`，而兜底那一档必须是 `var(--leaf)`（十六进制在这个仓里
           只许出现在 tokens.css 与 charts/scale.ts）。 -->
      <circle class="arc" cx="44" cy="44" :r="R"
              :stroke-dasharray="dash"
              :style="{ stroke: arcColor || 'var(--leaf)' }" />
    </svg>
    <div class="dial-copy" aria-hidden="true">
      <p class="value num">{{ valueText }}</p>
      <p class="label">{{ label }}</p>
    </div>
  </div>
</template>

<style scoped>
.dial { position: relative; width: var(--dial-size); height: var(--dial-size); flex: none; }
.track { fill: none; stroke: var(--steel); stroke-width: 8; }
/* 起点挪到正上方。`transform-origin` 用像素而不是 `center` 百分比：
   `viewBox` 是 88×88，圆心在 44,44 —— 百分比在两个方向一致时也对，
   但写死像素不依赖那一层的换算。 */
.arc {
  fill: none;
  stroke-width: 8;
  stroke-linecap: round;
  transform: rotate(-90deg);
  transform-origin: 44px 44px;
}
.dial-copy {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 2px; text-align: center; pointer-events: none;
}
.value { margin: 0; font-size: var(--size-h3); font-weight: var(--w-strong); }
.label { margin: 0; font-size: var(--size-note); color: var(--ink-muted); }
</style>
