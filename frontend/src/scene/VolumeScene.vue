<script setup lang="ts">
/**
 * 三维棚体温度场（V7）的**画**这一半。
 *
 * 这一层只做 Three 的调用，**不做任何判断**：画哪几片、多透、空腔在哪、
 * 测点画在哪些棚上，全部来自 `spec`（`scene/volumeView.ts` 的纯函数，有测试）；
 * 悬停取哪个格点来自 `scene/hover.ts`（纯函数，有测试）；颜色来自
 * `charts/scale.ts`（有测试）。剩下的是建几何与贴纹理 —— 而它拿不到任何
 * 自动证据（jsdom 没有 canvas/WebGL，规格书 §8.2）。
 * 所以这里越薄越好，**任何一个能被搬进纯函数的判断都该搬走**。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

import type { VolumePayload } from '../api/types'
import { tempStops } from '../charts/scale'
import { readPalette } from '../design/palette'
import { markerPoint, solveHover, type HoverHit, type HoverPick } from './hover'
import { rasterPlane, stripeIndexSet } from './raster'
import type { VolumeSpec } from './volumeView'

const props = defineProps<{
  spec: VolumeSpec
  payload: VolumePayload
  /** 面板当前要显示的那个格点（钉住的优先）。记号画在它上面。 */
  picked: HoverPick | null
}>()

const emit = defineEmits<{
  hover: [p: HoverPick | null]
  pick: [p: HoverPick | null]
}>()

const palette = readPalette()

const host = ref<HTMLDivElement | null>(null)
/** 没有 WebGL 时说清楚为什么画不出来 —— 白屏是最坏的一种「正常」。 */
const unavailable = ref('')

const NO_WEBGL =
  '这台机器或浏览器没有可用的 WebGL 上下文，画不出三维棚体。二维断面视图不受影响。'

/** 剖切刀切到哪个 y 为止（米）。初值在载荷到位后设成最远的那一片，即不切。 */
const cutY = ref(0)

/**
 * 数据坐标 `(x, y, z)` → Three 的世界坐标。
 *
 * **世界 Y 是高度**（Three 的相机默认朝上），世界 Z 是棚位 y —— 于是拱截面
 * 落在 XY 平面上，`ExtrudeGeometry` 沿本地 +Z 拉伸正好就是棚长方向：
 * 拱壳、场平面、测点三者**一处都不用转**。少一次旋转就少一处能转错的自由。
 */
function toWorld(x: number, y: number, z: number): [number, number, number] {
  return [x, z, y]
}

function hasWebGL(): boolean {
  try {
    const c = document.createElement('canvas')
    return !!(c.getContext('webgl2') || c.getContext('webgl'))
  } catch {
    return false
  }
}

let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let renderer: THREE.WebGLRenderer | null = null
let controls: OrbitControls | null = null
let raycaster: THREE.Raycaster | null = null
let clipPlane: THREE.Plane | null = null
let planeGroup: THREE.Group | null = null
let marker: THREE.Mesh | null = null
/** 挂载时装起来的收尾工作。`onBeforeUnmount` 只调它，不自己攒状态 —— 收尾的东西和建立的东西写在一起，才不会被漏掉。 */
let teardown: (() => void) | null = null
/** 最近一次悬停解出的格点。点击钉住的就是它 —— 与面板上正显示的那个同源。 */
let lastHover: HoverPick | null = null
const owned: { dispose: () => void }[] = []

function track<T extends { dispose: () => void }>(x: T): T {
  owned.push(x)
  return x
}

/** 拱截面：载荷给的折线，沿底边封口。**前端不重算 z(x)。** */
function archShape(arch: [number, number][]): THREE.Shape {
  const s = new THREE.Shape()
  s.moveTo(arch[0][0], arch[0][1])
  for (const [x, z] of arch.slice(1)) s.lineTo(x, z)
  s.lineTo(arch[arch.length - 1][0], 0)
  s.lineTo(arch[0][0], 0)
  s.closePath()
  return s
}

