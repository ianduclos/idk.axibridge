# Round 11 corpus harvest (2026-10-17)

Ten downloads approved by Ian. Seven fetched in full, one in part, three
refused by the sources. Manifest: `round11-harvest.csv` (88 rows: one per
file, or per dataset where a directory is the unit, plus the skipped
sources). Everything is under `.local/gesture/corpus/<group>/<id>/` (gitignored)
except the tesseract models. About 1.0 GB on disk in total, 0.7 MB of
contact sheets in `.local/gesture/out/harvest_round11/`.

## Fetched

| # | corpus id | what | size | rights |
|---|---|---|---|---|
| 2 | `artists/picasso-museu-barcelona` | 33 late drawings, 1946-1970 (1957 "Lines to Simulate Writing" asemic ink series, bulls, dedication drawings, Jacqueline profile, markers, grease pencil) | 3.5 MB | in copyright (Museu Picasso / VEGAP) |
| 4 | `earth/iceland-analog-seismograms` | 32 drum records, 1910-2004, 300 dpi JPG (smoked drums early, Heimaey 1973, Krafla, Kopasker 1976, Gjalp 1996, South Iceland 2000) | 109.7 MB | none stated; "made available to the public" |
| 5 | `earth/zenodo-5017751-fly` | mosquito + hover-fly HDF5 (`mos_vision.h5`, `hover_vision.h5`) | 91.9 MB | CC0 |
| 6 | `earth/s2-18MUC-20240731-pastaza` | Sentinel-2 L2A 30 km window, B03 + B08 at 10 m, B11 at 20 m; braided reach near 2.5 S 76.8 W | 27.4 MB | Copernicus open |
| 7 | `animal/movebank-lifetrack-stork-sicily`, `animal/movebank-tropicbird-santos2019` | stork GPS (90,965 fixes, 7 birds, 2015); tropicbird foraging GPS (2,113 fixes) | 21.3 MB | CC0 |
| 8 | `animal/geolife-1-3` | GeoLife 1.3 zip, left zipped (18,670 .plt, 1.67 GB uncompressed) | 298.6 MB | non-commercial research |
| 9 | `fabric/fabric-stain-dataset` | 466 photos (398 stain, 68 defect-free) with Supervisely annotations | 419.2 MB | CC0 |
| 10 | `.local/gesture/tessdata/` | `ara.traineddata` (tessdata_best), plus `eng` and `osd` copied from Homebrew | 26 MB | Apache-2.0 |

`TESSDATA_PREFIX=.local/gesture/tessdata tesseract --list-langs` lists ara, eng, osd.

## Skipped, and why

- **De Kooning (1) and Polke (3), MoMA.** moma.org returns a Cloudflare
  "Just a moment" challenge to scripts. Not bypassed.
- **De Kooning, Art Institute of Chicago.** The API works but the IIIF
  images answer 403 to scripts, as in the earlier artists harvest.
- **Picasso at the Menil.** Its robots.txt disallows ClaudeBot and other
  AI crawlers, so it was left alone. Barcelona was used instead.
- **USGS WWSSN film chips.** ScienceBase is behind the same Cloudflare
  challenge.
- **IRIS Caltech scans.** Every `ds.iris.edu/seismo-archives` page now
  returns 404 (retired in the EarthScope move). Iceland's archive filled the
  seismogram slot (32 records instead of 30).
- **Other Movebank studies.** Only the two CC0 repository datasets with
  direct file links were taken. Nothing that needs terms or a login was
  attempted; no account was created. The stork acceleration file (198 MB)
  was left out.

The de Kooning and Polke sheets, if Ian still wants them, need a browser
download by hand from the MoMA pages in `hands_trails-2026-10-17.md`.

## Notes for whoever uses these

- Picasso is small because the site only serves a 1200 px derivative. Many
  items are photographs of dedicated book spreads rather than flat sheets.
- Iceland files were checked byte-for-byte against the server's
  Content-Length. Two were first truncated by a download timeout and were
  fetched again. The early drum records are dark smoked paper.
- The Sentinel window was cut by a small range-request COG reader (own
  code, kept in the session scratch, not in the repo); geokeys come from
  the source files. Tile 18MUC is the Pastaza megafan scene named in the
  rivers results, but the exact river was not identified.
- Fly files are HDF5 (magic bytes and exact Zenodo sizes verified), not
  opened: the research venv has no h5py.
- GeoLife was not extracted. The zip listing is clean (no absolute or `..`
  paths) and `testzip` passes.
- Fabric: the 439 MB tar was fetched with parallel range requests, read
  through end to end, extracted with the tarfile `data` filter, then deleted.
  The photos are low-contrast grey and the stains mostly small.
- Nothing was executed from a download directory; downloaded data was only
  read by Python run with `-I` from elsewhere.
