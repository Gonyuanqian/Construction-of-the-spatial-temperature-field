/**
 * 残差诊断三连：残差 vs 昼夜 / 高度 / 棚长（规格书 §7.2）。
 *
 * ⚠️ 后两张**不是曲线**：这份数据在高度上只有 3 个取值、棚长上只有 7 个
 * （8 个点位 × 3 座棚），所以它们是 3 根和 7 根柱子。别以为图上少了东西。
 *
 * 每个箱画三样：平均残差（柱高）、箱内样本数、标准误（误差棒）。
 * 少了误差棒，任何一根短柱子都会被读成「这里系统地偏高/偏低」——
 * 柱子的高矮本身没有尺度。
 *
 * 纵轴一律是**折外残差 = 预测 − 实测**（正 = 报高了）。三张图的横轴不同，
 * 纵轴相同，所以三张并排读得通。
 */
import type { EChartsOption } from 'echarts'

import type { ResidualPanel } from '../../api/types'
import type { Palette } from '../../design/palette'

export function buildResidualOption(panel: ResidualPanel, p: Palette): EChartsOption {
  if (panel.bins.length === 0) {
    return {
      backgroundColor: 'transparent',
      title: {
        text: `${panel.label}：这一份数据上没有可用的箱`,
        left: 'center', top: 'middle',
        textStyle: { color: p.inkMuted, fontSize: p.chartTitle },
      },
      series: [],
    }
  }

  // 横轴标签**由后端给的位置拼出来**，前端不换算：`at` 就是那一箱的位置。
  const labels = panel.bins.map((b) => (b.at === null ? '—' : String(b.at)))
  // ⚠️ 无值的箱是 `null` 而**不是被过滤掉** —— 那一箱真实存在，
  // 从图上消失就是漏报（与页② 不藏最差折同一条房规）。
  const means = panel.bins.map((b) => b.mean)
  // 误差棒的数据：[箱号, 平均残差, 下界, 上界]。**只给两端都齐的箱** ——
  // `se` 是 null（箱内只有一个点，算不出标准误）或整箱无值时，这一箱就没有棒。
  // 这不是「藏起来」：柱子还在，只是它没有可报的精度。
  //
  // 写成显式的循环而不是 `.map(...).filter(...)`：后者要在表达式的右括号
  // 之后再写一个多行 `as` 断言，读起来要数括号才知道哪一个箱被留下。
  const errs: [number, number, number, number][] = []
  panel.bins.forEach((b, i) => {
    if (b.mean === null || b.se === null) return
    errs.push([i, b.mean, b.mean - b.se, b.mean + b.se])
  })

  return {
    backgroundColor: 'transparent',
    animation: false,
    // ⚠️ **有数据的时候这里不写 `title`** —— 图的名字由页面在画布**上方**的
    // `<h5>` 给出（`TrainView.vue`）。画布里的字是像素，读屏软件读不到，
    // 测试也读不到；两处各写一遍则是同一个名字上下并排出现两次。
    // 空态那支仍然要一个 `title` —— 那一句是**话**（为什么没有图），不是名字。
    grid: { left: 56, right: 16, top: 16, bottom: 52, containLabel: false },
    tooltip: {
      trigger: 'axis',
      formatter: (params: unknown) => {
        const arr = params as { dataIndex: number }[]
        if (!arr.length) return ''
        const b = panel.bins[arr[0].dataIndex]
        const mean = b.mean === null ? '无值' : `${b.mean.toFixed(4)} °C`
        const se = b.se === null ? '无值' : `± ${b.se.toFixed(4)}`
        return `${labels[arr[0].dataIndex]}：平均残差 ${mean}，标准误 ${se}，箱内 ${b.n} 个点`
      },
    },
    xAxis: {
      type: 'category', data: labels, name: panel.axis,
      nameLocation: 'middle', nameGap: 30,
      nameTextStyle: { color: p.inkMuted, fontSize: p.chartAxis },
      axisLine: { lineStyle: { color: p.steel } },
      axisTick: { show: false },
      axisLabel: { color: p.inkMuted, fontSize: p.chartAxis },
    },
    yAxis: {
      type: 'value', name: '残差 / °C',
      nameLocation: 'middle', nameGap: 44,
      nameTextStyle: { color: p.inkMuted, fontSize: p.chartAxis },
      axisLine: { lineStyle: { color: p.steel } },
      axisLabel: { color: p.inkMuted, fontSize: p.chartAxis },
      splitLine: { lineStyle: { color: p.steel, opacity: 0.25 } },
    },
    series: [
      {
        type: 'bar', silent: true, barCategoryGap: '22%',
        itemStyle: { color: p.steel },
        data: means,
        // 零线。没有它，读者看不出「这根柱子是往上还是往下」——
        // 纵轴的范围是数据撑出来的，零不一定落在看得见的地方。
        markLine: {
          silent: true, symbol: 'none',
          lineStyle: { color: p.inkMuted, type: 'dashed', width: 1 },
          label: { show: false },
          data: [{ yAxis: 0 }],
        },
      },
      {
        // 误差棒。`custom` 是因为它要画的是「一条竖线加两个帽子」，
        // 而不是一个数据点 —— 用 scatter 画不出来。
        type: 'custom', silent: true, z: 3,
        renderItem: (_params: unknown, api: any) => {
          const i = api.value(0)
          const top = api.coord([i, api.value(3)])
          const bot = api.coord([i, api.value(2)])
          const half = api.size([1, 0])[0] * 0.18
          const seg = (x1: number, y1: number, x2: number, y2: number) => ({
            type: 'line', shape: { x1, y1, x2, y2 },
            style: { stroke: p.ink, lineWidth: 1 },
          })
          return {
            type: 'group',
            children: [
              seg(top[0], top[1], bot[0], bot[1]),
              seg(top[0] - half, top[1], top[0] + half, top[1]),
              seg(bot[0] - half, bot[1], bot[0] + half, bot[1]),
            ],
          }
        },
        data: errs,
      },
    ],
  } as unknown as EChartsOption
}
