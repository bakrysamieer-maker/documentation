# Southern Rub' al-Khali candidate screen: method, results, limitations

*Desk study, October 2026. Everything below is a **candidate** for expert review, not a discovery.
The region is a sensitive border area (Oman, Saudi Arabia, Yemen). This work contains no field-visit planning.*

Arabic presentation of the findings: [`outputs/presentation/rub_al_khali_findings_ar.pdf`](../outputs/presentation/rub_al_khali_findings_ar.pdf).
Interactive map with adjustable weights: [`outputs/maps/rub_al_khali_candidates.html`](../outputs/maps/rub_al_khali_candidates.html).
Candidate table: [`outputs/candidates/top20_candidates.csv`](../outputs/candidates/top20_candidates.csv); snapshots in
[`outputs/candidates/snapshots/`](../outputs/candidates/snapshots/).

## 1. Summary

- **No conclusive evidence** of settlements or buried buildings appears in free 10–90 m data. The output is 20 ranked
  1 km cells (14 in Oman, 6 in Saudi Arabia, approximate borders) that combine the hypothesis's clues most strongly.
- The candidates fall in **three settings**:
  1. the sand front 30–90 km north and north-west of Shisr, where wadis end under the dunes and weak track
     alignments from Shisr pass;
  2. the north-west fan near 53°E 18.6°N, in the general vicinity of the published Maitan Neolithic sites;
  3. interdune sabkhas east of Umm Al Heesh, on the Mu'taridah side, which is a groundwater discharge zone.
- The strongest signals are **natural** (wadi ends, closed lows, thin sand). The "human" clues (tracks, geometry) are
  weak at this resolution and dominated by modern look-alikes: vehicle tracks, centre pivots and seismic lines.
- These results agree with Dellmour et al. (2026, *Nature*): early settlement followed places where water and
  tool-grade stone occur together at the desert margins, and the interior crossing found no archaeology. Remote
  sensing cannot attribute any site to the people of ʿĀd; that needs archaeological dating. Even the identification
  of Shisr with Ubar is disputed.

## 2. Study area and reference checks

The corridor is a 150 km band from Shisr (18.255 N, 53.649 E) running 293.5 km at 22.6° to the Umm Al Heesh lakes
(20.70 N, 54.73 E), plus a 140 km fan north-west of Shisr: 56,349 km² in all. Reference coordinates were checked on
10 m Sentinel-2:

- **Shisr:** the published point sits on the village, surrounded by modern pivots and radiating tracks.
- **Umm Al Heesh:** a wetland lies 0.3–1.5 km north of the published point. Its present water comes from a leaking
  exploration well (Kazak et al. 2025).
- **Muqshin:** the English-Wikipedia coordinate is bare sand. The village lies about 30 km away, at 19.560 N, 54.885 E.
- **Umm as Samim:** the regional DEM low falls 8 km from the published centre, confirming the depression.

## 3. Data (all free)

| Data | Date | Resolution | Note |
|---|---|---|---|
| Copernicus DEM GLO-30 / GLO-90 | 2011–2015 | 30 / 90 m | AWS open data |
| Sentinel-2 L2A Collection 1, 17 tiles | 2024-12-06 and 2025-02-26 | 10–20 m | one date per orbit, cross-orbit matching (6.2 M overlap pixels) |
| Sentinel-1 global seasonal coherence and backscatter (Kellndorfer et al. 2022) | 2019–2020 | ~90 m | AWS open data |
| Landsat-1 MSS L1TP, 7 scenes | 1972-09 to 1973-09 | 60 m | Google Cloud public Collection 1 |
| OpenStreetMap via Overture Maps 2026-10-21 | 2026 | vector | roads, buildings, infrastructure, land use |

Not available in this session: **ASTER**, because NASA Earthdata hosts are blocked and Earth Engine needs a key; and
**published site coordinates**, because Zenodo and OSF are blocked. Scripts 13 and 14 are written for both and the
score picks them up automatically.

**Data volume.** About 10.4 GB was transferred in total, above the 4–5 GB estimated at the checkpoint, though no single
download exceeded 5 GB. The excess came from a second Sentinel-2 corridor read (needed to remove date seams), preview
iterations and verification chips.

## 4. Method

