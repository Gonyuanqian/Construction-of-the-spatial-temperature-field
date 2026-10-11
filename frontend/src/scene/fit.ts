/**
 * 相机取景：**把整卷框进画面**。
 *
 * 这一层只做算术，不碰 Three（`VolumeScene.vue` 那一层照着结果摆相机）——
 * 于是「八个角都在画面里」这条**能被断言**，而画面本身不能
 * （jsdom 没有 canvas/WebGL，规格书 §8.2）。
 *
 * ⚠️ 2026-10-09：**这一条是实机截图逼出来的**。原来只有一句
 * 「距离按整卷的长度给」——`position = 中心 + 方向 × 棚长`。棚体是一条
 * 18 m 长、2.1 × 1.3 m 粗的**针**，而那句话把相机等同于「离中心多远」，
 * 完全没管针的两头。斜着看时**近的那一端**离相机比中段近得多
 * （实测 9.5 m 对 16.9 m），被放大约 2.6 倍，一头扎出画面下沿：
 * 1600 与 1280 两个宽度下截的图里，近端都是齐刷刷被削平的，
 * 用 `three` 自己的投影矩阵复核，近端那个角落的 NDC 是 **1.12**（1 就是边）。
 */
export interface WorldBox {
  /** 轴对齐包围盒的中心（世界坐标）。 */
  center: [number, number, number]
  /** 三个方向上的半长。 */
  half: [number, number, number]
}

/**
 * 相机**相对目标的偏移方向**。与改动前那一句里的 `(0.45, 0.35, 0.75)` 同向 ——
 * 这次只改「多远」，不改「从哪个方向看」：那个角度是既定的观感。
 */
export const FIT_DIR: [number, number, number] = [0.45, 0.35, 0.75]

/** 竖直视场角（度）。`VolumeScene` 建 `PerspectiveCamera` 时用同一个数。 */
export const FIT_FOV_DEG = 38

/**
 * 内容最多占到半幅的**这个比例**。
 *
 * 不贴边就完事：3.1 版那种「一个角正好压在边线上」在画面上读起来像是被裁了
 * （而它确实差一个像素就会被裁）。留 8% 的余量，也让「刚刚好」不再依赖
 * 画布量出来的那个像素宽高比。
 */
const MARGIN = 0.08

/** 近裁剪面。与 `VolumeScene` 建相机时给的一致。 */
const NEAR = 0.01

const dot = (a: readonly number[], b: readonly number[]): number =>
  a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
const cross = (a: readonly number[], b: readonly number[]): [number, number, number] =>
  [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
const unit = (a: readonly number[]): [number, number, number] => {
  const n = Math.hypot(a[0], a[1], a[2])
  return [a[0] / n, a[1] / n, a[2] / n]
}

/**
 * 在给定的取景方向上，算出「八个角都进画面」的**最小距离**。
 *
 * 不是一个一个角去试 —— 每个角给出一条**下界**，取最大：
 *
 *     该角离视线轴的距离 ÷ 半幅的张角 ≤ 它到相机的深度
 *
 * 而深度 = 相机到中心的距离 `d` 加上该角沿视线的偏移 `t`（朝向相机为负）。
 * 于是 `d ≥ 该角的投影 ÷ 张角 − t`。盒子是凸的，八个角都满足就整盒都满足。
 *
 * 「近端被放大」这件事**不用特判**，它自己就在式子里：近端那几个角的 `t` 是负的，
 * 右边因此变大，把相机推远。原先那句话缺的正是这个 `t`。
 */
export function fitCamera(
  box: WorldBox, aspect: number,
): { position: [number, number, number]; target: [number, number, number] } {
  const u = unit(FIT_DIR)
  // 视线方向（相机 → 目标）与它正交的两根轴。`right` 与世界上方叉出来，
  // 再叉回去得到相机自己的「上」—— 这样世界不会翻过来（`up[1] > 0`）。
  const f: [number, number, number] = [-u[0], -u[1], -u[2]]
  const right = unit(cross(f, [0, 1, 0]))
  const up = cross(right, f)

  const kY = Math.tan((FIT_FOV_DEG * Math.PI) / 360) * (1 - MARGIN)
  const kX = kY * aspect

  let d = 0
  for (const sx of [-1, 1]) {
    for (const sy of [-1, 1]) {
      for (const sz of [-1, 1]) {
        const v = [sx * box.half[0], sy * box.half[1], sz * box.half[2]]
        const t = dot(v, f)
        d = Math.max(
          d,
          Math.abs(dot(v, right)) / kX - t,
          Math.abs(dot(v, up)) / kY - t,
          // 退化输入（厚度为零的一卷）也要有解：至少不能站到近裁剪面里。
          NEAR - t,
        )
      }
    }
  }

  return {
    target: box.center,
    position: [
      box.center[0] + u[0] * d,
      box.center[1] + u[1] * d,
      box.center[2] + u[2] * d,
    ],
  }
}

/** 拿一个包围盒量出它的中心与半长 —— 与 `fitCamera` 配对，省得调用处自己减。 */
export function boxOf(
  lo: readonly [number, number, number],
  hi: readonly [number, number, number],
): WorldBox {
  return {
    center: [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2],
    half: [Math.abs(hi[0] - lo[0]) / 2, Math.abs(hi[1] - lo[1]) / 2, Math.abs(hi[2] - lo[2]) / 2],
  }
}