function buildShells(): void {
  const { arch, shellYs, shellLength } = props.spec
  if (!scene || arch.length < 2) return
  const shape = archShape(arch)
  const geo = track(new THREE.ExtrudeGeometry(shape, { depth: shellLength, bevelEnabled: false }))
  const mat = track(new THREE.MeshBasicMaterial({
    color: new THREE.Color(palette.steel),
    transparent: true,
    opacity: 0.16,
    side: THREE.DoubleSide,
    depthWrite: false,
  }))
  for (const y of shellYs) {
    const mesh = new THREE.Mesh(geo, mat)
    // 几何从本地 z=0 拉到 z=shellLength，而壳要**居中**在棚位上 ——
    // 数据集说的是「这棚在 y = 3」，不是「这棚从 1 米开始铺 4 米」。
    mesh.position.z = y - shellLength / 2
    scene.add(mesh)
  }
  // 棚肋：每个壳两端各一圈，让「长度」看得出来。
  const edgeMat = track(new THREE.LineBasicMaterial({
    color: new THREE.Color(palette.steel), transparent: true, opacity: 0.5,
  }))
  const edgeGeo = track(new THREE.EdgesGeometry(geo))
  for (const y of shellYs) {
    for (const z of [y - shellLength / 2, y + shellLength / 2]) {
      const line = new THREE.LineSegments(edgeGeo, edgeMat)
      line.position.z = z
      scene.add(line)
    }
  }
}

function buildPlanes(): void {
  if (!scene) return
  if (planeGroup) {
    scene.remove(planeGroup)
    planeGroup.traverse((o) => {
      const m = o as THREE.Mesh
      if (m.geometry) m.geometry.dispose()
      const mat = m.material as THREE.MeshBasicMaterial | undefined
      if (mat) {
        mat.map?.dispose()
        mat.dispose()
      }
    })
  }
  const group = new THREE.Group()
  planeGroup = group
  scene.add(group)

  const stops = tempStops()
  const { vmin, vmax, planes } = props.spec
  const nx = props.payload.x.length
  const nz = props.payload.z.length
  const blank = stripeIndexSet(props.spec.cavity, nx)
  const spanX = props.payload.x[nx - 1] - props.payload.x[0]
  const spanZ = props.payload.z[nz - 1] - props.payload.z[0]
  const midX = (props.payload.x[0] + props.payload.x[nx - 1]) / 2
  const midZ = (props.payload.z[0] + props.payload.z[nz - 1]) / 2

  for (const pl of planes) {
    const values = props.payload.planes[pl.planeIndex].values
    const raster = rasterPlane(values, vmin, vmax, stops, blank)
    const tex = new THREE.DataTexture(raster.data, raster.width, raster.height, THREE.RGBAFormat)
    // `flipY` 保持默认的 false：`rasterPlane` 的第 0 行就是 `values[0]`，
    // 而 `PlaneGeometry` 的 v=0 在本地 Y 最小处 —— 两边同向，谁都不用翻。
    tex.flipY = false
    tex.colorSpace = THREE.SRGBColorSpace
    tex.magFilter = THREE.LinearFilter
    tex.minFilter = THREE.LinearFilter
    tex.needsUpdate = true

    const geo = new THREE.PlaneGeometry(spanX, spanZ)
    const mat = new THREE.MeshBasicMaterial({
      map: tex,
      transparent: true,
      opacity: pl.opacity,
      side: THREE.DoubleSide,
      depthWrite: false,
      // 剖切刀：Three 自带，很便宜。切的是**片**，不移除。
      clippingPlanes: clipPlane ? [clipPlane] : [],
      clipShadows: false,
    })
    const mesh = new THREE.Mesh(geo, mat)
    mesh.position.set(midX, midZ, pl.y)
    mesh.renderOrder = pl.planeIndex
    mesh.userData.planeIndex = pl.planeIndex
    group.add(mesh)
  }
}

