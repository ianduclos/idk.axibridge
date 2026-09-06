"""Hold a real bench prefix, action and random stream fixed; toggle context only."""
from pathlib import Path
import sys, json, random, argparse
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from second_reading_study import draw
import matplotlib.pyplot as plt
from axibridge.sources.second_reading import SecondReading, SecondReadingParams
from axibridge.sources import _second_reading as engine
from axibridge.model import Layer, PathDocument

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, default=Path('shots/second-reading-latest'))
output = parser.parse_args().output
output.mkdir(parents=True,exist_ok=True)
params = SecondReadingParams(seed=12,turns=5,events=[{'kind':'stroke','turn':5,
    'points':[(65,140),(80,105),(115,88),(148,105),(144,137),(118,151)],'smoothing':.6}])
trajectory = SecondReading().trajectory(params)
memory = [engine.describe(i,[p],'organic','opening') for i,p in enumerate(trajectory.steps[0])]
for turn in range(1,6):
    meta = trajectory.metadata[turn]
    memory.append(engine.describe(turn+1,trajectory.steps[turn],'organic',meta['action'],tuple(meta['target_passage_ids'])))
base = [p for m in memory for p in m.paths]
fig, axes = plt.subplots(2,3,figsize=(15,7),facecolor='#e9e5dd')
records = []
for row, action in enumerate(('surround','concentrate')):
    for seed in range(100):
        c = engine.Commitment(action,(6,),3,1)
        aware,_ = engine.make_action(c,memory,.5,280,198,random.Random(seed))
        if c.response:
            break
    plain,_ = engine.make_action(engine.Commitment(action,(6,),3,1),memory,.5,280,198,random.Random(seed),False)
    # Locate the encounter for a generous detail, keeping identical extents
    # on both versions. The full-prefix panel establishes its context.
    difference = [p for p in aware if p not in plain]
    points = [p for path in (plain+aware if action == 'concentrate' else difference) for p in path.points]
    if action == 'surround':
        centre = aware[0].points[-1]
    else:
        centre = ((min(x for x,y in points)+max(x for x,y in points))/2,
                  (min(y for x,y in points)+max(y for x,y in points))/2)
    radius_x = max(32, (max(x for x,y in points)-min(x for x,y in points))/2+5) if action == 'concentrate' else 32
    radius_y = max(24, (max(y for x,y in points)-min(y for x,y in points))/2+5) if action == 'concentrate' else 24
    for col, (label, paths) in enumerate((('Existing drawing',base),('Same move, ignores encounter',base+plain),
                                        ('Same move, attends encounter',base+aware))):
        doc=PathDocument(width=280,height=198,layers=[Layer(id=1,name='Study',paths=paths)])
        draw(axes[row,col],doc)
        axes[row,col].set_title(f'{action} · {label}',fontsize=9)
        if col:
            axes[row,col].set_xlim(centre[0]-radius_x,centre[0]+radius_x)
            axes[row,col].set_ylim(centre[1]+radius_y,centre[1]-radius_y)
    records.append({'prefix':params.model_dump(),'action':action,'random_seed':seed,
                    'target_ids':[6],'context_ids':list(c.context_ids),'response':c.response,
                    'ignores':[p.model_dump() for p in plain], 'attends':[p.model_dump() for p in aware]})
fig.tight_layout();fig.savefig(output/'encounter-details.png',dpi=145)
(output/'encounter-details.json').write_text(json.dumps(records,indent=2))
print(output/'encounter-details.png')
