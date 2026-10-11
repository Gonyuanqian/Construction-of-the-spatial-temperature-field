/**
 * 轴上的**类别名**：收干净了再印。
 *
 * 页③ 那两张图的轴是 `type: 'category'`，类别名就是格点原值 `String()` 出来的
 * （`payload.x.map(String)`）。那些串是**身份**，不是给人看的字 —— 实测点的散点
 * 与拱线都按这个字符串在类别表里找位置，改一个字就找不到。
 *
 * 可它们**同时也是屏上印的字**，而 Python 那边 `np.arange(0, 2.1, 0.05)` 出来的
 * 不是 0.05 的整数倍：第 3 个是 `0.15000000000000002`。`String()` 之后那串尾巴
 * 原样进了类别名，也就原样印在了轴上。页③ 一屏三张并排、每张的 y 轴都占不满
 * 自己那一格，于是那串尾巴**溢出格子宽度、爬到左边那张温度场上** ——
 * 远看像花屏（用户报的就是这个）。
 *
 * 所以：`data` 原样留着不动，只在 `axisLabel.formatter` 里收。身份与印字分开。
 *
 * 两位小数够用：网格步长三档是 0.10 / 0.05 / 0.02（`tfield/field/grid.py`
 * 的 `GRID_PRESETS`），最细那档 0.02 恰好要两位。收完再把尾随的零去掉，
 * 于是 `1.30` 印成 `1.3`、`1.00` 印成 `1`。
 */
export function tickLabel(v: string): string {
  const n = Number(v)
  // 不是数的类别名（空串、`'p1'` 这种）原样放回去。`String(NaN)` 是「NaN」，
  // 那比原来那串尾巴更难解释。
  if (v.trim() === '' || !Number.isFinite(n)) return v
  return String(Number(n.toFixed(2)))
}
