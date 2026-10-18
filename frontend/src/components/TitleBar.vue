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

import { computed, onMounted, onUnmounted, ref, watchEffect } from 'vue'
import { useRoute } from 'vue-router'

import { getJson } from '../api/client'
import { useAsync } from '../composables/useAsync'
import { MODELS, SYSTEM_TITLE } from '../design/copy'
import { fmtClock } from '../design/format'
import Icon from './Icon.vue'

const health = useAsync(() => getJson<{ status: string; version: string }>('/api/health'))

/**
 * ⚠️ 这一句是**执行时补上的**，计划的替换稿里没有它：`useAsync` **不自己跑**
 * （它的 `run()` 自带一条防串号的 `seq` 守卫，所以发起权必须在调用方），
 * 少了这一句 `health.data.value` 永远是 `null` —— 那枚 `.ok` 点永不出现，
 * 而既有的「库版本 0.1.0」「后端没起」两条也会跟着红。
 */
onMounted(() => void health.run())

const route = useRoute()
const isLive = computed(() => route.path.startsWith('/live'))

/**
 * 前后端连上没有 —— 这一条状态线要说的事（2026-10-16 用户裁定：
 * 「这个状态应该以前后端服务有没有成功连接上来判断」）。
 *
 * ⚠️ 判据是 `GET /api/health` **能不能成功返回**，不是它返回了什么；
 * 用户要求里的「后端连接状态」与「数据服务运行状态」就是这一件事的两种说法，
 * 合**一条**（当场裁定 R2）。
 * `useAsync` 把「没回来」与「回来了但是错的」分得很清楚：`data` 与 `error`
 * 互斥，两个都空就是还在路上 —— 三态正好被这三个条件穷尽。
 * ⚠️ 这一档**只有实时那一屏**用（模板里的 `v-if="isLive"`）。
 */
const state = computed(() => (health.error.value ? 'bad' : health.data.value ? 'ok' : 'wait'))
/**
 * ⚠️ 这里必须是 `||`，**不能**写成 `??` —— 写错过一次，测试当场红。
 * `useAsync` 的 `error` 初值是**空串**，不是 `null`：`'' ?? x` 落穿不了，
 * 于是接上了也印出一句空白，而那行字看着像「还没轮到它渲染」。
 */
const statusText = computed(() =>
  health.error.value || (health.data.value ? '前后端已连接' : '检查中'))

/**
 * 本机挂钟（2026-10-12 用户裁定「顶栏可以放当前时间，顶栏的当前时间为本机的时间」）。
 *
 * ⚠️ **它与概览三格里的「本帧时刻」是两件事**，这正是它成立的理由：
 *   顶栏这一枚说的是「现在几点」，来自 `new Date()`，**不会倒退**；
 *   概览那一枚说的是「手上这一帧的数据时刻」，来自后端的 `cursor` ——
 *   帧历史在内存里，服务一重启就回到第 0 帧。
 * 所以它**不参与任何构场逻辑**：这一屏真正的时间轴永远来自服务端。
 *
 * 每一秒重算一次，屏上每分钟跳一格（`fmtClock` 只到分钟）——
 * 一秒一跳是为了让分钟那一位在整分上翻，而不是慢一个周期才翻。
 * ⚠️ 只在实时那一屏上开定时器：训练侧那四页一个像素都不该为它重渲染。
 */
const now = ref(new Date())
let timer: ReturnType<typeof setInterval> | undefined

