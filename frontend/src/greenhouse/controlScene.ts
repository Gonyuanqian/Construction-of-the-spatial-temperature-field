import * as THREE from 'three'
import type { ControlDevice, DeviceKind, ZoneKey } from '../api/greenhouseControl'
import type { DesignPreview, DesignSpec } from '../api/greenhouseDesigns'
import { disposeDesignModel, lightingFixtureLength } from './designScene'

type Position = { x: number; y: number; z: number }
type Zone = Exclude<ZoneKey, 'all'>
type Slot = {
  kind: DeviceKind
  zone: Zone
  anchor: THREE.Vector3
  object: THREE.Object3D
  show: (device?: ControlDevice) => void
  step?: (seconds: number, device: ControlDevice) => void
  running?: ControlDevice
}

function applies(device: ControlDevice, slot: Slot) {
  return device.kind === slot.kind && (device.zone_key === 'all' || device.zone_key === slot.zone)
}

export function buildControlOverlay(
  spec: DesignSpec, layout: DesignPreview,
  size: { width: number; length: number; height: number },
  palette: { frame: string; water: string; lamp: string },
) {
  const { width, length, height } = size
  const root = new THREE.Group()
  const slots: Slot[] = []
  const zone = (x: number): Zone => x < width / 2 ? 'a' : 'b'
  const at = (point: Position) => new THREE.Vector3(point.x - width / 2, point.z, point.y - length / 2)
  const frame = new THREE.MeshStandardMaterial({ color: palette.frame, roughness: .65 })
  const fanBlade = new THREE.MeshStandardMaterial({ color: palette.water, roughness: .5 })
  const water = new THREE.MeshBasicMaterial({ color: palette.water, transparent: true, opacity: .82, depthWrite: false })
  const darkPipe = new THREE.LineBasicMaterial({ color: palette.water, transparent: true, opacity: .32 })
  const activePipe = new THREE.LineBasicMaterial({ color: palette.water, transparent: true, opacity: .95 })
  const lampsOff = new THREE.MeshBasicMaterial({ color: palette.frame })
  const droplet = new THREE.SphereGeometry(.028, 7, 5)
  const sprinklerHead = new THREE.CylinderGeometry(.065, .065, .065, 8)
  const configuredLamps = spec.lighting?.enabled ? layout.lights : undefined
  const lampLength = configuredLamps ? lightingFixtureLength(spec, layout) : Math.min(1.25, length * .24)
  const lampGeometry = new THREE.BoxGeometry(.13, .06, lampLength)
  const resources = [frame, fanBlade, water, darkPipe, activePipe, lampsOff, droplet, sprinklerHead, lampGeometry]
  const surface = spec.structure
  const bay = surface.type === 'multi_span' ? surface.span_width_m : width
  const eave = surface.type === 'multi_span' ? surface.eave_height_m : 0
  const roof = (x: number) => {
    const offset = (x % bay) / bay
    return eave + surface.arch_height_m * Math.sqrt(Math.max(0, 1 - (2 * offset - 1) ** 2))
  }

  function slot(kind: DeviceKind, point: Position, object: THREE.Object3D,
    show: Slot['show'], step?: Slot['step']) {
    root.add(object)
    slots.push({ kind, zone: zone(point.x), anchor: at(point), object, show, step })
  }

  // Geometry is created once per saved layout. A poll only updates materials and animation.
  for (const row of layout.rows.filter((_, i) => i % Math.ceil(layout.rows.length / 36) === 0)) {
    const from = { x: row.x, y: row.y_start, z: .12 }
    const to = { ...from, y: row.y_end }
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([at(from), at(to)]), darkPipe)
    const drops = Array.from({ length: 4 }, () => new THREE.Mesh(droplet, water))
    const group = new THREE.Group()
    group.add(line, ...drops)
    slot('drip', { ...from, y: (from.y + to.y) / 2 }, group, device => {
      line.material = device ? activePipe : darkPipe
      drops.forEach(drop => { drop.visible = !!device })
    }, seconds => {
      drops.forEach((drop, i) => {
        const fraction = (seconds * .42 + i / drops.length) % 1
        drop.position.copy(at({ ...from, y: THREE.MathUtils.lerp(from.y, to.y, fraction), z: .16 }))
      })
    })
  }

  for (const point of layout.sprinklers.filter((_, i) => i % Math.ceil(layout.sprinklers.length / 32) === 0)) {
    const z = Math.max(.1, Math.min(spec.irrigation.installation_height_m, roof(point.x) - .08))
    const group = new THREE.Group()
    group.position.copy(at({ ...point, z }))
    group.add(new THREE.Mesh(sprinklerHead, frame))
    const drops = Array.from({ length: 8 }, () => new THREE.Mesh(droplet, water))
    group.add(...drops)
    const radius = Math.min(.8, spec.irrigation.coverage_radius_m, width * .13)
    slot('sprinkler', { ...point, z }, group, device => {
      drops.forEach(drop => { drop.visible = !!device })
    }, seconds => {
      drops.forEach((drop, i) => {
        const phase = (seconds * 1.5 + i / drops.length) % 1
        const angle = i * 2.399 + seconds * .9
        drop.position.set(Math.cos(angle) * phase * radius, -(phase ** 2) * Math.max(.03, z - .12), Math.sin(angle) * phase * radius)
      })
    })
  }

  const lightPlacements = configuredLamps
    ? configuredLamps.filter((_, i) => i % Math.ceil(configuredLamps.length / 48) === 0)
      .map(point => ({ point, glowWidth: spec.planting.band_width_m * .94, glowLength: lampLength * 2 }))
    : layout.beds.filter((_, i) => i % Math.ceil(layout.beds.length / 8) === 0).flatMap(bed => {
      const x = bed.x + bed.width / 2
      return [.23, .5, .77].map(fraction => ({
        point: { x, y: bed.y + bed.length * fraction, z: Math.max(.16, roof(x) * .72) },
        glowWidth: bed.width * .94, glowLength: bed.length * .26,
      }))
    })
  for (const { point, glowWidth, glowLength } of lightPlacements) {
    const group = new THREE.Group()
    group.position.copy(at(point))
    const amber = new THREE.MeshBasicMaterial({ color: palette.lamp, transparent: true })
    resources.push(amber)
    const lamp = new THREE.Mesh(lampGeometry, lampsOff)
    const glow = new THREE.Mesh(
      new THREE.PlaneGeometry(glowWidth, glowLength),
      new THREE.MeshBasicMaterial({ color: palette.lamp, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }),
    )
    glow.rotation.x = -Math.PI / 2
    glow.position.y = .068 - point.z
    group.add(lamp, glow)
    slot('lighting', point, group, device => {
      const brightness = THREE.MathUtils.clamp(device?.state.brightness_percent ?? 60, 0, 100) / 100
      lamp.material = device ? amber : lampsOff
      amber.opacity = .5 + brightness * .5
      glow.visible = !!device
      glow.material.opacity = .06 + brightness * .24
    })
  }

  for (const x of [width * .27, width * .73]) {
    const z = Math.min(height * .58, roof(x) * .71)
    const point = { x, y: length - Math.min(.05, length / 10), z }
    const housing = new THREE.Group()
    housing.position.copy(at(point))
    const radius = Math.min(.28, z * .58, width * .09)
    const rim = new THREE.Mesh(new THREE.TorusGeometry(radius, radius * .10, 7, 18), frame)
    const rotor = new THREE.Group()
    for (let i = 0; i < 3; i++) {
      const holder = new THREE.Group()
      holder.rotation.z = i * Math.PI * 2 / 3
      const blade = new THREE.Mesh(new THREE.BoxGeometry(radius * .36, radius * .78, .045), frame)
      blade.position.y = radius * .46
      blade.rotation.z = -.28
      holder.add(blade)
      rotor.add(holder)
    }
    housing.add(rim, rotor)
    slot('ventilation', point, housing, device => {
      rotor.traverse(child => { if (child instanceof THREE.Mesh) child.material = device ? fanBlade : frame })
    }, (seconds, device) => {
      const speed = device.state.speed
      rotor.rotation.z = seconds * (speed === 'high' ? 9 : speed === 'low' ? 3 : 6)
    })
  }

  function update(devices: readonly ControlDevice[]) {
    const running = devices.filter(d => d.enabled && d.state.running)
    for (const item of slots) {
      item.object.visible = devices.some(d => applies(d, item))
      const candidates = running.filter(d => applies(d, item))
      // Overlapping lighting controls share a demo fixture. Show the strongest active setting.
      item.running = item.kind === 'lighting'
        ? candidates.reduce<ControlDevice | undefined>((best, d) =>
          !best || (d.state.brightness_percent ?? 60) > (best.state.brightness_percent ?? 60) ? d : best, undefined)
        : candidates[0]
      item.show(item.running)
    }
  }

  function anchorFor(device: ControlDevice) {
    const candidates = slots.filter(item => applies(device, item))
    const center = candidates.reduce((point, item) => point.add(item.anchor), new THREE.Vector3())
    if (!candidates.length) return null
    center.divideScalar(candidates.length)
    return candidates.reduce((best, item) =>
      item.anchor.distanceToSquared(center) < best.anchor.distanceToSquared(center) ? item : best).anchor
  }

  return {
    root, update, anchorFor,
    animate(seconds: number) {
      for (const item of slots) if (item.running) item.step?.(seconds, item.running)
    },
    dispose() {
      root.removeFromParent()
      disposeDesignModel(root, resources)
    },
  }
}
