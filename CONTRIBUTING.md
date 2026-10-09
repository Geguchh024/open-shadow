# Contributing

Thanks for helping. Below is everything you need to work on the add-on.

## Project layout

```
open_shadow/               the add-on (this folder is what gets zipped)
  __init__.py              registration, upgrade-on-load handler, lamp type watcher
  blender_manifest.toml    extension manifest (id, version, license)
  nodekit.py               small DSL for building node trees in Python
  patterns.py              the procedural patterns, plus the Transform and
                           Finish groups every shadow material uses
  rig.py                   lamps, shadow planes, materials and drivers
  presets.py               built-in looks
  props.py / ops.py / ui.py   settings, operators, panels
  thumbs.py, thumbs/       preset gallery thumbnails
tools/render_thumbnails.py renders open_shadow/thumbs
tools/render_previews.py   renders the shadow previews in docs/images
tools/render_showcase.py   renders the artwork scenes in docs/images/showcase
tests/run_tests.py         headless test suite
```

## Running from source

Point Blender at the repo instead of installing the zip:

- Either add the repo root to *Preferences → File Paths → Script Directories*,
- or symlink `open_shadow` into your user extensions folder.

Then enable the add-on.

## Tests

```
blender -b --factory-startup --python tests/run_tests.py
```

The script exits with a non-zero status if any test fails. The tests cover:

- that every pattern builds and every preset applies;
- that every driver is valid and needs no Python, for every lamp type;
- that the plane fits the spot cone and follows lamp type changes;
- duplicating, removing, operators and settings;
- that a saved file works without the add-on, and upgrading old files;
- that light is really blocked, with small renders in both engines.

Please run them before opening a pull request.

## Thumbnails and previews

```
blender -b --factory-startup --python tools/render_thumbnails.py [-- PRESET_ID ...]
blender -b --factory-startup --python tools/render_previews.py [-- [--eevee] PRESET_ID ...]
blender -b --factory-startup --python tools/render_showcase.py [-- SCENE ... --samples N --scale F --plain]
```

Every preset needs a thumbnail; the tests check this.

## Building the zip

```
blender --command extension build --source-dir open_shadow --output-dir dist
```

## Writing a pattern

- A pattern is a function `build(pb, x, y, I)` in `patterns.py` plus a
  `Pattern(...)` entry in `PATTERNS`. `x, y` are the pattern coordinates
  (the plane spans -0.5..0.5), `I` maps input names to group input sockets.
  Return how much light passes: a float (0 = blocked, 1 = open) or a colour.
- `PB` has 2D helpers: `fill(d)` turns a signed distance into a mask,
  `band`, `union`, `cut`, `rot`, `hash`, `vor`, `vesica` (a leaf), and so on.
  `leaf_layer` and `fronds` build scattered leaves and fronds.
- **Group versions.** Node groups are rebuilt when their stored
  `os_version` differs from `GROUP_VERSION` in `patterns.py`. Bump it whenever
  you change a group. Opening an older file then rebuilds the groups and
  restores every light's settings by input name (see `rig.upgrade_file`).
- **Renaming inputs.** Presets refer to inputs by name. If you rename one,
  update `presets.py`; `every_preset_applies` catches mistakes.
- **No Python in drivers.** Driver expressions must stay *simple
  expressions* (`driver.is_simple_expression`), or files would need
  *Auto Run Python Scripts*. Driver variables must exist for the lamp type:
  `spot_size` only exists on Spot lamps, which is why `rig.add_drivers`
  builds different drivers per type and `rig.sync_types` rebuilds them.

## Releases

1. Bump `version` in `open_shadow/blender_manifest.toml`.
2. Add an entry to `CHANGELOG.md`.
3. Build the zip and attach it to a GitHub release.
