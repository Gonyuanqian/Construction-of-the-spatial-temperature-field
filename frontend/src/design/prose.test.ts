/// <reference types="node" />
// @vitest-environment node
/**
 * spec §十二.11 点名要的那条结构测试：
 * **「四页的 `<section>` 里不存在紧邻主图的裸 `<p class="note">`」**。
 *
 * 它是本次重做的**判据本身**（§五.3：「正文里不再有直接铺在主图前后的
 * `<p class="note">`」）。只靠人工看四页容易漏 —— 页③ 的主图卡片里就还留着
 * 「正在取场…」这类句子，而那是**状态**，不是散文；一条不区分二者的测试
 * 要么写不出来、要么把加载提示也判成违规。所以先把分界线写进标记里：
 *
 *   - 折进 `details.why`     → 口径（§八 说的「散文的归处」）
 *   - 落在 `fieldset.rail-box` → 左栏控件自己的说明（chrome，不是正文）
 *   - 带 `state`             → **此刻的状态**：加载 / 空 / 错误 / 提示
 *   - 带 `reading`           → 这一帧、这一点的**读数**（数字为主，不是句子）
 *   - 带 `data-grading`      → 分级那句（§6.2 页⑤ 与 §十二.7 明文要求它在屏上）
 *
 * 剩下的就是散文，而散文只许待在 `details.why` 里。
 *
 * ⚠️ **这条量的是模板源码，不是渲染结果**，理由与 `guards.test.ts` 那几条
 * 一样：要判的性质是「这句被写在了哪里」，源码文本量得到，而且不依赖四份
 * 各不相同的取数夹具。**它够不着什么**也说清楚：只扫下面 `SCANNED` 那份清单
 * 里的文件。`scene/VolumeView.vue`、`scene/VolumeScene.vue` 这类**组件**不在
 * 此列（§十二.11 说的是「四页的 `<section>`」）。三维那一块的两句口径因此不在
 * 这里兜着 —— 见台账里那条裁定。
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SRC = fileURLToPath(new URL('..', import.meta.url))
  .replaceAll('\\', '/').replace(/\/+$/, '')

/**
 * 扫哪些文件。⚠️ 2026-10-12 之前只扫四个 view —— 页⑤ 重做拆出来的那几块
 * 落在它射程之外，新写一句散文进去没人拦。这是个**真的盲区**，
 * 不是「组件不用守」：`components/OverviewStrip.vue` 就在 `<section>` 渲染路径上。
 *
 * `mustHave` 是那条「这一页真的还有 p.note 可查」的防空转断言。
 * ⚠️ 它只对**页面**成立：组件里有的是纯控件与读数，一句 `p.note` 都没有是正常的。
 *
 * ⚠️ 这条守卫**够不着**两处，说清楚：① `p.sub` 这类换个类名的写法
 *   （`OverviewStrip` 的副文案就是）；② `scene/VolumeView.vue` 这种大组件 ——
 *   它不在这一份清单里，理由是它的 `p.note` 全都落在 `fieldset.rail-box` 内
 *   或带 `state`，而把它加进来会让那条防空转断言变成一句修辞。
 */
const SCANNED: readonly { rel: string; mustHave: boolean }[] = [
  { rel: 'views/DataView.vue', mustHave: true },
  { rel: 'views/TrainView.vue', mustHave: true },
  { rel: 'views/FieldView.vue', mustHave: true },
  { rel: 'views/LiveView.vue', mustHave: true },
  { rel: 'components/OverviewStrip.vue', mustHave: false },
]

/** 把 HTML 注释换成等长空格 —— 注释里写着的标签名不该被当成真标签。 */
const blankComments = (s: string): string =>
  s.replace(/<!--[\s\S]*?-->/g, (c) => ' '.repeat(c.length))

/**
 * 「从 `<details …why…>` 到它那个 `</details>`」这样的区间。
 * 这四页里 `details` 与 `fieldset` 都不嵌套同名标签，所以找第一个闭合标签就够。
 */
function spans(text: string, open: RegExp, close: string): Array<[number, number]> {
  const out: Array<[number, number]> = []
  for (const m of text.matchAll(open)) {
    const start = m.index ?? 0
    const end = text.indexOf(close, start)
    out.push([start, end === -1 ? text.length : end + close.length])
  }
  return out
}

const inside = (ranges: Array<[number, number]>, at: number): boolean =>
  ranges.some(([a, b]) => at > a && at < b)

describe('四页的正文（spec §十二.11）', () => {
  for (const page of SCANNED) {
    it(`${page.rel}：每一个 p.note 都说得出自己是哪一类`, () => {
      const text = readFileSync(join(SRC, page.rel), 'utf8')
      const styleAt = text.indexOf('<style')
      const tpl = blankComments(
        text.slice(text.indexOf('<template'), styleAt === -1 ? undefined : styleAt))

      const folded = spans(tpl, /<details\b[^>]*\bwhy\b[^>]*>/g, '</details>')
      const rail = spans(tpl, /<fieldset\b[^>]*\brail-box\b[^>]*>/g, '</fieldset>')

      const unlabelled: string[] = []
      let seen = 0
      for (const m of tpl.matchAll(/<p\b[^>]*>/g)) {
        const tag = m[0]
        const cls = tag.match(/\bclass="([^"]*)"/)?.[1] ?? ''
        if (!/\bnote\b/.test(cls)) continue
        seen++
        if (/\b(state|reading)\b/.test(cls)) continue
        if (/\bdata-grading\b/.test(tag)) continue
        const at = m.index ?? 0
        if (inside(folded, at) || inside(rail, at)) continue
        unlabelled.push(`${page.rel}: ${tag.replace(/\s+/g, ' ')}`)
      }

      expect(unlabelled,
        `正文里还有没归类的散文段 —— 要么折进 details.why，`
        + `要么标成 state / reading / data-grading：\n${unlabelled.join('\n')}`,
      ).toEqual([])
      // 顺带钉住这条守卫**没有空转**：页面那一档真的还有 p.note 可查。
      if (page.mustHave) {
        expect(seen, `${page.rel} 一个 p.note 都没有 —— 守卫是不是已经空转了？`)
          .toBeGreaterThan(0)
      }
    })
  }
})
