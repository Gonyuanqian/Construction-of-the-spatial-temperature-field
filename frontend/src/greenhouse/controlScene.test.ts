// @vitest-environment node
import { expect, it } from 'vitest'
import { Group, InstancedMesh, Matrix4, Mesh, Vector3 } from 'three'
import { buildControlOverlay } from './controlScene'
import { buildDesignModel, disposeDesignModel } from './designScene'
import { controlOverview } from '../test/controlFixture'

it('only lights the active zone, then clears effects on the existing geometry after stopping', () => {
  const { spec, layout, devices } = controlOverview()
  const lamp = devices.find(device => device.kind === 'lighting')!
  const beds = [
    { x: 1, y: 1, width: 1, length: 15 },
    { x: 4, y: 1, width: 1, length: 15 },
  ]
  const overlay = buildControlOverlay(spec, { ...layout, beds }, { width: 6, length: 18, height: 2.4 },
    { frame: 'white', lamp: 'gold', water: 'cyan' })
  try {
    const view = overlay.root.children.filter((object): object is Group =>
      object instanceof Group && object.children.some(child => child instanceof Mesh && child.geometry.type === 'PlaneGeometry'))
    const active = { ...lamp, zone_key: 'b' as const, state: { running: true, brightness_percent: 60 } }
    overlay.update([{ ...lamp, zone_key: 'all' }, active])
    expect(view).toHaveLength(6)
    expect(view.filter(object => object.children.some(child => child instanceof Mesh && child.geometry.type === 'PlaneGeometry' && child.visible)))
      .toEqual(view.filter(object => object.position.x > 0))
    expect(overlay.anchorFor(active)?.x).toBeGreaterThan(0)
    overlay.update([{ ...active, state: { running: false } }])
    expect(view.every(object => object.children.some(child => child instanceof Mesh && child.geometry.type === 'PlaneGeometry' && !child.visible))).toBe(true)
  } finally {
    overlay.dispose()
  }
})

it('uses the saved design fixture positions in the equipment scene', () => {
  const { spec, layout, devices } = controlOverview()
  const point = { x: 1.2, y: 5, z: 1.5 }
  const design = { ...spec, lighting: {enabled:true, spacing_m:2, mounting_height_m:1.5} }
  const preview = { ...layout, lights:[point] }
  const model = buildDesignModel(design, preview, {
    frame:'white', ground:'black', cover:'cyan', soil:'brown', plant:'green',
    plantLight:'lime', path:'gray', pipe:'blue', lamp:'gold',
  })
  const overlay = buildControlOverlay(design, preview, model, { frame: 'white', lamp: 'gold', water: 'cyan' })
  try {
    const lamp = devices.find(device => device.kind === 'lighting')!
    const fixtures = model.root.getObjectByName('补光灯') as InstancedMesh
    expect(fixtures.count).toBe(1)
    const transform = new Matrix4()
    fixtures.getMatrixAt(0, transform)
    const position = new Vector3().setFromMatrixPosition(transform)
    const anchor = overlay.anchorFor(lamp)!
    expect(position.distanceTo(anchor)).toBeLessThan(1e-6)
    expect(anchor.y).toBe(1.5)
  } finally {
    overlay.dispose()
    disposeDesignModel(model.root)
  }
})
