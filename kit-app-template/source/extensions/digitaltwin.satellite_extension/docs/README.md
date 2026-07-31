# Satellite Digital Twin Extension

Builds an animated GPS/navigation-style satellite in the current USD stage:

- Hexagonal bus (gold MLI look)
- Two solar wings on booms (+X / -X) with slow sun-tracking rotation
- Nadir antenna farm: 4 helical L-band antennas + a high-gain dish on a short boom
- Zenith omni whip
- Orbits the World origin in the XZ plane; bus yaws slowly about Y

Modeled after `digitaltwin.xlerobot_extension` — pure USD prims + a per-frame update sub.
