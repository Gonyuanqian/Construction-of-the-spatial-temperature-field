<script setup lang="ts">
/**
 * 标题条。**跨模式、跨页面常驻** —— 它是系统的身份，不是某一页的页眉。
 * 切页面时闪一下、或只在某些页出现，就退化成了页眉（spec 2026-10-04 §1.3）。
 *
 * 2026-10-06（spec §5.2）三处改动：
 * ① 整条 `--leaf` 底、`--paper` 字 —— 它是这台界面的**铭牌**，
 *    也是全页唯一一条叶子色面（§三 第 3 条：管的是形状，不是面）；
 * ② 标题**居中**；
 * ③ 后端状态从侧栏底部搬到这里。
 *
 * ⚠️ 居中走 `grid-template-columns: 1fr auto 1fr`，标题占中格 ——
 * **几何居中**。用 flex 居中会被右格里的状态推偏。
 * 中格必须是 `auto`：写成 `1fr` 的话标题会随状态宽度漂。
 *
 * 状态为什么值得占这块地方：一台机器上可能同时跑着好几个后端，
 * 验收对盘时第一个要问的就是「你看的这个数是哪个后端给的」
 * （spec 2026-10-03 §5.1）。搬上来的第二个理由更硬：`/live` 收起导航，
 * 导航不在时原来那一行也跟着没了 —— 实时那一屏恰恰最需要确认后端是哪一个。
 */
import { onMounted, watch } from 'vue'

import { getJson } from '../api/client'
import { useAsync } from '../composables/useAsync'
import { MODELS, SYSTEM_TITLE } from '../design/copy'

const props = withDefaults(defineProps<{ demo?: boolean }>(), { demo: false })
const health = useAsync(() => getJson<{ status: string; version: string }>('/api/health'))

onMounted(() => { if (!props.demo) void health.run() })
watch(() => props.demo, (demo) => { if (!demo) void health.run() })
</script>

<template>
  <header class="titlebar">
    <h1>{{ SYSTEM_TITLE }}</h1>
    <div class="right">
      <!-- 模型库的入口。**不进左导航**：那一列有测试钉着「<a> 的数量与
           次序精确等于已开放项」（App.test.ts），而用户 2026-10-08 指定的
           位置就是标题条右边、紧挨着「后端：ok」。 -->
      <RouterLink class="to-models" to="/models"
                  :title="MODELS.entry" :aria-label="MODELS.entry">
        <!-- 档案盒。内联 SVG 而不是图标字体 / 图片：它要跟着 `.backend`
             那行字一起对齐，而且 **`currentColor` 上色** —— 十六进制色
             在这个仓里只许出现在 tokens.css 与 charts/scale.ts。 -->
        <svg viewBox="0 0 16 16" width="16" height="16"
             aria-hidden="true" focusable="false" fill="none"
             stroke="currentColor" stroke-width="1.4" stroke-linejoin="round">
          <path d="M2 3.5h12v2.5H2z" />
          <path d="M3 6.5h10v7H3z" />
          <path d="M6.5 9.2h3" />
        </svg>
      </RouterLink>
      <p class="backend">
        <template v-if="demo">演示预览：模拟数据</template>
        <template v-else-if="health.error.value">后端：{{ health.error.value }}</template>
        <template v-else-if="health.data.value">
          后端：{{ health.data.value.status }}，库版本
          <span class="num">{{ health.data.value.version }}</span>
        </template>
        <template v-else>后端：检查中</template>
      </p>
    </div>
  </header>
</template>

<style scoped>
.titlebar {
  background: var(--leaf);
  /* 2026-10-06 用户裁定：原来 8px 的上下内边距配上 17px 的标题，整条读起来
     像一条细带子，压不住整页。加高到 `--gap-m`，标题走 `--size-title`（26px）。 */
  padding: var(--gap-m) var(--gap-l);
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: baseline;
  column-gap: var(--gap-m);
}
.titlebar h1 {
  grid-column: 2;
  color: var(--paper);
  font-weight: var(--w-title);
  letter-spacing: 0.01em;
}
.right {
  grid-column: 3;
  justify-self: end;
  display: flex;
  align-items: center;
  gap: var(--gap-s);
  /* ⚠️ `align-self: center` 是承重的，不是顺手加的。外面那条栅格是
     `align-items: baseline`，而 `.right` 现在是个 flex 盒子 —— 它的基线由
     **第一个 flex 子项**（那个 `<a>`，里面只有一个 `<svg>`）合成，也就是
     图标的**下边缘**。不写这一句，图标下沿会跟 26px 的标题基线对齐，
     整簇往右下坠。 */
  align-self: center;
}
.backend {
  margin: 0;
  color: var(--steel);
  font-size: var(--size-label);
}
.to-models {
  color: var(--paper);
  display: inline-flex;
  align-items: center;
  /* 触摸目标：图标只有 16px，四周补出可点区域 */
  padding: 2px;
  border-radius: var(--radius);
}
.to-models:hover { color: var(--steel); }
</style>
