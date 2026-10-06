/**
 * 拱壳**跟着「棚体示意长度」走**（终审 C1）。
 *
 * 画面本身在 jsdom 里测不了（没有 WebGL，规格书 §8.2），但「壳长变了要重画壳」
 * 这条**接线**能测 —— 把 `three` 换成一堆记账用的假件，然后读**场景里留下了什么**。
 * 这比读组件内部的调用次数硬：断言的是「场景里有几个按 6 m 拉伸的壳、
 * 旧的还在不在」，也就是用户拖滑块之后画面上真正发生的事。
 *
 * 两个具体的坑各有一条断言：
 * - `buildShells` 原来只在 `onMounted` 里调过一次，滑块**改不动壳**；
 * - 壳是 `scene.add` 上去的，`scene.add` 只加不删 —— 重画之前不摘掉旧的那批，
 *   拖一次就叠一层壳，而且那批几何与材质再也没人 dispose。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'

import { makeVolumePayload } from '../test/fixtures'
import { buildVolumeSpec } from './volumeView'

/**
 * 假 three 记下的账。
 *
 * 用 `vi.hoisted` 而不是普通的模块级变量：`vi.mock` 的工厂被提到文件最上面，
 * 而它在**导入 `VolumeScene.vue` 的时候**就跑了 —— 那时候文件里的 `const`
 * 还全在死区里，直接引用会抛 `ReferenceError`。
 */
const rec = vi.hoisted(() => ({
  /** 每次建壳时 `ExtrudeGeometry` 拿到的拉伸长度，按调用次序。 */
  depths: [] as number[],
  /** 一共造了几张场纹理 —— 一张一片，也就是「那叠平面重建了几次」。 */
  textures: 0,
  /** 最近建的那个场景。组件一次只建一个。 */
  scene: null as any,
}))

vi.mock('three', () => {
  class Vec {
    x = 0
    y = 0
    z = 0
    set(x: number, y: number, z: number) {
      this.x = x
      this.y = y
      this.z = z
      return this
    }
  }

  /** 场景图里的一节。`kind` 是给测试认几何用的标签。 */
  class Node {
    children: Node[] = []
    position = new Vec()
    userData: Record<string, unknown> = {}
    add(o: Node) { this.children.push(o) }
    remove(o: Node) { this.children = this.children.filter((c) => c !== o) }
    traverse(cb: (o: Node) => void) {
      cb(this)
      for (const c of this.children) c.traverse(cb)
    }
  }
  class Geo {
    kind = ''
    dispose() {}
  }
  class Mat {
    map: any = null
    dispose() {}
  }
  class Mesh extends Node {
    geometry: Geo
    material: Mat
    visible = true
    constructor(geometry: Geo, material: Mat) {
      super()
      this.geometry = geometry
      this.material = material
    }
  }
  class Group extends Node {}

  class Scene extends Node {
    constructor() {
      super()
      rec.scene = this
    }
  }

  class ExtrudeGeometry extends Geo {
    depth: number
    constructor(_shape: unknown, opts: { depth: number }) {
      super()
      this.kind = 'extrude'
      this.depth = opts.depth
      rec.depths.push(opts.depth)
    }
  }
  class EdgesGeometry extends Geo {
    constructor(_base: unknown) {
      super()
      this.kind = 'edges'
    }
  }
  class PlaneGeometry extends Geo {
    constructor(_w: number, _h: number) {
      super()
      this.kind = 'plane'
    }
  }
  class SphereGeometry extends Geo {
    constructor(..._a: number[]) {
      super()
      this.kind = 'sphere'
    }
  }
  class DataTexture {
    constructor(..._a: unknown[]) { rec.textures += 1 }
  }
  class Color {
    hex: string
    constructor(hex: string) { this.hex = hex }
  }

  return {
    Scene, Group, Mesh, Vec,
    ExtrudeGeometry, EdgesGeometry, PlaneGeometry, SphereGeometry, DataTexture, Color,
    Vector2: Vec,
    Vector3: Vec,
    PerspectiveCamera: class extends Node {
      aspect = 1
      updateProjectionMatrix() {}
    },
    WebGLRenderer: class {
      domElement = document.createElement('canvas')
      localClippingEnabled = false
      setPixelRatio() {}
      setSize() {}
      setAnimationLoop() {}
      render() {}
      dispose() {}
    },
    Raycaster: class {
      setFromCamera() {}
      intersectObjects() { return [] }
    },
    Plane: class {
      constant: number
      constructor(_n: unknown, constant: number) { this.constant = constant }
      distanceToPoint() { return 1 }
    },
    Shape: class {
      moveTo() {}
      lineTo() {}
      closePath() {}
    },
    MeshBasicMaterial: Mat,
    LineBasicMaterial: Mat,
    LineSegments: Mesh,
    RGBAFormat: 1023,
    SRGBColorSpace: 'srgb',
    LinearFilter: 1006,
    DoubleSide: 2,
  }
})

vi.mock('three/examples/jsm/controls/OrbitControls.js', () => ({
  OrbitControls: class {
    target = { x: 0, y: 0, z: 0, set() {} }
    enableDamping = false
    update() {}
    dispose() {}
  },
}))

import VolumeScene from './VolumeScene.vue'

