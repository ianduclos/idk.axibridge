"""All interaction geometry is in paper millimetres, y down."""
import math
from shapely.geometry import LineString

def paper_pose(x,y,heading,start_x,start_y,scale):
    return start_x+3*scale*x,start_y-3*scale*y,-heading

def sensor_points(x,y,heading_deg,scale):
    h=math.radians(heading_deg);c,s=math.cos(h),math.sin(h);f=3*scale
    return [(x+f*(.55*c+side*.42*s),y+f*(.55*s-side*.42*c)) for side in (1,-1)]

def simplify_runs(strokes,tolerance=.003):
    result=[]
    for stroke in strokes:
        if len(stroke)<2:continue
        p=LineString(stroke).simplify(tolerance,preserve_topology=False)
        if p.length>1e-9:result.append([[float(x),float(y)] for x,y in p.coords])
    return result
