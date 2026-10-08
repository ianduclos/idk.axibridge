import pytest
from axibridge.mosca2.geometry import paper_pose, sensor_points, simplify_runs

def test_page_mapping_and_left_sensor_share_physical_frame():
    assert paper_pose(2,3,0,100,80,1)==pytest.approx((106,71,0))
    left,right=sensor_points(100,80,0,1)
    assert left==pytest.approx((101.65,78.74))
    assert right==pytest.approx((101.65,81.26))
    left,right=sensor_points(100,80,90,2)
    assert left==pytest.approx((102.52,83.3))
    assert right==pytest.approx((97.48,83.3))

def test_simplification_retains_separate_runs_and_endpoints():
    strokes=[[[10,10],[11,10.00001],[12,10]],[[20,20],[21,21]]]
    result=simplify_runs(strokes)
    assert result==[[[10,10],[12,10]],[[20,20],[21,21]]]
