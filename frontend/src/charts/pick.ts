/**
 * 「点了一格，这里是什么」—— 全前端**唯一**的判定处。
 *
 * spec §七 V5 给点选定了三种回答，不多不少：
 *
 *   1. 拱外，无定义
 *   2. 无测量带（z 高于实测上限），不报数
 *   3. 一个数（后端算的，不是现场重算的）
 *
 * 第四种回答是这么长出来的：格子里**存着**外推值，界面上却什么都不说 ——
 * 于是外推值被当成了实测值。它不报错，只是让人以为自己看到的是真的。
 * 所以判定只有一个地方做，别处（tooltip、侧栏读数、三维的悬停与坐标查询）
 * 一律拿 `PickResult` 再说人话。
 */
import type { SectionsPayload, SectionShed, VolumePayload } from '../api/types'

export type PickResult =
  | { kind: 'outside' }
  | { kind: 'unmeasured'; z: number }
  | { kind: 'value'; value: number }

/**
 * 判定的**核心**：只看三样事实 —— 这一格的值、斜纹下标、z 坐标。
 *
 * 两个视图各有自己的适配器（`interpretPick` / `interpretVolumePick`）把载荷
 * 翻成这三样。**三种回答、谁压过谁，只在这里写一遍** —— 写第二遍的话，
 * 同一个格子在切面图里说「无测量带」、在三维里报个数，而谁都不报错。
 */
export function pickFrom(
  values: (number | null)[][], stripes: [number, number][], z: number[],
  ix: number, iz: number,
): PickResult {
  const row = values[iz]
  if (!row || ix < 0 || ix >= row.length) {
    // 越界是**编程错误**（两条路都只会报出合法的下标），不是第四种回答。
    // 悄悄返回「无定义」会把一个 bug 画成正常留白。
    throw new Error(
      `格子下标越界：(${ix},${iz})，本片是 ${values.length} 行 × ${row?.length ?? 0} 列`)
  }
  // 顺序是**有意的**：拱外优先于斜纹。两者本该不相交，一旦相交，
  // 「无定义」是更保守的那句。
  const v = row[ix]
  if (v === null) return { kind: 'outside' }
  if (stripes.some(([a, b]) => a === ix && b === iz)) return { kind: 'unmeasured', z: z[iz] }
  return { kind: 'value', value: v }
}

function findShed(payload: SectionsPayload, shed: string): SectionShed {
  const s = payload.sheds.find((x) => x.shed === shed)
  if (!s) throw new Error(`载荷里没有 ${shed} 这个棚（有：${payload.sheds.map((x) => x.shed).join('、')}）`)
  return s
}

/** 二维（V5 切面场）的适配器。 */
export function interpretPick(
  payload: SectionsPayload, shed: string, ix: number, iz: number,
): PickResult {
  const s = findShed(payload, shed)
  return pickFrom(s.values, s.stripes, payload.z, ix, iz)
}

/**
 * 三维（V7 棚体）的适配器。
 *
 * ⚠️ 拱外与无测量带在这里**不能合并**（规格书 §四.4）。三维里两者都是「不填色」，
 * 所以最容易被顺手合成一支 —— 而它们的回答不是同一句话：拱外是「场在那里
 * 没有定义」，无测量带是「值在那儿，但没有实测支撑」。合成之后，悬停到拱顶下
 * 那一层会答「拱外，无定义」，把「不敢说」说成了「不存在」。
 * 这一条由 `pickFrom` 的两行顺序钉着，`pick.test.ts` 里有测试。
 */
export function interpretVolumePick(
  payload: VolumePayload, planeIndex: number, ix: number, iz: number,
): PickResult {
  const plane = payload.planes[planeIndex]
  if (!plane) {
    throw new Error(`这一卷没有第 ${planeIndex} 片（共 ${payload.planes.length} 片）`)
  }
  return pickFrom(plane.values, payload.stripes, payload.z, ix, iz)
}

/** 显示用。**判定里不许调它** —— 一舍入，面板上的数就不是格子里那个数了。 */
export function formatTemp(v: number): string {
  return v.toFixed(2)
}

/**
 * 三种回答的人话。**唯一的文案处** —— 切面图的 tooltip、页③ 的读数表、
 * 三维的悬停读数与坐标查询，四处共用它，措辞因此不可能不一致。
 *
 * ⚠️ 这里只吃 `maxMeasuredZ` 一个数，**不吃整个载荷**：三维那一版不报曲线，
 * 拿不到 `SectionsPayload`。多收一个载荷参数就多一份要同步的东西，
 * 而它只用得上这一个数。
 */
export function pickText(r: PickResult, maxMeasuredZ: number): string {
  switch (r.kind) {
    case 'outside':
      return '拱外，无定义：那里不在棚的拱形截面里，场没有定义'
    case 'unmeasured':
      return `无测量带（z 高于 ${maxMeasuredZ.toFixed(2)} m），不报数：` +
        '带内有外推值，但没有实测支撑'
    case 'value':
      return `现场重算：${formatTemp(r.value)} °C`
  }
}
