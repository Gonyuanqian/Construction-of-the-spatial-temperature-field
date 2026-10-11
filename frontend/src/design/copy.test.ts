/**
 * 标定那一个图章的三档。**全站一处**（`guards.test.ts` 挡着那三个字面量）。
 *
 * 为什么值得为一句屏上的话单开一个文件：它是用户判断「屏上这些误差数是不是
 * 这份数据的成绩」时唯一的抓手。说错了，屏上不会报错、也没有任何地方提示 ——
 * 用户只会把一份**别人的参数**算出来的数当成自己数据的成绩。
 *
 * 三档的来历（2026-10-10 用户裁定「模型不绑数据集」）：
 *   未标定          —— 连包都没有，用的是兜底参数；
 *   已标定          —— 包是**为这份数据**标的；
 *   已标定（借来的）—— 包是好的，但不是为这份数据标的（特征组对得上就照用）。
 */
import { describe, expect, it } from 'vitest'

import { BORROWED, MODELS, calibratedLabel } from './copy'

describe('标定图章', () => {
  it('没有包 → 兜底参数', () => {
    expect(calibratedLabel({ calibrated: false, mismatch_note: '' }))
      .toBe('未标定（兜底参数）')
  })

  it('包是这份数据的 → 已标定', () => {
    expect(calibratedLabel({ calibrated: true, mismatch_note: '' })).toBe('已标定')
  })

  it('包不是这份数据的 → 已标定（借来的）', () => {
    // ⭐ 这一档是 2026-10-10 才有的。在那之前「不是为这份数据标的」的包
    // **根本走不到屏上**（闸门卡在数据集签名上），所以屏上只有两档。
    expect(calibratedLabel({ calibrated: true, mismatch_note: '这一份模型的参数不是用当前这份数据标出来的' }))
      .toBe(`已标定（${BORROWED}）`)
  })

  it('判「借来的」只看那句话在不在，不看它是哪一句', () => {
    // 前端**不许**自己再判一遍签名（判据在后端一处：`deps.model_fit`）。
    // 换一句完全不相干的话也得是同一档 —— 这条钉的就是「它只是在读结果」。
    expect(calibratedLabel({ calibrated: true, mismatch_note: '随便一句' }))
      .toBe(calibratedLabel({ calibrated: true, mismatch_note: '另一句' }))
  })

  it('没标定时，那句借来的话再长也不改档', () => {
    // `calibrated: false` 与 `mismatch_note` 在后端**互斥**（没有包就没有
    // 「这一份包是谁的」这回事）。真出现这种载荷，说「借来的」比说「未标定」
    // 危险得多 —— 未标定至少不会让人以为有个模型在算。
    expect(calibratedLabel({ calibrated: false, mismatch_note: '借了别的' }))
      .toBe('未标定（兜底参数）')
  })
})

it('新增的四句文案不含屏上禁用的标点', () => {
  // 后端那一条（`test_on_screen_copy.py` 的 BANNED）扫的是载荷字段；
  // 前端这四句也上屏，同一把尺子量它们。
  const banned = ['——', '**', '`', ' · ', '→', '↳']
  for (const s of [MODELS.notSolid, MODELS.notSolidWhy,
                   MODELS.fixating, MODELS.fixatingWhy]) {
    for (const b of banned) expect(s).not.toContain(b)
  }
})
