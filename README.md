# NerdAxe / NerdQAxe / NerdOCTAXE — Home Assistant Integration

Monitors an ESP-Miner-family Bitcoin ASIC miner (NerdAxe, NerdQAxe, NerdOCTAXE, and
compatible boards running NerdOS/AxeOS) over its local REST API, and exposes a
power-profile switch so you can drop it into eco mode automatically — e.g. only
run full power when you have solar (PV) surplus.

No cloud, no account, purely local polling of `http://<device-ip>/api/system/info`.

## Install via HACS

1. HACS → the three-dot menu (top right) → **Custom repositories**
2. Add this repository URL, category **Integration**
3. Install "NerdAxe / NerdQAxe / NerdOCTAXE Miner", restart Home Assistant
4. Settings → Devices & Services → **Add Integration** → search "NerdAxe"
5. Enter the device's IP address (e.g. `10.0.1.80`)

## Entities

**Sensors** (polled every 30s): hashrate (current + 1h average), power, chip
temperature, voltage-regulator temperature, fan speed, frequency, actual core
voltage, accepted/rejected shares, duplicate HW nonces, best difficulty, WiFi
signal, uptime.

**`select.<device>_power_profile`** — `normal` / `eco` / `off`. `normal` and
`eco` PATCH frequency + core voltage to the device live (no reboot). `off`
POSTs `/api/system/shutdown`, which disables the ASICs and voltage regulators
(~0.06W measured, down from >100W) while leaving WiFi/HTTP alive — verified
against the firmware source that nothing clears this except a restart, so
selecting `eco`/`normal` again from `off` first POSTs `/api/system/restart`
and polls for up to 40s until the device answers again, then applies the
target settings. That round trip takes ~20-30s in practice; the select
service call will just sit there until it's done, which is normal.

If someone changes settings directly on the device's own web UI to something
that doesn't match any known profile, this entity shows as unknown rather
than guessing — that's intentional, not a bug.

## Eco profile

Defined in `custom_components/nerdaxe/const.py`:

```python
PROFILES = {
    "eco":    {"frequency": 400, "coreVoltage": 1070},
    "normal": {"frequency": 700, "coreVoltage": 1210},
}
```

These specific numbers came from stepping frequency and voltage down together
on a NerdOCTAXE-Gamma (8x BM1370) and watching `sharesRejected` /
`duplicateHWNonces` at each step over a 5-minute window:

| Frequency | Voltage (requested / actual) | Power | Result |
|---|---|---|---|
| 700 MHz | 1210 / 1210 mV | 213 W | baseline |
| 400 MHz | 1070 / 1070 mV | 109 W | clean — 0 errors over 5 min |
| 400 MHz | 1060 / **1054** mV | 109 W | voltage sag near the board's absMinVoltage (1050mV), **1 share rejected** |

213 W → 109 W is roughly **49% less power** for ~54% of the hashrate, and the
efficiency (W per TH/s) actually improves slightly at the lower point.

**Retune this for your own board/chip before trusting it** — silicon varies
between individual chips and boards, this is not a universal safe value. Step
down in ~10mV increments at your target frequency and watch `sharesRejected`
climb before you settle on a number. Individual per-ASIC control isn't
available on 8-chip chained boards like the NerdOCTAXE (they're a single hash
chain on one voltage rail), so this is necessarily a whole-board profile, not
per-chip.

## Example automation: three-tier PV following

Adjust `sensor.pv_surplus` (or whatever your grid-power sensor is called —
mind the sign convention, see below) and the thresholds to your own setup.
`off` below ~50W surplus (not worth running at all), `eco` between 50-250W,
`normal` above 250W:

```yaml
alias: Miner PV-following power profile
triggers:
  - trigger: numeric_state
    entity_id: sensor.pv_surplus
    below: 50
    for: "00:05:00"
    id: kein_ueberschuss
  - trigger: numeric_state
    entity_id: sensor.pv_surplus
    above: 50
    below: 250
    for: "00:05:00"
    id: wenig_ueberschuss
  - trigger: numeric_state
    entity_id: sensor.pv_surplus
    above: 250
    for: "00:05:00"
    id: viel_ueberschuss
conditions: []
actions:
  - choose:
      - conditions: [{ condition: trigger, id: kein_ueberschuss }]
        sequence:
          - action: select.select_option
            target: { entity_id: select.nerdoctaxe_power_profile }
            data: { option: "off" }
      - conditions: [{ condition: trigger, id: wenig_ueberschuss }]
        sequence:
          - action: select.select_option
            target: { entity_id: select.nerdoctaxe_power_profile }
            data: { option: "eco" }
      - conditions: [{ condition: trigger, id: viel_ueberschuss }]
        sequence:
          - action: select.select_option
            target: { entity_id: select.nerdoctaxe_power_profile }
            data: { option: "normal" }
mode: single
```

**Sign convention matters and varies by source.** A sensor literally named
"grid export" is usually positive when feeding in. Meters routed through
[evcc](https://evcc.io) are the opposite: positive = grid import, negative =
feed-in (confirmed against [evcc's meter docs](https://docs.evcc.io/en/reference/configuration/meters/)).
Check your actual sensor's sign with real numbers before trusting the
thresholds above — get it backwards and the miner runs full power exactly
when there's no surplus.

## Tested against

NerdOCTAXE-Gamma (8x BM1370), firmware v1.1.0-rc1, based on
[ESP-Miner-NerdQAxePlus](https://github.com/shufps/ESP-Miner-NerdQAxePlus).
Should work on any board exposing the same `/api/system/info` +
`PATCH /api/system` schema (Bitaxe/AxeOS family), but the profile wattages
above are specific to this one board and chip batch.
