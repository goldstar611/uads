# MC2 / .bas asset conversion to OBJ or 3DS

Goal: convert every MC2/`.bas` (native `.base`) unit/terrain object so the game loads them
from modern, editable asset files instead of the binary `.base` blobs, including the
"single load" path that has no `set.base`.

## How the engine picks a loader

`Utils::ProxyLoadBase` (src/loaders.cpp:44) dispatches **by file extension**:

| Extension | Loader | Format |
|-----------|--------|--------|
| `.3ds` | `NC_STACK_3ds::Load3DS` (src/3ds.cpp) | Autodesk 3DS binary (magic `0x4D4D`) |
| `.obj` | `NC_STACK_Obj3D::LoadObj3D` (src/obj3d.cpp) | Wavefront OBJ text + `.mtl` |
| anything else | `NC_STACK_base::LoadBaseFromFile` | native UA `.base` binary mesh |

All three produce the same internal `NC_STACK_base` mesh representation
(`Meshes`, vertexes/UVs/indices + `GFX::TRenderParams`), so the choice of file
format does not affect rendering features available at runtime.

## The "single load" chain (no set.base)

`load_set_base()` (src/yw_funcs.cpp:574) has a 3-tier fallback:

1. `rsrc:objects/set.base` — everything in one file.
2. Fragment load: `visproto.base` + `lego.base` + `slurp.base`.
3. **Single load**: text lists `rsrc:scripts/visproto.lst`, `rsrc:scripts/set.sdf`,
   `rsrc:scripts/slurps.lst`. Each non-comment line names one object, loaded
   individually via `ProxyLoadBase("rsrc:objects/<name>")` (sub_44AD8C, yw_funcs.cpp:547).

For a converted game the third tier is the target: keep the `.lst`/`.sdf` lists,
replace the `.base` blobs with per-object `.obj` (+`.mtl`) files. Each individual
file may independently be `.obj`, `.3ds`, or `.base`.

## What each mesh format supports (and what is actually used)

### 3DS (src/3ds.cpp, 3ds.h)

Parses a large chunk set: `0x3D3D` object, `0xAFFF` material, `0x4130`
face-material assignment, `0xA300` map names. Materials carry ambient/diffuse/
specular/shininess, texture1/2 (+masks), opacity, bump, self-illum, reflection
maps, tints, wire/two-sided flags.

**However `GenRenderParams` only consumes `texture1_map`** (src/3ds.cpp:570):
`RFLAGS_TEXTURED` + the diffuse texture. Everything else is parsed and discarded.
Face-material (per-face texture assignment) is supported via `0x4130`.

### OBJ (src/obj3d.cpp, obj3d.h)

Reads `v`, `vt`, `vn`, `f`, `mtllib`, `usemtl`. The MTL parser understands
`newmtl`, `map_Kd` (used), `map_Ks` / `map_Ke` (parsed, no-op), `d`,
and diffuse color. Per-face material via `usemtl` is supported.

Coordinate convention quirk: the loader negates Y on read
(`v` line: `(x, -y, z)`, obj3d.cpp:113) — UA world space is Y-down relative to
standard OBJ. A converter must match this or models appear upside-down.

Texture search path for `map_Kd` (obj3d.cpp:308): `rsrc:<name>` →
`rsrc:objects/<name>` → `rsrcpool/<name>`.

## Textures (both formats)

Mesh files only carry texture *names*; actual bitmaps load through
`Utils::ProxyLoadImage` (src/loaders.cpp:12) by extension:

- `.jpg .png .tiff .webp .bmp .gif .pcx .svg` → `NC_STACK_image` (SDL2_image)
- anything else → `NC_STACK_ilbm` (ILBM/PBM — the original UA texture format)

Textures stay as separate files regardless of mesh format; converting meshes
does not require converting textures (though PNG/BMP are recommended for
editability; ILBM remains the reference for exact original palettes).

## Conversion pipeline

The engine already contains a **native/O3DS → OBJ exporter**:
`NC_STACK_Obj3D::ExportObj(base, fname)` (src/obj3d.h:61, src/obj3d.cpp:398)
writes `<fname>` + `<fname>.mtl` from any loaded `NC_STACK_base` (one material
per mesh, `Mat%d` naming). There is **no 3DS writer** in the tree.

A practical conversion tool: load each `.base` object with
`LoadBaseFromFile`, call `ExportObj`, fix up material names to meaningful ids,
and keep the same basename in `rsrc:objects/` so the `.lst`/`.sdf` single-load
lists reference the new files unchanged.

## Recommendation: OBJ

**Convert to OBJ (+MTL), not 3DS.** Reasons:

1. **Exporter exists in-tree.** `ExportObj` is built into the engine and is the
   only writer for any mesh format; a 3DS writer would have to be written from
   scratch. The conversion then uses the engine's own geometry math, avoiding
   any risk of misinterpreting the `.base` format.
2. **Round-trip fidelity where it matters.** Both loaders reduce to the same
   internal mesh; OBJ's feature set (diffuse map + color + per-face material)
   covers everything `GenRenderParams` actually consumes. The extra 3DS chunks
   (bump/reflection/opacity/tints) are dead weight after load.
3. **Text format, scriptable.** OBJ+MTL is plain text — easy to generate,
   inspect, and diff from Python tooling; no chunk-container plumbing.
4. **Round trip out of the engine.** `ExportObj` output can be loaded straight
   back by `LoadObj3D`, enabling verify-by-reload tests during conversion.

3DS is worth choosing only if authenticity with the original 3D Studio
pipeline/tools matters (e.g. importing into period-correct software); the
runtime gains nothing from it.

Caveats for the converter, regardless of format:

- OBJ Y-negation convention (see above) — verify orientation with one unit
  before batch-converting.
- MTL `map_Kd` paths resolve via the 3-step search above; simplest is to keep
  texture files next to the models in `rsrc:objects/` or `rsrcpool/`.
- UV mapping: OBJ `vt` per-vertex; 3DS uses per-face vertex indices —
  `ExportObj` already handles the translation.
- Materials lose their original names (`Mat%d`) — rename them in a post-pass
  if the material names are needed downstream.
