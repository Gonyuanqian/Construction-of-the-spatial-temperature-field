/**
 * 页① 的切面图：一座棚的拱、八个测点（内部叫 V1）。
 *
 * **纯函数**：进的是后端给的两份载荷与调色板，出的是画法。
 * 这里不取数、不算数 —— 测点的 5 天均值与测点编号都是后端算好的（硬约束 1）。
 *
 * 2026-10-06 裁定（用户给了参考切面图）：**只画一个切面**。原先三棚并排、
 * 每格一张，但三座棚的点位本来就是同一套 —— 并排三张是把同一个形状画三遍，
 * 而每格只剩三分之一宽，拱与点都读不清。三座棚的均值改由 tooltip 带出来。
 *
 * 同一轮改掉的三处：
 *   · **去掉 z = 1.10 m 那条「无测量带」虚线**。顶层两个测点的 z 也是 1.10，
 *     线压在点上 —— 既没标出带在哪，又让人以为那两个点落在带里。这条约束
 *     改由页面的口径说明用文字交代；
 *   · **打开网格与刻度**（spec 设计主张 1「拱是坐标系本身」原先要求关掉）。
 *     没有刻度就看不出测点在哪 —— 这正是「展示得不准确」最直接的一处。
 *     轴线框仍然关着：拱还是这张图的轮廓，网格只是量尺；
 *   · **测点按高度分三层着色**，三色取自用户的那张参考图。
 *
 * 图幅照参考图定：横 2.1 m 对纵约 1.1 m，**纵向被拉长**（不是等比例），
 * 拱因此比真比例（2.1 : 0.85）显得高。拉长的倍率随卡片宽度走 ——
 * 图幅是按百分比给的，窗口越宽拱越扁，这是百分比图幅的固有代价。
 */
import type { EChartsOption } from 'echarts'

import type { ArchPayload, DatasetPayload, Position } from '../../api/types'
import { fmt1 } from '../../design/format'
import type { ColorKey, Palette } from '../../design/palette'

/**
 * 纵轴下界。**不从 0 起**：拱脚在 z ≈ 0.45 m、最低测点在 0.40，从 0 起画
 * 下面四成是空的。取 0.2 是因为它正好落在横网格线的步长上（0.2 / 0.4 / …），
 * 参考图同样把下界抬到了 0.25 附近。
 */
const Z_MIN = 0.2
/** 网格步长，与参考图一致：横线每 0.2 m，竖线每 0.5 m。 */
const X_STEP = 0.5
const Z_STEP = 0.2

/**
 * 图幅。**横向几乎占满卡片**（2026-10-06 用户裁定）。
 *
 * 原先是 `left: '30%', width: '40%'`，注释写的是「四边各留三成，图居中成一张
 * 图谱」—— 那是这张图**还占满整页宽**时定的：卡片约 1000px 时图幅 400px，
 * 那三成是构图。页① 改成左右分栏之后卡片只剩一半，同一组百分比把图幅压到
 * 约 190px，留白却原样留着 —— 用户看到的就是「图挤在中间、两边一大片白」。
 * **留白是相对卡片算的，卡片一变，构图就变成了白地。**
 *
 * 现在这三个数是按**卡片里各要让出多少**定的，不是按构图：
 *   left 12%    纵轴刻度（"1.3" 在 12px 等宽下约 30px，再加轴与刻度之间的间距）
 *   width 80%   图幅本身
 *   剩下 8%     最右那个测点（x = 1.95 的 B8）点旁的编号。它按 `position: 'right'`
 *               往外画，没有这块地方就会被卡片边裁掉。
 * 上下两成留白照旧：上面给纵轴名，下面给横轴名与它的刻度。
 */
const GRID = { left: '12%', width: '80%', top: '10%', bottom: '14%' }

/**
 * 层从高到低取哪一档色。**层的名字（`ztop` / `z0.7` / `z0.4`）不进这里** ——
 * 名字是后端的事，这里只认高低。多过三层的层落回 `ink-muted`：那是
 * 「有个东西我没认出来」的灰，比悄悄拿第一层的色画上去诚实。
 */
const LAYER_SLOTS: ColorKey[] = ['layerTop', 'layerMid', 'layerLow']

/** `[x, z, 编号, 棚1 均值, 棚2 均值, …]`。均值缺失是 `null`，不是 0。 */
type PointDatum = [number, number, string, ...(number | null)[]]

