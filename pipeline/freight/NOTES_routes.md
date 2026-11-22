# Freight reference data: verification notes

Research limits: balticexchange.com blocks automated fetches (returns a "Challenge Validation" page), so no Baltic page or Guide to Market Benchmarks PDF could be read directly. Benchmark definitions were verified from the Veson VesselsValue summary of Baltic definitions (`veson-baltic-defs`), Baltic circular titles/snippets surfaced by search (`baltic-circulars`), CFTC filings, and press. Non-benchmark routes are editorial (`s: "atlas"`) and not individually sourced.

## Verified at region level and cargo size (via Veson page unless noted)
C3, C5, C7, C17 (170kt from bmti-report), C10_14, C14, P1A/2A/3A/6_82, S1C/S2/S4A/S10, HS1-7_38, TD3C, TD15, TD22, TD6, TD7, TD8, TD9, TD19, TD20 (CFTC: Bonny-Rotterdam 130kt), TD23, TD25, TD26, TD27 (Baltic circular), TC1, TC2_37, TC5, TC6, TC7, TC8, TC10, TC12, TC14, TC15, TC16, TC17, TC18, TC19, BLNG1-3, BLPG1-3.

## Not verified / uncertain
- All **port names** are market convention (Ras Tanura, Ningbo, Houston, Rotterdam...), not taken from Baltic text (exceptions: Bonny-Rotterdam for TD20; BLNG origins from circular snippets). Treat as drawing anchors only.
- **Cargo sizes omitted** for C3, C5, C7 (secondary source says 160-170kt / 150-160kt; Baltic revised C2/C3/C7/C14 in 2024-25 and the new wording could not be read), TC20, TC21.
- **TC20, TC21**: no definition found. TC21 = US Gulf-Caribbean per a search snippet; TC20 (MEG-UK-Continent, LR2) is from recollection. No parcel given.
- **TD1**: dropped (could not confirm it exists). **TD2**: ceased 1 Aug 2024 (Circular 15/24), kept as discontinued. **TD17, TC9**: ceased 24 Dec 2025 (Circular 35/25), kept as discontinued; TD24 omitted (not requested).
- **TD34** (Mina al-Fahal-Ningbo, 270kt): created 2026 because of Hormuz disruption; public-trial status. The April 2026 Baltic consultation on Middle East methodology may change TD3C and other Gulf routes; current status of TD3C, TC1, TC5, TC8, TC17, TD8, TD23 not confirmed.
- **TD6** (Black Sea-Med): status unclear since 2022 sanctions.
- **TD15, TC8, TC10, TC15**: on Veson page, 2025-26 status not confirmed.
- **S10_63**: BDI moved from S10TC to S11TC (Aug 2024), so S10 may no longer be reported. Veson lists Supramax routes as _58; Baltic moved the standard to 63,500 dwt (Circular 09/23), so _63 codes are assumed.
- **Capesize standard** moved from 180,000 to 182,000 dwt (C5TC(182), 2 Jan 2026) per Baltic circulars.
- **C10_14**: described as a Pacific round voyage; Veson calls it "China-Japan transpacific round voyage".
- **Gas**: BLNG now the "-174" series (174,000 cbm): Australia-Japan, US Gulf-Continent, US Gulf-Japan. Older text (Gladstone-Tokyo, Sabine-Isle of Grain, Sabine-Tokyo via Panama) still appears on Veson. BLNG3 via Panama is from the older definition. BLPG parcel 44kt is from Veson; its VLGC TCE vessel is "84kt", and the 84,000 cbm class size in vessel_classes.json is an assumption.
- Corridors that would overlap were split to avoid double counting: TD25 (ARA/UKC) vs usgulf-med-crude; TC5 holds MEG-Japan products (TC1 empty); middle-east-europe-diesel holds TC8/TC20; TD34 has no corridor; guyana-europe-crude has none (TD27 holds it).
- Lithium (spodumene) is not in the atlas commodity list: that route has empty cargoes/corridor.
- Several non-benchmark country lists (e.g. Argentina soymeal/corn destinations, Black Sea wheat destinations, Vancouver potash destinations) are editorial selections and should be replaced by customs-derived shares later.

## Canal limits (discrepancies)
- **Panama**: Panamax locks LOA 289.56 m (950 ft); 294.13 m applies only to container/passenger ships (Wikipedia citing PCA), whereas the brief gave 294.13 m for all. Beam 32.31 m and TFW draft 12.04 m confirmed. Neopanamax: beam 51.25 m (raised from 49 m in 2018), draft 15.24 m, and **LOA 370.33 m since May 2021** (PCA news), not 366 m (original). The live PCA "Vessel Requirements" page returned 404, so these come from the PCA news page plus Wikipedia.
- **Suez**: 20.1 m (66 ft) draft for beam up to 50 m with a 1,006 m2 wetted-area cap (Wikipedia/EIA citing SCA). SCA tables not fetched directly.

## Vessel class size ranges
Min/max/typical values are conventional industry ranges plus Baltic reference vessels (Capesize 182k, Kamsarmax/"Panamax" 82k, Ultramax 63.5k, Supramax 58k, Handysize 38k, VLCC 300k, Suezmax 160k, Aframax 105k, LR1 75k, MR 47k per Veson). They are not from a single authoritative table. Newcastlemax (185-210k), VLOC (230-400k), handy tanker 37k, LR2, and LNG Q-Flex/Q-Max ranges are unverified. `dims` only where sourced: Suezmax draft/beam (SCA limits), Newcastlemax maxima (Wikipedia), Kamsarmax 229 m LOA.
