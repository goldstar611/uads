# SET.BAS → per-model OBJ conversion plan

> **STATUS: COMPLETE (2026-11-14).** All sets (DATA + dataxp, 12 total) converted to
> `~/utmshared/openua-obj/`, lossless reconstruction proven (VERIFY3 619/619 per set1;
> 148762/148762 file refs validated), in-game confirmed. Key bug found during
> verification: `NC_STACK_Obj3D::RecalcInternal` no-op broke per-cell terrain-filler
> rebuilds (seam strips/elevation) — fixed by rebuilding from ADEs for uattach models.
> Engine commits: UA_source `c5e8781` + `b77f66d`; asset tooling: urban_assault_decompiled
> `163d72b` (objconvert.py + docs/texture-mapping.md).

## Goal

Convert all per-set content (vehicles / buildings / slurps) from the per-set `SET.BAS`
blob into flat, per-model text assets under `~/utmshared/openua-obj/` (a copy of the
OpenUA Standalone Package minus `MOV/` and sound dirs; the pristine package stays
untouched). Zero sharing: every model owns its own copies of textures, texture
animations, ADE particle effects and skeletons. The engine then loads everything via
the existing single-load lists (`visproto.lst`, `set.sdf`, `slurps.lst`).

Rationale for zero sharing: update one model without touching any other; deleting or
rewriting a model can never break a neighbor.

## Verified facts

- **SET.BAS structure**: one MC2 `base` object — `EMBD` resource pool (SKLT / VANM /
  VBMP) plus 3 kid groups (vehicles 373 / buildings 256 / slurps 72 in set1). No
  palettes, remaps, scripts or world data inside; those are external sibling files.
- **Loader dispatch by extension** (`loaders.cpp:44`): `.3ds` → `NC_STACK_3ds`,
  `.obj` → `NC_STACK_Obj3D`, anything else → native `LoadBaseFromFile`.
- **Extension truncation to 3 chars** (`utils.cpp:124`): `set.base` → `set.bas`
  (how SET.BAS is found), `.sklt` → `.skl` (collision skeletons ship as `.skl` in
  `MC2RES/SKELETON`). `.uattach` must be opened via FSMgr directly, not the
  truncating helpers.
