<script setup lang="ts">
/**
 * 线框图标。**名字进、形状出** —— 形状表在 `design/icons.ts`。
 *
 * 上色一律 `currentColor`：默认 / 悬停 / 选中三态的亮暗由**文字颜色**带着走，
 * 图标自己不认识颜色（十六进制色在这个仓里只许出现在 `tokens.css` 与
 * `charts/scale.ts`，`guards.test.ts` 钉着）。
 *
 * 大小由调用方给：`--icon-size`（默认 18px）。写成一个变量而不是固定值，
 * 是因为同一枚图标在标题条上要跟 30px 的标题站在一起、在左栏里只需跟 15px
 * 的菜单字站在一起 —— 两处差着一档，而形状只有一份。
 */
import { ICON_PATHS, type IconName } from '../design/icons'

defineProps<{ name: IconName }>()
</script>

<template>
  <svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"
       fill="none" stroke="currentColor" stroke-width="1.6"
       stroke-linecap="round" stroke-linejoin="round">
    <path :d="ICON_PATHS[name]" />
  </svg>
</template>

<style scoped>
.icon {
  display: block;
  width: var(--icon-size, 18px);
  height: var(--icon-size, 18px);
  /* 图标在 flex 行里不许被压扁：左栏那一行是「图标 + 文字」，
     文字一长，默认的 `flex-shrink: 1` 会先把图标挤成一条竖线。 */
  flex: none;
}
</style>
