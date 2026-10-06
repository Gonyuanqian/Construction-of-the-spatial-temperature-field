/// <reference types="node" />
// @vitest-environment node
/**
 * 设计硬约束的守卫。这一组测试不渲染任何东西 —— 它扫的是**源码文本**。
 *
 * 为什么值得为「文件里的字面量」写测试：spec §六 的三条硬约束
 * （不做数值计算 / 令牌是唯一色源 / 图表只画不取数）都不是能靠
 * 单元测试证明的性质，它们靠的是**没有例外**。而例外是慢慢长出来的：
 * 先是有人图省事写了一个 #999，然后是第二个。所以钉在最便宜的地方。
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

import { FIELD_VIEWS, MODES, NAV_ITEMS, SYSTEM_TITLE } from './copy'

// Windows 上 import.meta.url 会把中文目录名百分号编码（%E7%A9%BA…），而 pathname 不解码；
// 只替换盘符前的斜杠（原写法）在非 ASCII 路径下会指向一个不存在的目录。
// 改用 fileURLToPath（负责解码），再统一成正斜杠并去掉尾部分隔符 ——
// 这样下面断言里的 '/src/…'、'/index.html' 在任何平台上所指都是同一棵真实的树。
const fwd = (p: string): string => p.replaceAll('\\', '/')
const SRC = fwd(fileURLToPath(new URL('..', import.meta.url))).replace(/\/+$/, '')
const FRONTEND = fwd(fileURLToPath(new URL('../..', import.meta.url))).replace(/\/+$/, '')
const REPO = fwd(fileURLToPath(new URL('../../..', import.meta.url))).replace(/\/+$/, '')

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else out.push(p)
  }
  return out
}

// 走仓库根用的剪枝版：node_modules 一个目录就上万文件，扫完再筛等不起。
// 排除的是**产物与外来物**（构建产物、依赖、git 内部），不是「不方便的代码」——
// 守卫够不着的目录，就是它守不住的地方，所以这张排除表要短、要说得清。
const SKIP_DIRS = new Set(['node_modules', 'dist', '.git', '.superpowers',
  '__pycache__', '.venv', 'venv'])
const SKIP_FILES = new Set(['package-lock.json'])
const TEXT_EXT = ['.ts', '.vue', '.py', '.md', '.html', '.css', '.js']

function walkRepo(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name) || SKIP_FILES.has(name)) continue
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walkRepo(p, out)
    else if (TEXT_EXT.some((e) => p.endsWith(e))) out.push(p)
  }
  return out
}

const ALL_SRC = walk(SRC).map(fwd)
const VUE = ALL_SRC.filter((p) => p.endsWith('.vue'))
const TS = ALL_SRC.filter((p) => p.endsWith('.ts') && !p.endsWith('.test.ts'))

describe('设计令牌是颜色与字体的唯一来源', () => {
  it('tokens.css 定义了全部必需的令牌', () => {
    const css = readFileSync(join(SRC, 'design', 'tokens.css'), 'utf8')
    const need = [
      '--paper', '--ink', '--steel', '--leaf', '--net',
      '--ink-muted', '--leaf-soft', '--unknown-stripe',
      '--font-cn', '--font-latin', '--font-num',
      '--w-body', '--w-strong', '--w-title',
      '--size-title', '--size-h', '--size-body', '--size-note',
      // 卡片化重做新增（spec 2026-10-06 §四）
      '--size-label', '--size-readout',
      '--card', '--radius', '--shadow',
      '--lh-body', '--gap-s', '--gap-m', '--gap-l', '--gap-xl',
      '--rule', '--sidebar-w', '--temp-scale', '--err-scale',
    ]
    const missing = need.filter((t) => !css.includes(`${t}:`))
    expect(missing, `tokens.css 少了这些令牌：${missing.join('、')}`).toEqual([])
  })

  it('没有 .vue 文件写死十六进制色值', () => {
    const hits: string[] = []
    for (const p of VUE) {
      const text = readFileSync(p, 'utf8')
      for (const m of text.matchAll(/#[0-9A-Fa-f]{3,8}\b/g)) {
        hits.push(`${p.slice(SRC.length)}: ${m[0]}`)
      }
    }
    expect(hits, '色值必须来自 tokens.css，但发现：\n' + hits.join('\n')).toEqual([])
  })

  it('palette.ts 只按名字读令牌，不重打一遍色值', () => {
    // 图表要的是真颜色字符串（canvas 不认 var(--ink)），所以 palette.ts 得把
    // 令牌读成值。但**读**不等于**抄**：色值只在 tokens.css 里存在一次。
    // 若这里把十六进制重打一遍，单一来源就名存实亡 —— 而现有的守卫只扫 .vue，看不见它。
    const text = readFileSync(join(SRC, 'design', 'palette.ts'), 'utf8')
    for (const t of ['--paper', '--ink', '--ink-muted', '--steel',
                     '--leaf', '--leaf-soft', '--net']) {
      expect(text, `palette.ts 没有读令牌 ${t}`).toContain(t)
    }
    const hexes = [...text.matchAll(/#[0-9A-Fa-f]{6}\b/g)].map((m) => m[0])
    expect(hexes, `palette.ts 不许重打色值：${hexes.join('、')}`).toEqual([])
  })

  it('温度色标是正向 cividis，不是 cividis_r', () => {
    const css = readFileSync(join(SRC, 'design', 'tokens.css'), 'utf8')
    expect(css).toMatch(/--temp-scale:\s*cividis\s*;/)
    // 全仓不许出现 cividis_r —— 它是 Streamlit 版用反了的那一个（spec §8.1）
    const bad = [...VUE, ...TS].filter((p) =>
      readFileSync(p, 'utf8').includes('cividis_r'))
    expect(bad.map((p) => p.slice(SRC.length))).toEqual([])
  })

  it('十六进制色值只允许出现在两个地方：tokens.css 与色标采样点', () => {
    // 色标名不是颜色，所以采样点只能写成字面量；除此之外任何地方的十六进制
    // 都要走令牌。
    //
    // tokens.css 的例外是**整文件**的（它本来就是令牌的唯一定义处）。
    // charts/scale.ts 例外但**定点**：文件里的十六进制必须与两条色标的采样点
    // 集合**相等** —— 多一个（夹带了别的颜色）红，少一个（被删了）也红。
    // 早先这个例外挂在 options/diurnalResidual.ts 上，色标搬到 scale.ts 之后
    // 必须一起搬：守卫指着一个不再含色值的文件，等于那七个值从此没人守。
    const TEMP_STOPS = ['#00224E', '#12456F', '#4C6C7F', '#7C7B78', '#BE8353', '#EB9A31', '#FFE945']
    const DELTA_STOPS = ['#053061', '#2166AC', '#4393C3', '#92C5DE', '#D1E5F0', '#F7F7F7',
      '#FDDBC7', '#F4A582', '#D6604D', '#B2182B', '#67001F']
    const TOKENS = 'design/tokens.css'
    const SCALES = 'charts/scale.ts'
    const hits: string[] = []
    for (const p of ALL_SRC.filter((x) => !x.endsWith('.test.ts'))) {
      const rel = p.slice(SRC.length).replace(/\\/g, '/')
      const name = rel.slice(1)
      if (name === TOKENS || rel === TOKENS) continue
      const hexes = [...readFileSync(p, 'utf8').matchAll(/#[0-9A-Fa-f]{6}\b/g)]
        .map((m) => m[0].toUpperCase())
      if (name === SCALES || rel === SCALES) {
        const want = new Set([...TEMP_STOPS, ...DELTA_STOPS].map((s) => s.toUpperCase()))
        const got = new Set(hexes)
        for (const h of got) if (!want.has(h)) hits.push(`${rel}: 多出的色值 ${h}`)
        for (const w of want) if (!got.has(w)) hits.push(`${rel}: 缺少色标采样点 ${w}`)
      } else {
        for (const h of hexes) hits.push(`${rel}: ${h}`)
      }
    }
    expect(hits).toEqual([])
  })

  it('阴影只有一档，且必须写成 var(--shadow)', () => {
    // spec §四 的三条判据之一：阴影只有一档。SaaS 套装的招牌正是
    // 「用阴影的深浅伪造层级」—— 所以这里不是禁阴影，是禁**第二种**阴影。
    // 与色值那条守卫同一个手法：钉在最便宜的地方（源码文本）。
    const hits: string[] = []
    for (const p of ALL_SRC.filter((x) => !x.endsWith('.test.ts'))) {
      const text = readFileSync(p, 'utf8')
      for (const m of text.matchAll(/box-shadow\s*:\s*([^;]+);/g)) {
        // `?? ''`：`tsconfig` 开着 noUncheckedIndexedAccess 时 `m[1]` 是
        // `string | undefined`。取不到捕获组时给空串 —— 空串不等于
        // `var(--shadow)`，于是照样被报出来，不会静默放过。
        const v = (m[1] ?? '').trim()
        if (v !== 'var(--shadow)') {
          hits.push(`${p.slice(SRC.length)}: box-shadow: ${v}`)
        }
      }
    }
    expect(hits, '阴影只有一档，且只能写成 var(--shadow)：\n' + hits.join('\n'))
      .toEqual([])
  })
})

describe('文案只有一个来源', () => {
  it('系统标题在全仓只定义一次，且不在 .vue 里重复', () => {
    const files = [...VUE, ...TS, fwd(join(FRONTEND, 'index.html'))]
    const withTitle = files.filter((p) =>
      readFileSync(p, 'utf8').includes(SYSTEM_TITLE))
    expect(withTitle.map((p) => p.replace(FRONTEND, ''))).toEqual([
      '/src/design/copy.ts',
      '/index.html',
    ])
  })

  it('标题在仓库其余地方也逐字一致，旧名不再残留', () => {
    // 上面那条只扫 frontend/src 与 index.html —— 于是同一个标题在 README.md 与
    // backend/api/main.py 里又各写了一遍，写的还是计划 1 的旧名（人参棚…），
    // 整整漂了一份计划都没人发现：界面说「棚式…」、README 与 /docs 说旧名，
    // 而验收时对盘要核的正是这个名字。
    //
    // 这一条是本组守卫的**补盲**：扫描集扩到仓库根。诚实说清它够不着什么 ——
    // .json/.docx/.png 不扫（只扫源码与文档），构建产物与 node_modules 不扫
    // （那是生成物，不是源头）；旧名是按「人参棚 + 空间温度场」这个**系统名组合**
    // 拦的，不是按「人参棚」——数据集文件名里也有这三个字，那是数据资产的名字，
    // 改了反而错。
    //
    // 字面量为什么拆开写：这条守卫扫的是**源码文本**，而它自己就是一个源码文件。
    // 整串写在这里的话，它第一个举报的就是自己。拆开拼，才既扫得着别人、又不自指。
    const RETIRED = ['人参棚', '空间温度场'].join('')
    const files = walkRepo(REPO).map(fwd)
    const retired = files.filter((p) => readFileSync(p, 'utf8').includes(RETIRED))
    expect(retired.map((p) => p.slice(REPO.length)),
      `旧名「${RETIRED}…」还残留在：`).toEqual([])

    // 正着也钉一遍：这两处必须写着令牌里的那个名字。
    for (const rel of ['/README.md', '/backend/api/main.py']) {
      const text = readFileSync(fwd(join(REPO, rel)), 'utf8')
      expect(text, `${rel} 没写系统标题`).toContain(SYSTEM_TITLE)
    }
  })

  it('index.html 的 <title> 与令牌一致', () => {
    // index.html 是静态文件，import 不了 TS —— 所以它只能抄一遍，
    // 而抄的这一遍就是这条测试存在的理由。
    const html = readFileSync(join(FRONTEND, 'index.html'), 'utf8')
    expect(html).toContain(`<title>${SYSTEM_TITLE}</title>`)
  })

  it('导航的次序就是流水线的次序，不许排序', () => {
    expect(NAV_ITEMS.map((i) => i.label)).toEqual([
      '数据导入与检查', '模型训练', '空间温度场的构建', '影响分析',
    ])
  })

  it('每个未开放的项都带一句给人看的理由', () => {
    // 三个清单一起管：模式、页面导航、页③ 的视图切换。
    // 少收一个，那个清单里的"未开放"就会退化成一句"本轮不做"。
    for (const item of [...MODES, ...NAV_ITEMS, ...FIELD_VIEWS]) {
      if (!item.enabled) {
        expect(item.why.length, `${item.label} 没写为什么未开放`).toBeGreaterThan(10)
      }
    }
  })
})
