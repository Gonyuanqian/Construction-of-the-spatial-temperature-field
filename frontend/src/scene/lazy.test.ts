/// <reference types="node" />
// @vitest-environment node
/**
 * 三维那一块**不在入口 chunk 里**。
 *
 * 懒加载这件事运行时断言不了（jsdom 不跑真打包），能断言的只有**构建产物**：
 * `dist/assets/` 里必须有一个 chunk 带着 Three，而**入口那个**不带着它。
 * 断的是「入口不背这 600 KB」，不是「某个文件叫什么名字」—— 所以按**内容**找，
 * 不按文件名找。
 *
 * **产物陈旧就红，不是 skip。** 源码比 `dist/index.html` 新的时候，红绿都不作数 ——
 * 那时它反映的是上一次构建，不是现在这份代码。这里与后端那条同类测试
 * （`test_spa_fallback.py` 用 skip）处置不同，理由写在 `REASON` 那句断言旁边。
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const fwd = (p: string): string => p.replaceAll('\\', '/')
const FRONTEND = fwd(fileURLToPath(new URL('../..', import.meta.url))).replace(/\/+$/, '')
const SRC = join(FRONTEND, 'src')
const DIST = join(FRONTEND, 'dist')

/** Three 里的**字符串字面量**：压缩不会改名，而类名会被改名。 */
const THREE_MARK = 'THREE.WebGLRenderer'

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else out.push(p)
  }
  return out
}

function staleReason(): string {
  if (!existsSync(join(DIST, 'index.html'))) {
    return 'dist/index.html 不在：先跑 npm run build（frontend/dist 不进 git，新克隆里没有）'
  }
  const built = statSync(join(DIST, 'index.html')).mtimeMs
  const newest = Math.max(...walk(SRC).map((p) => statSync(p).mtimeMs))
  if (newest > built) {
    return 'dist 比 src 旧：先跑 npm run build 再跑这一条，否则它反映的是上一次构建'
  }
  return ''
}

const REASON = staleReason()

describe('三维懒加载', () => {
  it('入口 chunk 里没有 Three，别的 chunk 里有', () => {
    // 产物不可信时**在这里说清为什么**，而不是 skip 掉。
    // skip 的坏处是它和「这条被禁用了」在报告里长得一样 —— 一句 reason
    // 顶不过一个绿点，而一个绿点会让人以为懒加载被验过了。
    //
    // 「新克隆里没构建过」在别处（`test_spa_fallback.py`）是常态，所以那边 skip；
    // 这里要防的是「构建过了但没重构建」—— 那是这次改动的产物对不上源码，
    // 红才是对的答案。两者看着像，处境不像。
    expect(REASON, 'dist 不可信，先 npm run build 再跑这一条').toBe('')

    const html = readFileSync(join(DIST, 'index.html'), 'utf8')
    const entry = /<script[^>]+src="\/assets\/([^"]+\.js)"/.exec(html)?.[1]
    expect(entry, 'index.html 里找不到入口 chunk 的 <script src>').toBeTruthy()

    const chunks = readdirSync(join(DIST, 'assets')).filter((f) => f.endsWith('.js'))
    expect(
      chunks.length,
      '只有一个 chunk：什么都没被切开，懒加载没有生效',
    ).toBeGreaterThan(1)

    const entryText = readFileSync(join(DIST, 'assets', entry!), 'utf8')
    expect(
      entryText.includes(THREE_MARK),
      '入口 chunk 里带着 Three —— 懒加载没生效，断面的首屏在为三维付钱',
    ).toBe(false)

    const others = chunks
      .filter((f) => f !== entry)
      .map((f) => readFileSync(join(DIST, 'assets', f), 'utf8'))
    expect(
      others.some((t) => t.includes(THREE_MARK)),
      '没有任何按需 chunk 带着 Three —— 要么它被摇掉了，要么整块没被打进去',
    ).toBe(true)
  })
})
