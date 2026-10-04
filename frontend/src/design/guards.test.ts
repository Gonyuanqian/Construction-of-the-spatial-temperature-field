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

import { MODES, NAV_ITEMS, SYSTEM_TITLE } from './copy'

// Windows 上 import.meta.url 会把中文目录名百分号编码（%E7%A9%BA…），而 pathname 不解码；
// 只替换盘符前的斜杠（原写法）在非 ASCII 路径下会指向一个不存在的目录。
// 改用 fileURLToPath（负责解码），再统一成正斜杠并去掉尾部分隔符 ——
// 这样下面断言里的 '/src/…'、'/index.html' 在任何平台上所指都是同一棵真实的树。
const fwd = (p: string): string => p.replaceAll('\\', '/')
const SRC = fwd(fileURLToPath(new URL('..', import.meta.url))).replace(/\/+$/, '')
const FRONTEND = fwd(fileURLToPath(new URL('../..', import.meta.url))).replace(/\/+$/, '')

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else out.push(p)
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
    for (const item of [...MODES, ...NAV_ITEMS]) {
      if (!item.enabled) {
        expect(item.why.length, `${item.label} 没写为什么未开放`).toBeGreaterThan(10)
      }
    }
  })
})