function buildSensors(): void {
  if (!scene) return
  const geo = track(new THREE.SphereGeometry(0.028, 10, 8))
  const mat = track(new THREE.MeshBasicMaterial({ color: new THREE.Color(palette.ink) }))
  for (const s of props.spec.sensorSheds) {
    for (const p of s.points) {
      const dot = new THREE.Mesh(geo, mat)
      dot.position.set(...toWorld(p.x, s.y, p.z))
      scene.add(dot)
    }
  }
}

function buildMarker(): void {
  if (!scene) return
  const geo = track(new THREE.SphereGeometry(0.045, 14, 10))
  const mat = track(new THREE.MeshBasicMaterial({
    color: new THREE.Color(palette.leaf), transparent: true, opacity: 0.9,
  }))
  marker = new THREE.Mesh(geo, mat)
  marker.visible = false
  scene.add(marker)
}

function syncMarker(): void {
  if (!marker) return
  const k = props.picked
  if (!k) {
    marker.visible = false
    return
  }
  const [x, y, z] = markerPoint(props.payload, k)
  marker.position.set(...toWorld(x, y, z))
  marker.visible = true
}

function fitCamera(): void {
  if (!camera || !controls) return
  const { payload } = props
  const cx = (payload.x[0] + payload.x[payload.x.length - 1]) / 2
  const cz = (payload.z[0] + payload.z[payload.z.length - 1]) / 2
  const cy = (payload.planes[0].y + payload.planes[payload.planes.length - 1].y) / 2
  const span = payload.planes[payload.planes.length - 1].y - payload.planes[0].y
  controls.target.set(cx, cz, cy)
  // 距离按整卷的长度给，保证一开始整卷都在画面里。
  camera.position.set(cx + span * 0.45, cz + span * 0.35, cy + span * 0.75)
  camera.updateProjectionMatrix()
  controls.update()
}

function resize(): void {
  const el = host.value
  if (!el || !renderer || !camera) return
  const w = el.clientWidth || 640
  const h = el.clientHeight || 420
  renderer.setSize(w, h, false)
  camera.aspect = w / h
  camera.updateProjectionMatrix()
}

function onPointerMove(e: PointerEvent): void {
  const el = host.value
  if (!el || !raycaster || !camera || !planeGroup || !clipPlane || !renderer) return
  // 收进一个局部常量：`clipPlane` 是模块级的 `let`，上面那句守卫的收窄
  // **传不进下面那个箭头函数**（闭包可能晚于一次重新赋值才跑，TS 不敢认）。
  // 不写这一行，`vue-tsc` 会在 `clipped` 那一行报 TS18047。
  const clip = clipPlane
  const r = renderer.domElement.getBoundingClientRect()
  const ndc = new THREE.Vector2(
    ((e.clientX - r.left) / r.width) * 2 - 1,
    -((e.clientY - r.top) / r.height) * 2 + 1,
  )
  raycaster.setFromCamera(ndc, camera)
  // `intersectObjects` 返回的次序就是**由近到远** —— `solveHover` 要的正是它。
  const hits: HoverHit[] = raycaster
    .intersectObjects(planeGroup.children, false)
    .map((h) => ({
      planeIndex: Number(h.object.userData.planeIndex ?? 0),
      // 世界坐标 (X, Y, Z) = 数据坐标 (x, z, y)。
      x: h.point.x,
      z: h.point.y,
      // ⚠️ `Raycaster` **不认** `clippingPlanes`：交点里会带着已经切掉、
      // 屏幕上根本看不见的那一片。这一行是这一版最容易漏掉的一行 ——
      // 漏了它，用户对着空处悬停会得到一个温度，而且不报任何错。
      clipped: clip.distanceToPoint(h.point) < 0,
    }))
  lastHover = solveHover(hits, props.payload.x, props.payload.z)
  emit('hover', lastHover)
}