/**
 * 与 `VolumeScene.test.ts` 同一套环境夹具：调色板要能读到底色（读不到就抛），
 * 而 `ResizeObserver` 是 jsdom 里没有的。
 *
 * 另外把 `getContext` 顶掉：组件用「造一个 canvas 试取上下文」来判断有没有
 * WebGL，jsdom 那一支会返回 null **并往控制台喷一条 not implemented** ——
 * 这里返回一个空对象，让那条路通到假 three 上。
 */
function installEnvironment(): void {
  const root = document.documentElement
  root.style.setProperty('--paper', '#F7F6F2')
  root.style.setProperty('--ink', '#211F1C')
  root.style.setProperty('--ink-muted', '#5C5850')
  root.style.setProperty('--steel', '#DEDCD6')
  root.style.setProperty('--leaf', '#14532D')
  root.style.setProperty('--leaf-soft', '#E7EFE9')
  root.style.setProperty('--net', '#0B0F0D')
  root.style.setProperty('--layer-top', '#C44E52')
  root.style.setProperty('--layer-mid', '#4C72B0')
  root.style.setProperty('--layer-low', '#55A868')
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  })
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as never)
}

/** 场景里所有带几何的东西（组也走一遍）。 */
function parts(scene: unknown): any[] {
  const out: any[] = []
  const walk = (o: any) => {
    out.push(o)
    for (const c of o.children ?? []) walk(c)
  }
  walk(scene)
  return out
}

/** 拱壳那一批：壳体 + 棚肋。 */
function shells(scene: unknown): any[] {
  return parts(scene).filter((o) =>
    o.geometry?.kind === 'extrude' || o.geometry?.kind === 'edges')
}

async function mountScene(shellLength: number) {
  const payload = makeVolumePayload()          // 三座棚：y = 3 / 9 / 15
  const w = mount(VolumeScene, {
    props: { payload, spec: buildVolumeSpec(payload, shellLength), picked: null },
  })
  await nextTick()
  return { w, payload }
}

/** 只动壳长：`payload` 原样不动，`spec` 按新长度重算 —— 与滑块做的事一样。 */
async function dragSliderTo(w: Awaited<ReturnType<typeof mountScene>>, len: number) {
  rec.depths.length = 0
  await w.w.setProps({ spec: buildVolumeSpec(w.payload, len) })
  await nextTick()
}

describe('拱壳跟着「棚体示意长度」走（C1）', () => {
  beforeEach(() => {
    installEnvironment()
    rec.depths.length = 0
    rec.textures = 0
  })

  it('滑块一动，壳按新长度重画，**旧的那批先摘掉**', async () => {
    const m = await mountScene(4)
    // 三座棚共用一份几何：拉伸长度只该造一份，不是每座棚一份。
    expect(rec.depths, '挂载时就没按滑块给的 4 m 建壳').toEqual([4])

    await dragSliderTo(m, 6)

    expect(rec.depths, '壳长从 4 换到 6，拱壳没有重建（滑块是死的）').toEqual([6])
    // 旧的摘掉了：场景里只剩一批壳体（3 座棚）+ 六个棚肋端圈。
    // 没摘的话这里是 6 和 12 —— 拖几下就叠出一摞壳。
    const bodies = parts(rec.scene).filter((o) => o.geometry?.kind === 'extrude')
    expect(bodies).toHaveLength(3)
    expect(shells(rec.scene)).toHaveLength(9)
    expect(
      bodies.every((mesh) => mesh.geometry.depth === 6),
      '场景里还留着按 4 m 拉伸的壳',
    ).toBe(true)
  })

  it('棚肋端圈跟着挪：6 m 的壳从棚位两侧各伸出 3 m', async () => {
    const m = await mountScene(4)
    await dragSliderTo(m, 6)
    // 3 m 那座从 0 到 6，9 m 那座从 6 到 12，15 m 那座从 12 到 18。
    // 读的是**场景里现存的**那些，不是「造过几个」—— 旧的没摘掉就会多出一倍。
    expect(
      parts(rec.scene).filter((o) => o.geometry?.kind === 'edges').map((o) => o.position.z),
    ).toEqual([0, 6, 6, 12, 12, 18])
  })

  it('**只动壳长时，那叠场平面不重画**（一片一张纹理）', async () => {
    // 37 片就是 37 张 DataTexture。壳长一个数都没进平面，跟着重画是白扔 ——
    // 而滑块是用户会一路拖过去的控件。
    const m = await mountScene(4)
    expect(rec.textures, '挂载时建了 2 片（夹具那一卷）').toBe(2)
    await dragSliderTo(m, 6)
    expect(rec.textures, '壳长变了却把那叠平面重画了一遍').toBe(2)
  })

  it('换载荷时壳也跟着重建（拱形与棚位是载荷给的）', async () => {
    const m = await mountScene(4)
    rec.depths.length = 0
    const next = makeVolumePayload({ t_index: 13, time: '2026-07-23T12:10:00' })
    await m.w.setProps({ payload: next, spec: buildVolumeSpec(next, 4) })
    await nextTick()
    expect(rec.depths, '换了载荷却没重建壳').toEqual([4])
    expect(shells(rec.scene), '新旧两批壳叠在场景里').toHaveLength(9)
  })
})
