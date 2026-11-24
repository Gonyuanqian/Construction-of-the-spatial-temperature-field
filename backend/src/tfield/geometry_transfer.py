"""Experimental geometry transfer, NOT a size-conditioned thermal predictor.

Only the normalized reference arch is supported. A single section is repeated
along the requested length under an explicit uniformity assumption. This module
is exposed only through the explicit prototype runtime; it does not widen the
trained model's validated geometry bounds.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib
import json
import numbers

import numpy as np
import pandas as pd

from . import config as C
from .field.sample import sample_grid
from .independent_training import GEOMETRY, PROTOCOL, local_positions

POLICY = 'experimental_relative_section_uniform_length_v0'
MAX_GRID_VALUES = 2_000_000


@dataclass(frozen=True)
class HouseDimensions:
    length_m: float
    width_m: float
    height_m: float

    def __post_init__(self):
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, numbers.Real) or not np.isfinite(value) or not 0 < value <= 10_000:
                raise ValueError(f'{name} 必须是大于 0 且不超过 10000 的有限米数；这是原型数值限制，不是模型适用范围。')

    def roof(self, x):
        """Affine transfer of the reference arch; independent W/H scaling is not necessarily circular."""
        ref_x = np.asarray(x, float) / self.width_m * GEOMETRY['width_m']
        height = np.sqrt(np.maximum(C.ARCH_R**2-(ref_x-C.ARCH_XC)**2, 0)) + C.ARCH_K
        return height / GEOMETRY['height_m'] * self.height_m

    def contains(self, x, y, z):
        return (np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
                & (np.asarray(x) >= 0) & (np.asarray(x) <= self.width_m)
                & (np.asarray(y) >= 0) & (np.asarray(y) <= self.length_m)
                & (np.asarray(z) >= 0) & (np.asarray(z) <= self.roof(x)+1e-10*self.height_m))


@dataclass
class TransferredVolume:
    dimensions: HouseDimensions
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    section: np.ndarray
    mask: np.ndarray
    above_source_height: np.ndarray
    nodes: np.ndarray
    timestamp: str
    source_ref: str

    @property
    def field_ref(self):
        digest=hashlib.sha256()
        for values in (self.x,self.y,self.z,np.nan_to_num(self.section,nan=-1e30)):
            digest.update(values.tobytes())
        digest.update((POLICY+self.source_ref+self.timestamp).encode())
        return digest.hexdigest()

    def query(self, x, y, z):
        if not all(isinstance(v,numbers.Real) and not isinstance(v,bool) and np.isfinite(v) for v in (x,y,z)):
            raise ValueError('查询坐标须为有限数值。')
        result=dict(x=float(x),y=float(y),z=float(z),value=None,field_ref=self.field_ref,
            policy=POLICY,accuracy_validated=False)
        if not self.dimensions.contains(x,y,z):return result|dict(kind='outside')
        if z/self.dimensions.height_m > C.MAX_MEASURED_Z/GEOMETRY['height_m']+1e-10:
            return result|dict(kind='unmeasured')
        value=sample_grid(self.x,self.y,self.z,(x,y,z),lambda _:self.section,
                          lambda ix,iz:bool(self.above_source_height[iz,ix]))
        return result|dict(kind='value' if value is not None else 'unavailable',value=value)

    def payload(self):
        """Existing scene-compatible payload. Shell center is placement only, never a measured section."""
        dimensions=asdict(self.dimensions)
        usable=self.mask & ~self.above_source_height
        values=self.section[usable]
        mean=float(values.mean())
        rows=[[float(v) if np.isfinite(v) else None for v in row] for row in self.section]
        arch_x=np.unique(np.append(np.linspace(0,self.dimensions.width_m,129),C.ARCH_XC/GEOMETRY['width_m']*self.dimensions.width_m))
        section_ref=local_positions()
        return dict(t_index=0,time=self.timestamp,n_times=1,preset='experimental_transfer',monotonic=False,
            calibrated=False,mismatch_note='',artifact_note='',y_step=float(self.y[1]-self.y[0]),
            y_min=0.,y_max=float(self.dimensions.length_m),x_min=0.,x_max=float(self.dimensions.width_m),
            z_max=float(self.dimensions.height_m),shed_width=float(self.dimensions.width_m),shed_height=float(self.dimensions.height_m),
            max_measured_z=float(C.MAX_MEASURED_Z/GEOMETRY['height_m']*self.dimensions.height_m),
            vmin=float(values.min()),vmax=float(values.max()),mean=mean,
            x=self.x.tolist(),z=self.z.tolist(),arch=np.column_stack([arch_x,self.dimensions.roof(arch_x)]).tolist(),
            sheds=[dict(id='single_prototype',y=float(self.dimensions.length_m/2))],
            sensors=[],available_sheds=[],stripes=[[int(ix),int(iz)] for iz,ix in np.argwhere(self.above_source_height)],
            planes=[dict(y=float(y),measured=False,virtual_source=False,shed=None,values=rows,mean=mean) for y in self.y],
            field_ref=self.field_ref,elapsed_ms=0.,
            note='实验性参考横截面映射；沿棚长均匀展开，非纵向实测；其他尺寸的温度精度尚未验证。',
            transfer=dict(policy=POLICY,requested_dimensions=dimensions,reference_dimensions={k:GEOMETRY[k] for k in dimensions},
                temperature_policy='reference_field_mapping_no_size_response',longitudinal_policy='uniform_assumption_not_measured',
                section_y_m=None,shell_center_is_display_only=True,accuracy_validated=False,source_ref=self.source_ref),
            virtual_nodes=[dict(x=float(p[0]*self.dimensions.width_m),z=float(p[1]*self.dimensions.height_m),
                y=None,temperature=float(v),source='G_prediction',measured=False) for p,v in zip(section_ref,self.nodes)])


def build_transferred_volume(field_model, weather, node_temperatures, dimensions: HouseDimensions, *,
                             nx=43, nz=33, ny=13, allow_assumptions=False, source_ref=''):
    if allow_assumptions is not True:
        raise ValueError('须显式启用参考截面映射与纵向均匀假设，不能当作已验证的跨尺寸预测。')
    if not isinstance(dimensions,HouseDimensions):raise ValueError('须提供经过校验的棚体尺寸。')
    if getattr(field_model,'protocol',None)!=PROTOCOL or any(field_model.geometry.get(k)!=GEOMETRY[k] for k in ('length_m','width_m','height_m')):
        raise ValueError('成品与参考横截面协议或几何不一致。')
    if any(isinstance(n,bool) or not isinstance(n,numbers.Integral) or not 3<=n<=512 for n in (nx,nz,ny)) or nx*nz*ny>MAX_GRID_VALUES:
        raise ValueError('网格各轴须为 3 至 512 个点，总值数不得超过 2000000。')
    frame=weather.reset_index(drop=True)
    required=['bg_temp','bg_rh','bg_light']
    if len(frame)!=1 or not set(required+['timestamp']).issubset(frame.columns) or not np.isfinite(frame[required].to_numpy(float)).all():
        raise ValueError('构场需一个完整的外部气象时刻。')
    timestamp=pd.Timestamp(frame.timestamp.iloc[0])
    if pd.isna(timestamp) or frame.bg_light.iloc[0]<0 or not 0<=frame.bg_rh.iloc[0]<=100:
        raise ValueError('气象时刻、湿度或光照无效。')
    nodes=np.asarray(node_temperatures,float)
    if nodes.shape!=(8,) or not np.isfinite(nodes).all():raise ValueError('构场需单棚 8 个有限的虚拟点温度。')
    u,w=np.linspace(0,1,nx),np.linspace(0,1,nz)
    x,z=u*dimensions.width_m,w*dimensions.height_m
    X,Z=np.meshgrid(x,z)
    mask=dimensions.contains(X,0.,Z)
    relative=np.column_stack([np.tile(u,nz),np.repeat(w,nx)])
    section=np.full((nz,nx),np.nan)
    section[mask]=field_model.predict(frame,nodes[None,:],target_positions=relative[mask.ravel()])[0]
    if not np.isfinite(section[mask]).all():raise ValueError('模型返回了无效温度。')
    above=(Z/dimensions.height_m>C.MAX_MEASURED_Z/GEOMETRY['height_m']+1e-10)&mask
    return TransferredVolume(dimensions,x,np.linspace(0,dimensions.length_m,ny),z,section,mask,above,
        nodes.copy(),timestamp.isoformat(),str(source_ref))
