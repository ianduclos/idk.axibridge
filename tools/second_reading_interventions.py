"""Compare the same prefix and continuation streams under controlled interventions."""
from pathlib import Path
import sys, json, argparse
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from second_reading_study import draw
import matplotlib.pyplot as plt
from axibridge.sources.second_reading import SecondReading, SecondReadingParams


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('shots/second-reading-latest'))
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    module = SecondReading()
    cases = [
        ('Long crossing', [(40,145),(105,117),(174,95),(245,65)]),
        ('Open hook', [(65,140),(80,105),(115,88),(148,105),(144,137),(118,151)]),
        ('Small interruption', [(139,97),(149,108),(145,120)]),
    ]
    fig, axes = plt.subplots(3, 5, figsize=(20, 9), facecolor='#e9e5dd')
    recipes = []
    for row, (name, points) in enumerate(cases):
        events = [{'kind':'stroke','turn':5,'points':points,'smoothing':.6}]
        variants = [('Shared prefix',4,[]), (name,5,events),
                    ('One answer',6,events), ('Four answers',9,events),
                    ('Alternative four answers',9,[*events,{'kind':'branch','turn':6,'seed':29}])]
        for col, (title, turn, recorded) in enumerate(variants):
            params = SecondReadingParams(seed=12,turns=turn,events=recorded)
            doc = module.generate(params); draw(axes[row,col], doc)
            axes[row,col].set_title(title, fontsize=10)
            trajectory = module.trajectory(params)
            recipes.append({'case':name,'view':title,'params':params.model_dump(),
                            'actions':trajectory.metadata[:turn+1]})
            lines = ''.join('<polyline points="'+ ' '.join(f'{x:.6f},{y:.6f}' for x,y in p.points)+'"/>'
                            for p in doc.layers[0].paths)
            (args.output/f'intervention-{row}-{col}.svg').write_text(
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{params.width}mm" height="{params.height}mm" '
                f'viewBox="0 0 {params.width} {params.height}"><g fill="none" stroke="#24221e" stroke-width="0.3">'
                +lines+'</g></svg>')
    fig.tight_layout()
    fig.savefig(args.output/'interventions.png',dpi=135)
    (args.output/'interventions.json').write_text(json.dumps(recipes,indent=2))
    print(args.output/'interventions.png')

if __name__ == '__main__': main()
