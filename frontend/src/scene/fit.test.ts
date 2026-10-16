/**
 * 相机取景：**整卷都得在画面里**。
 *
 * 2026-10-09 实机截图发现的：棚体是一条 18 m 长、2.1 × 1.3 m 粗的针，
 * 而相机只按「长度」估了个距离。斜着看的时候，**近的那一端离相机比中段近得多**
 * （实测 9.5 m 对 16.9 m），于是它被放大约 2.6 倍，一头扎出画面下沿 ——
 * 1280 与 1600 两个宽度下截出来的图里，近端都是齐刷刷被削平的。
 *
 * 这里的断言**不是**复核 `fit.ts` 那套手算 —— 那只是把同一份推导抄两遍。
 * 投影片用的是 `three` 自己的 `PerspectiveCamera` 与 `Vector3.project`：
 * 一个真相机、真矩阵，再把八个角投到 NDC 上看有没有出界。
 */
import * as THREE from 'three'
import { describe, expect, it } from 'vitest'

import { FIT_DIR, FIT_FOV_DEG, fitCamera, type WorldBox } from './fit'

/**
 * 真实载荷的包围盒（2026-10-09 实机取的那一卷）：
 * 数据 x 0→2.1、z（高）0→1.3、棚长 y 0→18，世界坐标是 (x, z, y)。
 */
const REAL: WorldBox = { center: [1.05, 0.65, 9], half: [1.05, 0.65, 9] }

function corners(b: WorldBox): THREE.Vector3[] {
  const out: THREE.Vector3[] = []
  for (const sx of [-1, 1]) {
    for (const sy of [-1, 1]) {
      for (const sz of [-1, 1]) {
        out.push(new THREE.Vector3(
          b.center[0] + sx * b.half[0],
          b.center[1] + sy * b.half[1],
          b.center[2] + sz * b.half[2],
        ))
      }
    }
  }
  return out
}

/** 八个角投到 NDC 之后，离画面中心最远的那个（1 = 正好压在边上）。 */
function worstNdc(box: WorldBox, aspect: number): number {
  const { position, target } = fitCamera(box, aspect)
  const cam = new THREE.PerspectiveCamera(FIT_FOV_DEG, aspect, 0.01, 500)
  cam.position.set(...position)
  cam.lookAt(new THREE.Vector3(...target))
  cam.updateMatrixWorld(true)
  cam.updateProjectionMatrix()
  return Math.max(...corners(box).flatMap((c) => {
    const p = c.clone().project(cam)
    return [Math.abs(p.x), Math.abs(p.y)]
  }))
}

describe('相机取景把整卷框进画面', () => {
  // 两个宽度各来一遍：1280 那一屏中栏 468 px、1600 那一屏 788 px。
  //
  // ⚠️ 2026-10-16 起画布高**不再是一个常数**：页⑤ 那一屏把高度交给窗口分配，
  // `VolumeScene.vue` 里那一档的上下限是 200 / 460 px（页③ 仍是写死的 460）。
  // 两个宽度 × 那一档高度，比例落在 [468/460, 788/200] ≈ [1.02, 3.94] 里 ——
  // **最紧的那一头仍是 1280 那一屏配上最高的画布**，也就是下面第二个用例，
  // 所以这三个数不用改。真正兜住整段的其实是第三个（正方，1.0）：它比
  // 468/460 ≈ 1.017 还紧，而取景只随比例松、不随比例紧（比例越小画面越窄）。
  //
  // ⚠️ 高度那两条边界一旦被改动（**尤其是下限再往下压**），回来把这一段的
  // 算术重做一遍 —— 2026-10-09 那个「棚体近端扎出画面下沿」的 bug 正是随
  // 比例变的，而下限越低压出来的比例越宽，越宽这一组用例就越宽松：
  // 真出问题的是**窄**的那一头，也就是 1280 那一屏配上 460 的画布。
  it.each([
    ['1600 那一屏的中栏', 788 / 460],
    ['1280 那一屏的中栏', 468 / 460],
    ['正方（最窄可能遇到的比例）', 1],
  ])('%s：八个角都在画面里', (_name, aspect) => {
    expect(worstNdc(REAL, aspect)).toBeLessThanOrEqual(1)
  })

  it('不是靠「把相机拉得老远」凑出来的 —— 内容要占到大半幅', () => {
    // 退到天边也能让 `toBeLessThanOrEqual(1)` 通过，而那样画面上只剩一根牙签。
    expect(worstNdc(REAL, 788 / 460)).toBeGreaterThan(0.7)
  })

  it('看的角度没变：还是从 (0.45, 0.35, 0.75) 那个方向看', () => {
    // 这一条钉的是「只改距离、不改取景角度」—— 原来那套角度是既定的观感，
    // 修取景不该顺手把它也换了。
    const { position, target } = fitCamera(REAL, 1)
    const d = new THREE.Vector3(...position).sub(new THREE.Vector3(...target)).normalize()
    const want = new THREE.Vector3(...FIT_DIR).normalize()
    expect(d.x).toBeCloseTo(want.x, 10)
    expect(d.y).toBeCloseTo(want.y, 10)
    expect(d.z).toBeCloseTo(want.z, 10)
    expect(new THREE.Vector3(...position).distanceTo(new THREE.Vector3(...target)))
      .toBeGreaterThan(0)
  })

  it('只有一片场（厚度为零）时不崩、照样框得住', () => {
    // 退化输入：`planes` 只剩一片时这一卷在棚长方向上是**平的**，
    // 半厚为 0。一个除零或 NaN 会让相机飞到无穷远、画面全空，
    // 而那是「什么都没画」里最难查的一种。
    const flat: WorldBox = { center: [1.05, 0.65, 9], half: [1.05, 0.65, 0] }
    for (const v of [...fitCamera(flat, 788 / 460).position, ...fitCamera(flat, 788 / 460).target]) {
      expect(Number.isFinite(v)).toBe(true)
    }
    expect(worstNdc(flat, 788 / 460)).toBeLessThanOrEqual(1)
  })
})
