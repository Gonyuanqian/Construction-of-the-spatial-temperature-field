import type { VolumePayload } from '../api/types'

/** 有效网格单元的外表面；不跨越 null 或无测量带连接。坐标为 Three 的 x,z,y。 */
export function solidSurface(payload: VolumePayload, blank: ReadonlySet<number>) {
  const nx = payload.x.length, nz = payload.z.length, ny = payload.planes.length
  const corners = [[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,1],[1,0,1],[1,1,1],[0,1,1]] as const
  const valid = (x: number, z: number, y: number) => x >= 0 && z >= 0 && y >= 0 && x < nx-1 && z < nz-1 && y < ny-1 && corners.every(([dx,dz,dy]) => {
    const v = payload.planes[y+dy].values[z+dz][x+dx]
    return v !== null && Number.isFinite(v) && !blank.has((z+dz)*nx+x+dx)
  })
  const faces = [
    { delta: [-1,0,0], ids: [0,3,7,4] }, { delta: [1,0,0], ids: [1,5,6,2] },
    { delta: [0,-1,0], ids: [0,4,5,1] }, { delta: [0,1,0], ids: [3,2,6,7] },
    { delta: [0,0,-1], ids: [0,1,2,3] }, { delta: [0,0,1], ids: [4,7,6,5] },
  ]
  const positions: number[] = [], temperatures: number[] = []
  for (let y=0;y<ny-1;y++) for (let z=0;z<nz-1;z++) for (let x=0;x<nx-1;x++) {
    if (!valid(x,z,y)) continue
    for (const {delta,ids} of faces) {
      if (valid(x+delta[0],z+delta[1],y+delta[2])) continue
      for (const i of [ids[0],ids[1],ids[2],ids[0],ids[2],ids[3]]) {
        const [dx,dz,dy] = corners[i]
        positions.push(payload.x[x+dx],payload.z[z+dz],payload.planes[y+dy].y)
        temperatures.push(payload.planes[y+dy].values[z+dz][x+dx]!)
      }
    }
  }
  return { positions, temperatures }
}