| Clue | Layer | Key numbers |
|---|---|---|
| 3 Valleys opening onto the sands | D8 flow routing (GLO-90). A terminus is where a ≥ 20 km² catchment, ≥ 70% sand-free upstream, enters sand and stays under it for ≥ 2.7 km. Buried courses are routed on a sub-dune base surface (2 km minimum of interdune floors). | 132 termini; 129 projected courses |
| 6 Shallow or recent sand | Dune height = DEM − base surface; 1972–73 vs 2024–25 sand class (red/green ratio, quantile-matched per MSS footprint); radar-bright sand (Sentinel-1 VV z > 1 inside sand) | sand covers 44.7% of the corridor; dune height p50 6.4 m, p90 48 m, p99 98 m; dune shift median 375 m in 52 yr (indicative) |
| 5 Groundwater-path lows | Closed depressions of the base surface, regional residual, wet surfaces (MNDWI > −0.05) | strongest east of Umm Al Heesh |
| 1 Fossil springs | Sentinel-2 pale-crust **proxy** (bright + SWIR-absorbing + not iron-stained), × 0.5 | cannot separate carbonate, gypsum, calcrete or salt |
| 2/4 Tracks and alignments | Sato ridge filter on 20 m red band, local z > 2, farm/blob/tile-seam exclusion, Hough segments; Shisr-radial bearing peaks extended 40 km | 21,735 segments; bearings 3°, 17°, 43°, 275° (3.5–6.7 km of segments each; 2–16% on mapped roads) |
| 4 Geometric anomalies | Corners (perpendicular segment pairs), Hough circles 60–300 m, curvilinear line density | 11 corners; 861 circles (522 at modern features); 4 long straight lines incl. a parallel E–W set ~45 km NNE of Shisr (seismic-like) |

**Scoring.** Components are rescaled 0–1 (1st–99th percentile inside the corridor) on a 1 km UTM 40N grid and
weighted 20 / 20 / 10 / 15 / 20 / 15 (clues 3, 1, 5, 2/4, 4, 6; editable in
[`config/weights.yaml`](../config/weights.yaml) or live in the map). Modern features are masked with a 300 m buffer,
farms are excluded, and seismic-like cells are multiplied by 0.5. The top 20 are kept with ≥ 5 km spacing. Each
candidate lists automatic natural or modern explanations.

## 5. Limitations

- At 10–20 m, walls, buildings, tombs and triliths are sub-pixel. Only 11 corners were found in the whole corridor.
- Clue 1 rests on a non-specific proxy until ASTER is run. The proxy is capped below the "satisfied" threshold by design.
- No published sites were available for training or validation, so no machine-learning model was fitted and no trilith
  alignments were drawn.
- The DEM is a surface model of the dune tops; the sub-dune base surface is an estimate.
- Landsat-1 MSS has detector striping. Change is relative per scene footprint, and block-shaped patterns follow scene
  edges (processing artefacts).
- The track detector has low sensitivity: many faint tracks are missed and some detections are dune slip faces.
- Weights are judgement calls. Borders are approximate (Natural Earth 1:10m). There is no ground truth, and none will
  be sought in this work.

## 6. False-positive risks (and how they were handled)

| Look-alike | Affects clues | Handling |
|---|---|---|
| Sabkha salt crusts, natural gypsum | 1, 5 | named in candidate notes; ASTER needed to separate |
| Calcrete, Pleistocene–Holocene lake marls | 1 | natural (though palaeo-environmentally relevant) |
| Wadi terminal fans | 3, 4 | named in notes |
| Dune slip faces, deflation scars | 4 | visible in snapshots (C03, C11) |
| Limestone joint sets, karst dolines | 4 | named in notes |
| Modern vehicle tracks radiating from Shisr | 2/4 | tracks on mapped roads excluded; unmapped ones remain possible |
| Oil-exploration seismic lines, pipelines, power lines | 2/4 | long-straight-line detection, mapped infrastructure, ×0.5 |
| Centre-pivot farms (Shisr, Muqshin area) | 4 | NDVI farm mask, 82.8 km² excluded |
| Leaking well at Umm Al Heesh | 1, 5 | documented; modern water |
| Sentinel-2 tile and date seams | all spectral layers | one date per orbit, cross-orbit matching, seam mask |

## 7. Next steps (desk-based only)

1. Add an Earth Engine service-account key as `EE_SERVICE_ACCOUNT_JSON` in the environment settings, then run
   `scripts/13_aster_gee.py`.
2. Allow `zenodo.org`, `osf.io` and `files.osf.io`, then run `scripts/14_published_sites.py`. The score step then
   trains and spatially cross-validates the classifier and the alignments step draws trilith lines.
3. Have archaeologists and geomorphologists review the candidates on high-resolution archive imagery.
4. Share results with the competent authorities (Oman Ministry of Heritage and Tourism; Saudi Heritage Commission)
   before any follow-up. This work includes no field visits.

## References

See the [README](../README.md#references-used-so-far) and the last slide of the presentation.