export function buildSensorLayoutOption(
  ds: DatasetPayload,
  arch: ArchPayload,
  p: Palette,
): EChartsOption {
  const sheds = arch.sheds
  // 棚的次序**只有一个来源**：`arch.sheds`。tooltip 的行序与每个点里那串
  // 均值的排列都用它 —— 两边各排各的话，p2 的数会挂在 p3 的名下，
  // 而这种错在屏幕上长得和对的一模一样。
  const shedIds = sheds.map((s) => s.id)
  const series: Record<string, unknown>[] = [
    {
      name: '拱形轮廓',
      type: 'line',
      data: arch.arch,
      showSymbol: false,
      silent: true,
      lineStyle: { color: p.ink, width: 1.2 },
      z: 2,
    },
  ]

  for (const { layer, color, points } of byLayer(ds, p, shedIds)) {
    series.push({
      name: `${layer} 测点`,
      type: 'scatter',
      data: points,
      symbolSize: 18,
      itemStyle: { color, borderColor: p.paper, borderWidth: 2 },
      label: {
        show: true,
        position: 'right',
        distance: 6,
        color: p.ink,
        fontSize: p.chartAxis,
        // 编号拿不到就空着。**不就地编一个** —— 错的编号与对的看起来一模一样。
        formatter: (params: { data: PointDatum }) => params.data[2] ?? '',
      },
      z: 3,
    })
  }

  return {
    // 底色由外层的卡片给，图自己不铺。铺一层纸色的话，页面底一深（2026-10-06
    // 起页面比卡片深）就成了卡片里一块颜色不同的**方板** —— 方角嵌在圆角卡里，
    // 而且与另外三张 option 的 `'transparent'` 不一致。
    backgroundColor: 'transparent',
    animation: false,
    grid: GRID,
    xAxis: {
      type: 'value',
      min: arch.x_min,
      max: arch.x_max,
      interval: X_STEP,
      name: '棚长 x / m',
      nameLocation: 'middle',
      nameGap: 26,
      nameTextStyle: { color: p.inkMuted, fontSize: p.chartAxis },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: true, lineStyle: { color: p.steel, width: 1 } },
      axisLabel: { show: true, color: p.inkMuted, fontSize: p.chartAxis, formatter: (v: number) => fmt1(v) },
    },
    yAxis: {
      type: 'value',
      min: Z_MIN,
      max: arch.z_max,
      interval: Z_STEP,
      name: '高度 z / m',
      nameTextStyle: { color: p.inkMuted, fontSize: p.chartAxis },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: true, lineStyle: { color: p.steel, width: 1 } },
      axisLabel: { show: true, color: p.inkMuted, fontSize: p.chartAxis, formatter: (v: number) => fmt1(v) },
    },
    series,
    tooltip: {
      trigger: 'item',
      backgroundColor: p.paper,
      borderColor: p.steel,
      textStyle: { color: p.ink },
      formatter: (params: { data: PointDatum }) => {
        const d = params.data
        const rows = sheds.map((s, i) => {
          // 元组尾部是变长的（棚有几座就几格），按下标取出来的是整个联合类型，
          // 这里收回「一格均值」该有的那个类型。缺格是 undefined，走「无值」。
          const v = d[3 + i] as number | null | undefined
          return `${s.id}　${v === null || v === undefined ? '无值' : `${fmt1(v)} °C`}`
        })
        // 一页最多一处折叠的口径说明，这里的量纲与棚名要短，别抢正文。
        const head = d[2] ? `${d[2]}，5 天棚温均值` : '5 天棚温均值'
        return [head, ...rows].join('<br/>')
      },
    },
  } as unknown as EChartsOption
}

/**
 * 测点按高度分层，层从高到低。每层一组：层的名字、这一层用哪一档色、以及
 * 排好序的点。同层内按 x 从左到右 —— 与后端排编号的次序**同一条规则**，
 * 所以图上从左往右读就是 B1、B2……（跨层时编号在前一层继续）。
 */
function byLayer(
  ds: DatasetPayload,
  p: Palette,
  shedIds: string[],
): { layer: string; color: string; points: PointDatum[] }[] {
  const groups = new Map<string, Position[]>()
  for (const pos of ds.positions) {
    const g = groups.get(pos.layer)
    if (g) g.push(pos)
    else groups.set(pos.layer, [pos])
  }

  // 次序由调用方给的 `shedIds` 定，不在这里另排一遍 —— 见上面那段注释。
  const means = (pos: Position): (number | null)[] =>
    shedIds.map((shed) =>
      ds.temperature.find((t) => t.shed === shed && t.position === pos.id)?.mean ?? null)

  return [...groups.entries()]
    // 层从高到低。用这一层任意一点的高度代表整层 —— 同层的 z 是同一个数。
    .sort((a, b) => b[1][0].z - a[1][0].z)
    .map(([layer, list], i) => ({
      layer,
      color: p[LAYER_SLOTS[i] ?? 'inkMuted'],
      points: list
        .slice()
        .sort((a, b) => a.x - b.x)
        .map((pos) => [pos.x, pos.z, ds.point_codes[pos.id] ?? '',
          ...means(pos)] as PointDatum),
    }))
}
