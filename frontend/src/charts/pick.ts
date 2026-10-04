/**
 * 「点了一格，这里是什么」—— 全前端**唯一**的判定处。
 *
 * spec §七 V5 给点选定了三种回答，不多不少：
 *
 *   1. 拱外，无定义
 *   2. 无测量带（z 高于实测上限），不报数
 *   3. 一个数（后端算的，现场重算）
 *
 * 第四种回答是这么长出来的：格子里**存着**外推值，界面上却什么都不说 ——
 * 于是外推值被当成了实测值。它不报错，只是让人以为自己看到的是真的。
 * 所以判定只有一个地方做，别处（tooltip、侧栏读数、将来的导出）
 * 一律拿 `PickResult` 再说人话。
 */
import type { SectionsPayload, SectionShed } from '../api/types'

export type PickResult =
  | { kind: 'outside' }
  | { kind: 'unmeasured'; z: number }
  | { kind: 'value'; value: number }

function findShed(payload: SectionsPayload, shed: string): SectionShed {
  const s = payload.sheds.find((x) => x.shed === shed)
  if (!s) throw new Error(`载荷里没有 ${shed} 这个棚（有：${payload.sheds.map((x) => x.shed).join('、')}）`)
  return s
}

export function interpretPick(
  payload: SectionsPayload, shed: string, ix: number, iz: number,
): PickResult {
  const s = findShed(payload, shed)
  const row = s.values[iz]
  if (!row || ix < 0 || ix >= row.length) {
    // 越界是**编程错误**（ECharts 只会报出合法的下标），不是第三种状态之外的
    // 第四种回答。所以这里抛错 —— 悄悄返回「无定义」会把一个 bug 画成正常留白。
    throw new Error(`格子下标越界：(${ix},${iz})，本断面是 ${s.values.length} 行 × ${row?.length ?? 0} 列`)
  }

  // 顺序是**有意的**：拱外优先于斜纹。两者本该不相交，一旦相交，
  // 「无定义」是更保守的那句。
  const v = row[ix]
  if (v === null) return { kind: 'outside' }
  if (s.stripes.some(([a, b]) => a === ix && b === iz)) return { kind: 'unmeasured', z: payload.z[iz] }
  return { kind: 'value', value: v }
}

/** 显示用。**判定里不许调它** —— 一舍入，面板上的数就不是格子里那个数了。 */
export function formatTemp(v: number): string {
  return v.toFixed(2)
}

/**
 * 三种回答的人话。**唯一的文案处** —— tooltip 与侧栏读数共用它，
 * 两处措辞因此不可能不一致。
 */
export function pickText(r: PickResult, payload: SectionsPayload): string {
  switch (r.kind) {
    case 'outside':
      return '拱外，无定义：那里不在棚的拱形截面里，场没有定义'
    case 'unmeasured':
      return `无测量带（z 高于 ${payload.max_measured_z.toFixed(2)} m），不报数：` +
        '带内有外推值，但没有实测支撑'
    case 'value':
      return `现场重算：${formatTemp(r.value)} °C`
  }
}