- **Vehicle variant flags** (`ypabact.cpp:6870-7188`, original scripts
  `vp_normal/vp_fire/vp_megadeth/vp_wait/vp_dead/vp_genesis` → visproto.lst indices):
  `f`=fire, `w`=wait, `d`=megadeath (DEATH2), `x`=dead (normal destruction),
  `g`=genesis (beam-in/create). Case-insensitive (`VPD`, `VPW`, ...). Some models are
  reused across vehicles (FOX's megadeath → `VPdPANZ2`).
- **Texture sharing today**: by name via the rsrc publicList (`TRYSHARED=1`,
  `rsrc.cpp:39`); measured in set1: HUBI.ILBM ×61 vehicle files, BAGGER ×44, FX1 ×42,
  MTL ×32. Models reference atlas windows via `NAM2` (texture file name) — the
  1565 CIBOs carry no OTL2 outlines in either audited set.
- **`ExportObj` limitations** (obj3d.cpp:398): meshes only; triangulates; merges
  equal-render-param ADEs into one `Mat%d`; drops STRC / ADES metadata / KIDS /
  polFlags / per-poly ATTS shading / bmpanim animType / dynamic-texture frames.
- **No KIDS and no non-default STRC_BASE** in set1–set6 objects; set46 (menu/hub
  shell, KIDS trees) is **out of scope** and stays on the blob path.
- **Single-load only triggers when `SET.BAS` is absent**, and then requires ALL of:
  `visproto.lst` (vehicles), `set.sdf` first section (lego/buildings, paired by kid
  index, not name; references external collision skeletons), `slurps.lst`
  (`yw_funcs.cpp:573-624`).
- **Shipped package gaps the converter must close**: no `slurps.lst` in any
  `dataxp/SetN/Scripts`; `Skeleton/ColSide.sklt` + `Skeleton/ColCross.sklt` exist only
  inside SET.BAS but are required at runtime from `data:mc2res`; the shipped
  non-XP `visproto.lst` misses 11 xpack vehicles (blob has 373 kids); `SetN/RSRCPOOL`
  is empty but bmpanim resolves `rsrc:rsrcpool/<name>` (`bmpAnm.cpp:252`).
- **Format-independence note**: the geometry/index coherence problem (ADEs bind to
  skeleton poly/point indices; loaders rebuild a skeleton from mesh faces, and 0/2-vertex
  skeleton polys cannot exist in any mesh file) is not fixable by choosing 3DS over
  OBJ — 3DS is triangles-only natively. Fix = authoritative per-model `.skl` +
  original indices in the sidecar.

## Layout (flat, per-model names)

```
DATA/SET1/OBJECTS/VP_NFOX.obj         (mtllib VP_NFOX.mtl)
DATA/SET1/OBJECTS/VP_NFOX.mtl         (map_Kd VP_NFOX_MTL.png)
DATA/SET1/OBJECTS/VP_NFOX_MTL.png     (own copy; same pixels as neighbors' copies, separate file)
DATA/SET1/OBJECTS/VP_NFOX_<ANM>.anm   (own copy of texture animations → also placed in SetN/rsrcpool/)
DATA/SET1/OBJECTS/VP_NFOX_<ADE>.ade   (own copy of particle effects)
DATA/SET1/OBJECTS/VP_NFOX.uattach     (sidecar: anm/ade/kid attachments + metadata)
skeleton/VP_NFOX_<ORIG>.skl           (own skeleton copy where lego needs one)
MC2RES/SKELETON/colside.skl, colcross.skl
```

Every file prefixed with the model name → updating one model touches only its files.
Converted meshes are `.obj` (3-char extension, truncation-safe; naming anything
`.base` would truncate to `.bas` and collide with originals).

## Phase 1 — Engine (UA_source fork, podman build)

1. **`ua_export` console tool** (new executable in `src/CMakeLists.txt`):
   init System+GFX with SDL dummy video, load set palette, open a named `SET.BAS`,
   walk its named kids, and for each model:
   - `ExportObj` → `<MODEL>.obj` + `.mtl` + `<MODEL>_<ORIG>.png` per texture
     (enhanced `ExportObj`: texture files named from the bitmap's rsrc name, not
     `Tex%d`; per-model json sidecar with `Mat%d → orig texture name`),
   - extract bmpanim ANMs via the existing writer (`bmpAnm.cpp:477`) as per-model
     copies into `SetN/rsrcpool/` (per-model name; the ANM payload embeds texture
     names → rewritten to the model's own copies; 5 pool names have no `.ANM`
     extension — path building must not assume one),
   - write ADEs (area/amesh/particle) as standalone IFF files (new writer; engine
     has `SavingIntoIFF` for all three classes already),
   - write per-model skeleton `.skl` (writer exists, `sklt.cpp:445`),
   - emit `colside.skl` / `colcross.skl` into `MC2RES/SKELETON`,
   - round-trip verify each `.obj` via `LoadObj3D` (mesh/vertex/index counts).
2. **`NC_STACK_Obj3D` sidecar support**: read `<name>.uattach` (FSMgr-direct open)
   and re-attach:
   - bmpanim ANMs with `animType` (loop/ping-pong — only exists in BANI STRC, never
     in the `.ANM` payload) and per-model texture name bindings,
   - ADEs with the **original** poly/point indices (loader must treat the per-model
     `.skl` as authoritative and regenerate area/amesh from the skeleton, not from
     OBJ faces — OBJ faces only provide the exported visual mesh),
   - kid STRC transforms (all defaults today; kept for future-proofing),
   - area render state lost by OBJ/MTL: polFlags / trcVal / clrVal / shdVal /
     per-poly ATTS shading.

## Phase 2 — Working dir + data assembly (Python)

1. Copy the package to `~/utmshared/openua-obj/` excluding `MOV/` and sound dirs.
2. Per set (set1..set5 + XP sets as applicable; set46 untouched):
   - delete `objects/SET.BAS` in the working copy (activates single-load),
   - write converted models/textures/anms/ades/skeletons (Phase 1 output),
   - regenerate `scripts/visproto.lst` — all 373 models in blob kid order (shipped
     lst misses the 11 XP tail entries),
   - rewrite `set.sdf` col-1 → per-model `.obj` paths in the **exact original
     order** (lego pairs by index); columns 2+ and subsector/sektor sections verbatim,
   - generate `scripts/slurps.lst` (72 ground fillers, order H×36 then V×36),
   - emit `colside.skl` + `colcross.skl` into `MC2RES/SKELETON`.
3. Keep untouched: `BEEBOX.BAS` (required at `yw_funcs.cpp:1111`), `palette/*`,
   `remap/*`, `MC2RES` pointers, fonts, `world.ini`.
4. Emit `docs/texture-mapping.md` in `urban_assault_decompiled`: per-model texture
   tables plus the historical shared-atlas audit (what WAS shared: HUBI ×61, BAGGER
   ×44, FX1 ×42, MTL ×32 vehicle files in set1).

## Phase 3 — Verification

1. Headless round-trip checks per model (mesh/vertex/index counts, attachment
   re-bind verification) — no GUI needed.
2. User battle test per set on the local setup (podman here has no GUI): all 6
   vehicle states (drive/fire/wait/dead/megadeath/genesis), building shapes,
   slurp fillers, muzzle flashes/exhausts/death FX, per-model textures.
3. Documented deliberate behavior changes:
   - baked-palette PNGs instead of 8-bit ILBM (the hi/alpha|beta|gamma FX texture
     variants from `SetN/HI/<mode>/` are bypassed — one quality level for all),
   - triangulated meshes (3DS-compatible; ADE/poly binds unaffected thanks to the
     authoritative-`.skl` approach).

## Repo / commit mapping

- Engine changes (`ua_export`, `ExportObj` enhancement, `.uattach` loader) →
  `UA_source` fork, committed there.
- Python assembly tooling + texture mapping doc → `urban_assault_decompiled`.
- This plan + conversion status → `uads/docs/`.
