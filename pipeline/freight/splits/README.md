# Measured coast splits (empty on purpose)

`ports.assign()` chooses one gateway from a coast rule, or lists the other coasts as options with no weight
(`basis` `"open"`, `w` `None`). A measured split would give each option a weight. Nothing is loaded from this folder
yet: no free source of such a split has been read and fetched.

When one is added, put one file per source here, named `<source>-<group>.json`, with the layout

```json
{
  "group": "wheat",
  "s": "usda-fgis",
  "url": "https://...",
  "y": 2024,
  "note": "export inspections by port region and destination",
  "splits": [
    {"o": "USA", "d": "JPN", "w": {"USKAM": 0.78, "USMSY": 0.22}}
  ]
}
```

and teach `ports.assign()` to read it (basis `"measured"`). Every weight must come from the file, never from memory.
First candidates (plan section 4): USDA FGIS export grain inspections for US grain by port region and destination,
then the Canadian Grain Commission for Canadian grain by port.
