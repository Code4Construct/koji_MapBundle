# koji_MapBundle

koji_MapBundle is a QGIS plugin for exporting and importing project map assets as
portable ZIP-based map bundles.

It packages selected layers, layer styles, SVG symbols, and print layouts, then
restores them into another QGIS project. Imported GeoPackage data is copied next
to the current QGIS project file, so project layers keep stable local data
sources after import.

## Features

- Export selected vector and raster layers into a map bundle ZIP file.
- Preserve vector data in a GeoPackage inside the bundle.
- Preserve QGIS layer styles and referenced SVG symbol assets.
- Export and import print layout templates.
- Import bundle data into a project-side folder next to the current QGIS project.

## Usage

1. Enable `koji_MapBundle` in the QGIS plugin manager.
2. Open `koji_MapBundle` from the toolbar or plugin menu.
3. Choose `地図バンドルを書き出し` to create a ZIP bundle.
4. Choose `地図バンドルを読み込み` to import a received ZIP bundle.

## Import Storage

When a bundle is imported, its contents are copied to a folder in the same
directory as the current QGIS project file. The plugin asks for the imported
GeoPackage name and uses `MapBundle` as the default.

Example:

```text
sample.qgz
SampleProject_20260704_220000/
  data/
    MapBundle.gpkg
  styles/
  symbols/
  layouts/
  manifest.json
```

If the current project has not been saved yet, the plugin asks for a destination
folder.

## Japanese UI Name

The Japanese UI name is `地図バンドル`.

## Documentation

Project documentation and download information are planned at:

https://www.arinobu.org/koji_mapbundle.html