function onClick(): void {
  // 钉住的**不是**鼠标此刻那一格，而是最近一次解出的那一格：
  // `pointermove` 与 `click` 之间鼠标可能已经动过了，而用户以为自己点的是
  // 屏幕上那个记号。用记号所指的那一格，两边才对得上。
  emit('pick', lastHover)
}

function onPointerLeave(): void {
  lastHover = null
  emit('hover', null)
}

onMounted(() => {
  const el = host.value
  if (!el || !hasWebGL()) {
    unavailable.value = NO_WEBGL
    return
  }
  const last = props.payload.planes.length - 1
  cutY.value = props.payload.planes[last].y

  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(38, 1, 0.01, 500)
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1))
  // 材质级的 `clippingPlanes` 要它，默认是关的。
  renderer.localClippingEnabled = true
  el.appendChild(renderer.domElement)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true

  raycaster = new THREE.Raycaster()
  // 世界 Z 是棚位 y；法向朝 −Z、常数是 cutY，于是 `distanceToPoint(p) < 0`
  // 恰好等价于「p 的棚位 y 大于 cutY」—— 切掉的那一侧就是刀面之外。
  clipPlane = new THREE.Plane(new THREE.Vector3(0, 0, -1), cutY.value)

  buildShells()
  buildPlanes()
  buildSensors()
  buildMarker()
  fitCamera()
  syncMarker()
  resize()

  const ro = new ResizeObserver(resize)
  ro.observe(el)
  renderer.setAnimationLoop(() => {
    controls?.update()
    if (scene && camera) renderer?.render(scene, camera)
  })
  teardown = () => {
    ro.disconnect()
    renderer?.setAnimationLoop(null)
    controls?.dispose()
    // `owned` 里是这一块自己建的几何与材质。Three 不管垃圾回收，
    // 不 dispose 的话每次换时刻都会漏一批 GPU 缓冲 —— 拖几下就卡死。
    for (const d of owned) d.dispose()
    renderer?.dispose()
    renderer?.domElement.remove()
  }
})

/**
 * 载荷一换就重建那叠平面。**`cutY` 它不动** —— 剖切刀切到哪里是用户设的，
 * 与换了个时刻无关；而 `clipPlane` 是同一个对象，改 `constant` 就够。
 */
watch(() => [props.spec, props.payload], () => {
  if (!scene) return
  buildPlanes()
  syncMarker()
})

watch(() => props.picked, syncMarker, { deep: true })

watch(cutY, (v) => {
  if (clipPlane) clipPlane.constant = v
})

onBeforeUnmount(() => {
  teardown?.()
  teardown = null
})
</script>

<template>
  <div class="scene-wrap">
    <div
      ref="host" class="scene" role="img"
      :aria-label="`棚体三维温度场，共 ${payload.planes.length} 片`"
      @pointermove="onPointerMove"
      @pointerleave="onPointerLeave"
      @click="onClick"
    />
    <p v-if="unavailable" class="note">{{ unavailable }}</p>
    <fieldset v-else class="cut">
      <legend>剖切刀（沿棚长 y）</legend>
      <input
        v-model.number="cutY" type="range"
        :min="payload.planes[0].y"
        :max="payload.planes[payload.planes.length - 1].y"
        :step="payload.y_step"
        aria-label="剖切刀"
      >
      <p class="num">切到 y = {{ cutY.toFixed(2) }} m 为止</p>
    </fieldset>
  </div>
</template>

<style scoped>
.scene-wrap { position: relative; }
.scene { width: 100%; height: 460px; cursor: crosshair; }
.scene :deep(canvas) { display: block; width: 100%; height: 100%; }
.cut { border: var(--rule); padding: var(--gap-s); margin: var(--gap-s) 0 0; font-size: var(--size-note); }
.cut input { width: 100%; }
</style>