watchEffect(() => {
  if (timer) { clearInterval(timer); timer = undefined }
  if (isLive.value) timer = setInterval(() => { now.value = new Date() }, 1000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<template>
  <header class="titlebar" :class="{ live: isLive }">
    <!-- 顶部边缘那道折角（用户第一部分要求的「低调的折线、切角、几何线条」）。
         ⚠️ 挂 `v-if="isLive"`：它是这一屏的装饰，训练侧那四页不该多出它。
         `preserveAspectRatio="none"` 让它跟着页宽拉伸，而
         `vector-effect="non-scaling-stroke"` 把描边钉死在 1px —— 少了这一句，
         宽屏上那条线会被横向拉成一根粗杠。 -->
    <svg v-if="isLive" class="deco" viewBox="0 0 100 12" preserveAspectRatio="none"
         aria-hidden="true" focusable="false">
      <polyline points="0,11 12,11 22,1 78,1 88,11 100,11"
                fill="none" stroke="currentColor" stroke-width="1"
                vector-effect="non-scaling-stroke" />
    </svg>
    <!-- 图标 + 标题包成一格。⚠️ 新加的只是这层壳：浅色档与训练侧那四页
         里，它占的仍是原来标题占的那一格（见样式里的 `.brand`）。 -->
    <div class="brand">
      <Icon v-if="isLive" name="leaf" class="leaf" />
      <h1>{{ SYSTEM_TITLE }}</h1>
    </div>
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
      <!-- 本机挂钟（2026-10-12）。⚠️ **与概览三格里的「本帧时刻」是两件事**：
           这一枚是「现在几点」、不会倒退；那一枚是「手上这一帧的数据时刻」、
           重启就回到第 0 帧。各自带标签，不合并。 -->
      <p v-if="isLive" class="clock">
        <span class="clock-label">本机时间</span>
        <span class="num">{{ fmtClock(now) }}</span>
      </p>
      <!-- 状态：**一枚点 + 一句话**，一块而不是两块（裁定 R2）。参考图右上角
           就是这个形状。⚠️ 只在实时那一屏上换成它；训练侧那四页仍是
           「后端：ok，库版本 0.1.0」—— 那四页的浅色档一个字节都没动。 -->
      <p v-if="isLive" class="status" :class="state">
        <span class="dot" aria-hidden="true" />
        <span>{{ statusText }}</span>
      </p>
      <p v-else class="backend">
        <template v-if="health.error.value">后端：{{ health.error.value }}</template>
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
  /* 面走 `--header`，不走 `--leaf`（2026-10-12）：实时那一档的面是深蓝、
     强调色是青，两者在这一轮之前是同一个令牌。浅色档 `--header` 取 `var(--leaf)`，
     页①②③④ 像素不变。 */
  background: var(--header);
  /* 76px 是实时那一档的取值（`--titlebar-h`）；浅色档是 `auto`，即现状。
     ⚠️ `min-height` 而不是 `height`：窄屏上标题折行时写死高度会把字切掉。 */
  min-height: var(--titlebar-h);
  /* 2026-10-06 用户裁定：原来 8px 的上下内边距配上 17px 的标题，整条读起来
     像一条细带子，压不住整页。加高到 `--gap-m`，标题走 `--size-title`（26px）。 */
  padding: var(--gap-m) var(--gap-l);
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: baseline;
  column-gap: var(--gap-m);
}
/* 图标 + 标题那一格。⚠️ 包这一层壳是为了给实时那一屏塞进那枚叶片，
   而它在**浅色档与训练侧四页上必须原地不动** —— 占的仍是原来标题占的中格。
   所以栅格列号从 `h1` 挪到了这里：`h1` 现在不再是一个栅格项。 */
.brand { grid-column: 2; }
.titlebar h1 {
  color: var(--on-face);
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
  color: var(--face-dim);
  font-size: var(--size-label);
}
.to-models {
  color: var(--on-face);
  display: inline-flex;
  align-items: center;
  /* 触摸目标：图标只有 16px，四周补出可点区域 */
  padding: 2px;
  border-radius: var(--radius);
}
.to-models:hover { color: var(--face-dim); }

/* 本机挂钟。次要文字那一档 —— 它是给「现在」对表用的，不是数据。 */
.clock {
  margin: 0;
  display: inline-flex;
  align-items: baseline;
  gap: var(--gap-s);
  color: var(--face-dim);
  font-size: var(--size-label);
}
.clock-label { font-size: var(--size-note); }
/* ── 页⑤ 精修（2026-10-16）：标题条的新面 ───────────────────────────
   新样式**一律**挂在 `.titlebar.live` 底下。用户裁的是「只需要改动实时模式
   的页面」，而标题条是全站共享的 —— 漏挂一处，页①②③④ 就跟着动了，
   而屏上不一定看得出来（浅色档的强调色本来就是青）。 */
.titlebar.live {
  /* 底部那条青线与顶部那道折角都贴着这一条的边放，所以这里要是定位原点。 */
  position: relative;
  /* 参考图版式：图标 + 标题占左，时间与状态占右。
     ⚠️ 浅色档仍是 `1fr auto 1fr` 的**中置铭牌**（2026-10-06 用户裁定），
     一个字符都不改。 */
  grid-template-columns: 1fr auto;
  align-items: center;
}
/* ⚠️ 底格右边那一簇在浅色档占的是第 3 格；这里只有两格，
   不把它挪回来就会**另开一个隐式列**，把它们顶出栅格。 */
.titlebar.live .right { grid-column: 2; }

/* 底部那条细青线（用户第一部分要求的「细青色发光分隔线」）。
   ⚠️ 用一条 1px 的伪元素，不用 `border-bottom`：border 上写不出「线只有
   1px、光却有 8px」这件事，而这条线的**读法**正是「一道亮着的边」。 */
.titlebar.live::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 1px;
  background: var(--edge);
  /* 发光那一档是分过的：`--glow-edge` 的半径只有 8px，因为压着光的是
     一条 1px 高的线 —— 半径一大，光就糊开、线反而看不见了。 */
  box-shadow: var(--glow-edge);
  /* 压到 75%：满亮度的青线＋一层光会抢标题的读数，而它只是条分隔线。 */
  opacity: 0.75;
  pointer-events: none;
}

/* 顶部那道折角。⚠️ 折角（`22,1` 那一段斜线）才是「切角」这件事本身；
   平的那两段是它的起讫，少了就成了两根浮空的斜杠。
   `height` 只有 12px、透明度三成半：装饰要待在边缘，不跟标题抢地方。 */
.titlebar.live .deco {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 12px;
  color: var(--edge);
  opacity: 0.35;
  pointer-events: none;
}

.titlebar.live .brand {
  grid-column: 1;
  justify-self: start;
  display: flex;
  align-items: center;
  gap: var(--gap-m);
  /* 窄屏上标题折行时不许把叶片挤扁（`Icon.vue` 里那颗图标自带 `flex: none`，
     这一句管的是这一格自己别把父格撑破）。 */
  min-width: 0;
}
/* 标题左边那一枚叶片。28px 是配 30px 的标题量的：再小就只剩一个点。 */
.titlebar.live .brand .leaf {
  --icon-size: 28px;
  color: var(--edge);
}
.titlebar.live h1 {
  /* 参考图给的是 28–32px（裁定 R5 暂定 30）。
     ⚠️ **不写进 `--size-title`**：那个名字在浅色档是 26px，动它就是四页一起动。 */
  font-size: 30px;
  /* 「浅蓝白」是用户对标题字色的原话。`--on-face` 是**纯白**，读不出那层蓝 ——
     所以这一档另起 `--title-ink`。
     ⚠️ 这里本来顺手把 `--on-face` 的色号写在括号里，结果被 `guards.test.ts`
     「没有 .vue 文件写死十六进制色值」当场逮住：那条守卫扫的是**源码文本**，
     注释里的一样的算。 */
  color: var(--title-ink);
}

/* 右上角那一簇状态。与 `.clock`（本机时间）同一档字号。 */
.titlebar.live .status {
  margin: 0;
  display: inline-flex;
  align-items: center;
  gap: var(--gap-s);
  color: var(--face-dim);
  font-size: var(--size-label);
}
/* 那枚点。**接上了才是实心的绿**；「检查中」与「连不上」都是空心圈 ——
   两者的差别写在旁边那行字里（连不上时写的是后端的原话，不是一句「异常」）。
   ⚠️ 不为「连不上」另开一个红色的令牌：那要多一个颜色名、要动「新令牌在
   浅色档一律取等值」那条纪律，而信息一个字都没多。 */
.titlebar.live .status .dot {
  width: 7px;
  height: 7px;
  border: 1px solid var(--face-dim);
  border-radius: 50%;
  flex: none;
}
.titlebar.live .status.ok .dot {
  background: var(--ok);
  border-color: var(--ok);
}
</style>
