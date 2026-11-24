from types import SimpleNamespace
import json
import numpy as np
import pandas as pd
import pytest

from tfield.geometry_transfer import HouseDimensions,build_transferred_volume
from tfield.independent_training import GEOMETRY,PROTOCOL


class AnalyticSection:
    protocol=PROTOCOL
    geometry=GEOMETRY.copy()
    def predict(self,weather,nodes,*,target_positions):
        p=target_positions
        return (weather.bg_temp.iloc[0]+p[:,0]+2*p[:,1])[None,:]


def volume(dimensions=HouseDimensions(6,2.1,1.3017),**kwargs):
    frame=pd.DataFrame([dict(timestamp='2026-07-26T17:00:00',bg_temp=25.,bg_rh=60.,bg_light=100.)])
    return build_transferred_volume(AnalyticSection(),frame,np.arange(8)+25.,dimensions,allow_assumptions=True,**kwargs)


@pytest.mark.parametrize('dims',[(3,1.05,.65085),(6,2.1,1.3017),(12,2.1,1.3017),(8,3,1.8),(6,4.2,2.6034),(6,2.1,2.2),(30,3,2),(60,6,3)])
def test_requested_geometry_and_normalized_field_are_consistent(dims):
    field=volume(HouseDimensions(*dims));reference=volume()
    assert field.x[-1]==dims[1] and field.y[-1]==dims[0] and field.z[-1]==dims[2]
    np.testing.assert_array_equal(field.mask,reference.mask)
    np.testing.assert_allclose(field.section,reference.section,equal_nan=True)
    assert np.isnan(field.section[~field.mask]).all()
    actual=field.query(.5*dims[1],.37*dims[0],.5*dims[2])
    assert actual['value']==pytest.approx(26.5)
    assert field.query(.5*dims[1],.93*dims[0],.5*dims[2])['value']==pytest.approx(actual['value'])
    assert not actual['accuracy_validated']


@pytest.mark.parametrize('dims',[(0,2,1),(-1,2,1),(6,0,1),(6,2,float('nan')),(float('inf'),2,1),(True,2,1),(10001,2,1)])
def test_invalid_dimensions_rejected(dims):
    with pytest.raises(ValueError):HouseDimensions(*dims)


@pytest.mark.parametrize('kwargs',[dict(nx=1),dict(ny=True),dict(nz=513),dict(nx=512,nz=512,ny=512)])
def test_grid_limits_checked_before_allocation(kwargs):
    with pytest.raises(ValueError,match='网格'):volume(**kwargs)


def test_explicit_assumptions_required_and_reference_model_unchanged():
    weather=pd.DataFrame([dict(timestamp='2026-07-26',bg_temp=25,bg_rh=60,bg_light=100)])
    model=AnalyticSection();original=model.geometry.copy()
    with pytest.raises(ValueError,match='显式'):build_transferred_volume(model,weather,np.arange(8),HouseDimensions(12,3,2))
    volume(HouseDimensions(12,3,2));assert model.geometry==original==GEOMETRY
    incompatible=SimpleNamespace(protocol='legacy',geometry=GEOMETRY)
    with pytest.raises(ValueError,match='不一致'):build_transferred_volume(incompatible,weather,np.arange(8),HouseDimensions(6,2,1),allow_assumptions=True)


def test_queries_preserve_boundary_missing_region_and_float_coordinates():
    field=volume()
    assert field.query(-.001,3,.4)['kind']=='outside'
    assert field.query(1,6.001,.4)['kind']=='outside'
    assert field.query(0,3,1.2)['kind']=='outside'
    assert field.query(1.05,3,1.2)['kind']=='unmeasured'
    assert field.query(0,0,0)['kind']=='value'
    with pytest.raises(ValueError):field.query(float('nan'),3,.4)
    actual=field.query(.777,2.1,.56)
    assert actual['x']==.777 and actual['y']==2.1 and actual['z']==.56


def test_payload_never_labels_generated_planes_or_center_as_observed():
    field=volume(HouseDimensions(12,3,2));payload=field.payload()
    json.dumps(payload,allow_nan=False)
    assert payload['transfer']['section_y_m'] is None
    assert not payload['transfer']['accuracy_validated']
    assert payload['transfer']['shell_center_is_display_only']
    assert max(point[1] for point in payload['arch'])==pytest.approx(2.)
    assert not payload['sensors'] and not payload['available_sheds']
    assert all(not p['measured'] and not p['virtual_source'] for p in payload['planes'])
    assert all(node['y'] is None and not node['measured'] for node in payload['virtual_nodes'])
    assert payload['planes'][0]['values']==payload['planes'][-1]['values']
    assert field.query(1,2,.4)['field_ref']==payload['field_ref']
    assert payload['field_ref']!=volume().field_ref
