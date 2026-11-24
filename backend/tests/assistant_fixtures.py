"""Independent analytic fixture, not user/production observations."""
import math


def snapshot_body():
    xs=[0.,1.,2.]; ys=[0.,2.,4.]; zs=[0.,.5,1.,1.5]
    planes=[]
    for y in ys:
        rows=[]
        for z in zs:
            rows.append([10+2*x+3*y+4*z if z<=math.sqrt(max(0,1.2**2-(x-1)**2)) else None for x in xs])
        planes.append({'y':y,'values':rows,'measured':False,'shed':None,'mean':None})
    volume={'x':xs,'z':zs,'planes':planes,'stripes':[[1,3]],'max_measured_z':1.,
            'geometry':{'radius':1.2,'center_x':1.,'offset_z':0.},'time':'fixture-time',
            't_index':7,'field_ref':'analytic-linear-field','preset':'standard','monotonic':True,
            'y_step':2.,'y_min':0.,'y_max':4.,'frame':{'n':7,'time':'fixture-time'},
            'sheds':[],'available_sheds':[]}
    return {'source_time':'fixture-time','frame_index':7,'session_id':'fixture-session', 'model_id':1,
            'volume':volume,'facts':[{'id':'F:context','text':'独立线性场测试夹具，不是用户现场数据。'}]}
