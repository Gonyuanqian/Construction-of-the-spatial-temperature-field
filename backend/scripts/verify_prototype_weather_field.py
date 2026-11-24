"""Offline acceptance bridge: actual frozen G/F, saved views and coordinate query."""
import argparse
import json
import os
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root/'backend/src'),str(root/'backend')]
parser=argparse.ArgumentParser()
parser.add_argument('--request',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--model-directory',type=Path,required=True)
args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=True)
os.environ['TFIELD_PROTOTYPE_MODEL_DIR']=str(args.model_directory.resolve())
os.environ['TFIELD_WEATHER_RESULT_ROOT']=str((args.output/'saved-results').resolve())
from tfield import prototype_runtime,weather_runtime
from api import weather_views

request=json.loads(args.request.read_text('utf-8'))
result=prototype_runtime.infer(request['frames'],request['dimensions'],request['reference_id'])
weather_runtime.save_result(request['frame_id'],result)
_,volume=weather_views.saved_volume(request['frame_id'])
frame=weather_views.sections(request['frame_id'])
d=request['dimensions']
profile={key:volume[key] for key in ('preset','monotonic','y_step','y_min','y_max')}
point=weather_views.point(request['frame_id'],d['width_m']/2,d['length_m']*.75,d['height_m']*.4,**profile,expected_ref=volume['field_ref'])
assert point['kind']=='value'
assert volume['y_max']==d['length_m'] and volume['x_max']==d['width_m'] and volume['z_max']==d['height_m']
for name,payload in [('summary',result['summary']),('volume',volume),('frame',frame),('point',point)]:
    (args.output/f'{name}.json').write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False),'utf-8')
print(json.dumps({'passed':True,'dimensions':d,'nodes':len(result['summary']['node_temperatures']),'paid_requests':0}))
