# Evidence catalogue

Review baseline: `aa309b4`, inspected 7 September 2026. All application screenshots are from an isolated Chromium session, built from copied source, with temporary configuration and project directories. No hardware or user project was modified. Screenshots represent particular fixtures, not aesthetic findings.

## Reading order

1. [Illustrated reader](index.html)
2. [Canonical editable review](REVIEW.md)
3. [Supporting architecture audit](SUPPORT-architecture.md)
4. [Supporting interaction audit](SUPPORT-interaction.md)

The supporting reports contain independent positions and source hypotheses; the main review resolves priority and records remaining uncertainty. They are retained to keep disagreements inspectable, not to duplicate the recommendation list.

## Captures

| ID | Capture | What it establishes |
|---|---|---|
| E01 | [Empty Compose](assets/01-empty-compose.png) | Initial hierarchy, default generator, large paper surface. |
| E02 | [Selected Flow field](assets/02-flow-selected.png) | Generator latch, inspector allocation, visible cost readouts. |
| E03 | [Plot](assets/03-plot.png), [Pens](assets/03-pens.png), [Settings](assets/03-settings.png) | Initial inspector surfaces, backend prominence, configuration density. |
| E04 | [Second Reading, initial](assets/04-second-reading.png), [1100 wide](assets/05-second-reading-1100.png) | Initial temporal workspace and smaller-window composition. |
| E05 | [Before intervention](assets/06-second-before.png), [human turn](assets/07-second-human-turn.png), [kept](assets/08-second-kept.png) | Real pointer capture and recipe promotion, not synthetic artwork used to judge a generator. |
| E06 | [1440](assets/09-second-1440.png), [1100](assets/09-second-1100.png), [900](assets/09-second-900.png) | Measured stage/SVG mismatch at smaller heights. |
| E07 | [Homeostat bench](assets/10-homeostat-bench.png) | Generic process parameter/stage/transport arrangement. |
| E08 | [Injected preview failure](assets/11-preview-error.png) | Keep disabled; error appears behind overlay. Failure was deliberately injected, not spontaneous. |
| E09 | [Simulator paused](assets/12-simulator-paused.png) | Machine status/control placement. Synthetic stripe fixture makes material estimates unrepresentative of typical drawings. |
| E10 | [Tray target](assets/13-tray.png) | Visible frozen-output target and pass count. |
| E11 | [Compose 1440](assets/14-compose-1440.png), [1100](assets/14-compose-1100.png), [900](assets/14-compose-900.png) | Layout allocation and breakpoint. Dense black regions are the synthetic stripe fixture, not a claim of erroneous rendering. |
| E12 | [CSS zoom stress](assets/15-compose-200-percent.png) | Layout stress only; does not substitute for native text zoom or assistive technology. |
| E13 | [Dense import](assets/16-dense-import.png) | Final 12,410 SVG paths across four layers, with two copies of the 6,000-path stripe fixture. Not a frame-rate benchmark. |

## Structured evidence and baseline

1. [Second Reading](assets/second-reading-evidence.json): exact stroke event and smoothing, branches, staged note, kept state, stage dimensions and reload boundary.
2. [Workflow](assets/workflow-evidence.json): save/load, process playback, modal focus escape, deliberately injected failure, simulator pause state and tray label.
3. [Measurements](assets/measurement-evidence.json): computed control and viewport rectangles, type/colour values, CSS zoom and dense import interval including settling wait.
4. [Full baseline log](assets/baseline-tests.log): 1,263 tests passed; one dependency deprecation warning. Earlier temporary-copy omissions were corrected before this run; no application fixes were made.

## Proposal artwork

1. [Composition](assets/concept-compose.svg)
2. [Development](assets/concept-develop.svg)
3. [Lifetimes](assets/concept-lifetimes.svg)

These are native vector schematics with empty paper placeholders, not edited screenshots or a claim that a redesign was implemented. Flexoki values are from [upstream CSS](https://github.com/kepano/flexoki/blob/main/css/flexoki.css), saved in [flexoki.css](assets/flexoki.css); [license](assets/flexoki-LICENSE). Dark semantic roles follow [the published mapping](https://stephango.com/flexoki). The report's system-font reading typography is distinct from the application’s proposed retained Roboto Mono.
