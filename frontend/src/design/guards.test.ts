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

import { BORROWED, FIELD_VIEWS, LIVE_NAV_ITEMS, MODES, NAV_ITEMS, SYSTEM_TITLE } from './copy'

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
      // 切面图的测点分层色（页①，2026-10-06）：取自用户给的参考图
      '--layer-top', '--layer-mid', '--layer-low',
      // 导航专属的一对蓝（2026-10-06 用户裁定）。登记的用处不是"存在"，
      // 是**被删掉会红** —— 没进这张表的令牌，谁把它删了都没人吭声。
      '--nav-tint', '--nav-blue',
      // 字号标尺（2026-10-06 放大）与两个图表字号。图表那两个是给
      // `design/palette.ts` 读走的（canvas 不认 var()），删了图会静默退回默认字号。
      '--size-h3', '--size-chart-axis', '--size-chart-title',
      // 残差图的柱子色（页②，2026-10-08 走查时从 `--steel` 换过来的）。
      '--bar',
      // 页⑤ 仪表盘重做（2026-10-12）。登记的用处不是「存在」，是**被删掉会红**：
      // 浅色那一档全部取等值，页①②③④ 一个像素不动。
      '--header', '--on-face', '--face-dim', '--interact', '--card-2', '--ok',
      // 版式那两个（同一轮）。标题条高度与右栏宽度只在 /live 上离开默认值。
      '--titlebar-h', '--side-w',
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

  it('一层 `.seg` 不裁焦点环，也不自己写 outline', () => {
    // 终审 I-4：计划把「分段控件的 `:focus-visible` 不许被新样式盖掉」列为
    // 最可能咬到真人的前四条之一，还写着「Task 4 的 ModeSwitch.test.ts」——
    // 而那个文件里一条都没有。缓解本身在（全局那条还在、组件没覆盖它），
    // 但**无人回归**。jsdom 量不到 outline 画出来是什么样，所以退到源码文本，
    // 与上面两条守卫同一个手法。
    //
    // 两件事各钉一次：
    // ① 组件自己不许写 `outline` —— 一写就把 `base.css` 那条盖掉；
    // ② 容器不许 `overflow: hidden` —— `:focus-visible` 带 `outline-offset: 2px`，
    //    伸出按钮盒的那 2px 会被祖先裁掉（首个/末个按钮尤甚）。圆角改由
    //    首末子元素各自带，视觉不变。
    // 扫**所有**定义了 `.seg` 的组件，不是写死一个文件 —— 页③ 与实时屏的
    // 左栏切换也用它，写死一处等于新加的第二处没人守。
    const withSeg = VUE.filter((p) =>
      /\.seg\s*\{/.test(readFileSync(p, 'utf8')))
    expect(withSeg.map((p) => p.slice(SRC.length)).sort(),
      '`.seg` 的守卫扫不到任何文件，说明它已经空转了').toEqual([
      '/components/ModeSwitch.vue',
      '/views/FieldView.vue',
      '/views/LiveView.vue',
    ])
    for (const p of withSeg) {
      const css = readFileSync(p, 'utf8')
      const rel = p.slice(SRC.length)
      expect(css, `${rel} 自己写了 outline，全局那条就没了`).not.toMatch(/outline\s*:/)
      const seg = css.match(/\.seg\s*\{[^}]*\}/)?.[0] ?? ''
      expect(seg, `${rel} 的 .seg 会把焦点环裁掉`).not.toMatch(/overflow/)
    }
    // 正着也钉一遍：被继承的那条还在 `base.css` 里，而且底色是 `--leaf`。
    const base = readFileSync(join(SRC, 'design', 'base.css'), 'utf8')
    const focus = base.match(/:focus-visible\s*\{[^}]*\}/)?.[0] ?? ''
    expect(focus, 'base.css 里没有 :focus-visible 规则').not.toBe('')
    // ⚠️ 2026-10-12：焦点环从主色改到**交互色**（`base.css` 那一条）。
    // 这条守卫守的是「被继承的那条还在、没被组件盖掉」，所以它跟着换算 —
    // 不换的话它会指着 `base.css` 里一个已经不存在的值，从此永远红。
    expect(focus).toContain('var(--interact)')
  })

  it('一排指标卡在窄屏上换行，不被压窄也不撑出横向滚动', () => {
    // 终审 I-4 的另一半，与上一条同病：计划写着「Task 3 的 StatRow 守卫」
    // 测 1280px 五卡换行，而 `StatRow.test.ts` 里**没有任何**与 flex-wrap /
    // min-width / 溢出相关的断言。jsdom 不做布局（`getBoundingClientRect()`
    // 一律回 0），所以这里量的是规则本身。
    //
    // ⚠️ 这条**够不着**真正的版面：1280 / 1440 / 2560 下到底破不破版，
    // 仍是人工验收项（§十二.8），不是这条测试能证明的。
    const text = readFileSync(join(SRC, 'components', 'StatRow.vue'), 'utf8')
    const rule = text.match(/\.stats\s*\{[^}]*\}/)?.[0] ?? ''
    expect(rule, 'StatRow 里没有 .stats 规则').not.toBe('')
    expect(rule, '窄屏上不换行就会压成窄条或撑出横向滚动').toMatch(/flex-wrap:\s*wrap/)
    // 换行要有阈值，不然永远不换 —— `min-width` 就是那个阈值。
    const child = text.match(/\.stats\s*>\s*:deep\(\*\)\s*\{[^}]*\}/)?.[0] ?? ''
    expect(child, '一排的每一张卡没有最小宽度').toMatch(/min-width:\s*\d+px/)
  })

  it('页① 那排卡的浅叶底走令牌，而且只改底色', () => {
    // 2026-10-06 用户裁定：页① 那排卡换成四个数，并铺 `--leaf-soft`。
    // 这条守两件事：
    // ① 色必须从令牌来。写成十六进制会被上面那条全局守卫拦下，但**换一个
    //    令牌**不会 —— 那同样把「这一排是体检结论、别处是内容」说没了。
    // ② 只许动 background。圆角与阴影全站各一档（spec §四），在一条
    //    tinted 规则里偷偷加第二种，正是那个 SaaS 套装的招牌。
    const text = readFileSync(join(SRC, 'components', 'StatRow.vue'), 'utf8')
    const rule = text.match(/\.stats\.tinted[^{]*\{[^}]*\}/)?.[0] ?? ''
    expect(rule, 'StatRow 里没有浅叶底那条规则').toContain('var(--leaf-soft)')
    expect(rule, '浅叶底那一条只该改背景色').not.toMatch(/border-radius|box-shadow/)
  })

  it('页① 的数据预览两个方向都能滚，表头与首列粘住', () => {
    // 用户对这一块的原话是「做成上下左右滑动的窗口形式」。而 jsdom 不做布局
    // （`getBoundingClientRect()` 一律回 0），滚动与 sticky 在那边量不出任何
    // 效果 —— 所以与上面 StatRow 那两条同一个道理：量的是**规则本身**。
    //
    // ⚠️ 这条够不着：`max-height` 到底够不够高、粘住的表头会不会透出底下的字、
    // 26 列在 1280px 下横向滚动条在不在。三条都是人眼验收项。
    const text = readFileSync(join(SRC, 'components', 'DataPreviewTable.vue'), 'utf8')
      // 注释里写着的 `overflow` / `sticky` 不该被当成真规则。
      .replace(/\/\*[\s\S]*?\*\//g, (c) => ' '.repeat(c.length))
    const rule = (sel: string): string => {
      // 选择器先当字面量转义（`.win` 的 `.` 是元字符），再把空白放宽成 `\s+`
      // —— 源码里换不换行、缩进几个空格都不该让这条测试红。
      const pat = sel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+')
      const m = [...text.matchAll(new RegExp(`${pat}\\s*\\{([^}]*)\\}`, 'g'))]
      expect(m.length, `DataPreviewTable.vue 里没有 ${sel} 这条规则`).toBeGreaterThan(0)
      return m.map((x) => x[1]).join('\n')
    }
    const win = rule('.win')
    expect(win, '纵向不可滚').toMatch(/overflow-y:\s*auto/)
    expect(win, '横向不可滚').toMatch(/overflow-x:\s*auto/)
    // 没有高度上限，表就跟着内容往上长，滚动条长在 <body> 上 —— 那不是一个
    // 窗口，是一张很长的表。用户要的是前者。
    expect(win, '没有高度上限').toMatch(/max-height:\s*\d+px/)
    expect(rule('thead th'), '表头不粘').toMatch(/position:\s*sticky/)
    expect(rule('td.t'), '时刻列不粘').toMatch(/position:\s*sticky/)
  })

  it('palette.ts 只按名字读令牌，不重打一遍色值', () => {
    // 图表要的是真颜色字符串（canvas 不认 var(--ink)），所以 palette.ts 得把
    // 令牌读成值。但**读**不等于**抄**：色值只在 tokens.css 里存在一次。
    // 若这里把十六进制重打一遍，单一来源就名存实亡 —— 而现有的守卫只扫 .vue，看不见它。
    const text = readFileSync(join(SRC, 'design', 'palette.ts'), 'utf8')
    for (const t of ['--paper', '--ink', '--ink-muted', '--steel',
                     '--leaf', '--leaf-soft', '--net', '--bar']) {
      expect(text, `palette.ts 没有读令牌 ${t}`).toContain(t)
    }
    const hexes = [...text.matchAll(/#[0-9A-Fa-f]{6}\b/g)].map((m) => m[0])
    expect(hexes, `palette.ts 不许重打色值：${hexes.join('、')}`).toEqual([])
  })

  it('温度色标是正向 turbo，不是它的反向', () => {
    const css = readFileSync(join(SRC, 'design', 'tokens.css'), 'utf8')
    expect(css).toMatch(/--temp-scale:\s*turbo\s*;/)
    // 全仓不许出现反向色标的名字 —— spec §8.1 记着这个坑：
    // 用反了的话图会整张读反，而屏上不会报任何错。
    // ⚠️ 两个反向名一起扫：换 turbo 只是换了哪一条色标，
    // 「反向」这件事本身照旧不该在仓里出现。
    const bad = [...VUE, ...TS].filter((p) => {
      const t = readFileSync(p, 'utf8')
      return t.includes('cividis_r') || t.includes('turbo_r')
    })
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
    // 必须一起搬：守卫指着一个不再含色值的文件，等于那九个值从此没人守。
    // ⚠️ 2026-10-12 换 turbo 时**一起改**：漏改的话 `charts/scale.ts` 里那九个
    // 新值会全部被判成「多出的色值」，而这个文件正好也在同一次提交里。
    const TEMP_STOPS = ['#30123B', '#4675ED', '#1BCFD4', '#61FC6C', '#D1E834',
      '#F6A12A', '#F04D02', '#B10A01', '#7A0403']
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

describe('基线控件是控件，不是裸文本', () => {
  it('button 有真实的边界、圆角与底色，且不吃阴影', () => {
    // spec §一 成因 1：`button { background: none; border: 0 }` 让全站按钮
    // 退化成带下划线的字。这是「读起来像文档」最直接的一条成因。
    // 阴影不许上按钮 —— 阴影专供卡片（spec §九）。
    const css = readFileSync(join(SRC, 'design', 'base.css'), 'utf8')
    const rule = css.match(/(^|\n)button\s*\{[^}]*\}/)?.[0] ?? ''
    expect(rule, 'base.css 里没有 button 规则').not.toBe('')
    expect(rule).toContain('background: var(--card)')
    expect(rule).toContain('border: 1px solid var(--steel)')
    expect(rule).toContain('border-radius: var(--radius)')
    expect(rule).not.toContain('box-shadow')
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
    for (const item of [...MODES, ...NAV_ITEMS, ...FIELD_VIEWS, ...LIVE_NAV_ITEMS]) {
      if (!item.enabled) {
        expect(item.why.length, `${item.label} 没写为什么未开放`).toBeGreaterThan(10)
      }
    }
  })

  it('标定图章的三个字面量只在 copy.ts 里，`.vue` 一律走 `calibratedLabel`', () => {
    // ⚠️ 这是本次（2026-10-10 用户裁定「模型不绑数据集」）最不能错的一处标注：
    // 三档（未标定 / 已标定 / 已标定（借来的））说错了，用户会把**一份别人的
    // 参数**算出来的误差当成这份数据的成绩 —— 屏上不会报错，也没有任何地方
    // 提示。原先三个页面各自写了一遍那个二元三元表达式，所以加了这一档之后
    // 它们在屏上就会各说各话。
    //
    // 扫的是**带引号的字面量**：注释里当然可以提「已标定」这三个字
    // （读的人正是靠注释才明白这一档在干什么），写死的一句话一定带引号。
    const quoted = (s: string, t: string) =>
      t.includes(`'${s}'`) || t.includes(`"${s}"`) || t.includes(`\`${s}\``)
    const bad: string[] = []
    for (const p of VUE) {
      const t = readFileSync(p, 'utf8')
      if (quoted('已标定', t) || quoted('未标定（兜底参数）', t)) bad.push(p.slice(SRC.length))
    }
    expect(bad, '这些 .vue 自己写死了标定图章的话').toEqual([])

    // 正着也钉一遍：**四处**读取点（页③ 的指标卡与图表头、页④ 那一卷、
    // 页⑤ 这一帧），一个不多一个不少。上面那条只挡得住「自己写死一句话」，
    // 挡不住「干脆不印图章」（把格子 `v-if` 掉、或者整个删掉）。
    // ⚠️ 按路径排序再比：`walk()` 吃的是 `readdirSync` 的次序，那是文件系统的
    // 事，拿它当断言次序等于让这条测试在别人的机器上红。
    const where = VUE
      .map((p) => [p.slice(SRC.length),
                   readFileSync(p, 'utf8').split('calibratedLabel(').length - 1] as const)
      .filter(([, n]) => n > 0)
      .sort((a, b) => a[0].localeCompare(b[0]))
    expect(where).toEqual([
      ['/scene/VolumeView.vue', 1],
      ['/views/FieldView.vue', 2],
      ['/views/LiveView.vue', 1],
    ])
  })

  it('「借来的」三个字也只在 copy.ts 里', () => {
    // 同一个道理：页③ 的选项、模型库那一行的图章、标定图章上的括注，三处
    // 印的是**同一档**。三处各写一遍不会报错，只会漂成一个说「借来的」、
    // 一个说「非本地」。
    const quoted = (t: string) =>
      t.includes(`'${BORROWED}'`) || t.includes(`"${BORROWED}"`) || t.includes(`\`${BORROWED}\``)
    const bad = [...VUE, ...TS.filter((p) => !p.endsWith('design/copy.ts'))]
      .filter((p) => quoted(readFileSync(p, 'utf8')))
    expect(bad.map((p) => p.slice(SRC.length))).toEqual([])
  })
})
