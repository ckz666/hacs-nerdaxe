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

**Sensors** (polled every 30s), enabled by default: hashrate, power, chip
temperature, voltage-regulator temperature, fan speed, frequency, actual core
voltage, accepted/rejected shares, duplicate HW nonces, best difficulty, best
session difficulty.

Disabled by default (diagnostic/niche — enable manually if you want them):
1h-average hashrate, raw voltage, raw current, WiFi signal strength, uptime.

**Buttons**:
- **Restart** — fire-and-forget `POST /api/system/restart`. Doesn't wait for
  the device to come back, unlike waking from `off` below — a button press
  shouldn't hang the UI for the ~20-30s a real restart takes.
- **Shutdown** — same effect as selecting `off` on the power-profile entity
  below (`POST /api/system/shutdown`).

**`select.<device>_power_profile`** — `off` / `eco` / `normal` / `turbo`.
`eco`, `normal`, and `turbo` PATCH frequency + core voltage to the device
live (no reboot). `off` POSTs `/api/system/shutdown`, which disables the
ASICs and voltage regulators (~0.06W measured, down from >100W) while
leaving WiFi/HTTP alive — verified against the firmware source that nothing
clears this except a restart, so selecting a power profile again from `off`
first POSTs `/api/system/restart` and polls for up to 40s until the device
answers again, then applies the target settings. That round trip takes
~20-30s in practice; the select service call will just sit there until it's
done, which is normal.

If someone changes settings directly on the device's own web UI to something
that doesn't match any known profile, this entity shows as unknown rather
than guessing — that's intentional, not a bug.

## Power profiles

Defined in `custom_components/nerdaxe/const.py`:

```python
PROFILES = {
    "eco":    {"frequency": 400, "coreVoltage": 1070},
    "normal": {"frequency": 700, "coreVoltage": 1210},
    "turbo":  {"frequency": 800, "coreVoltage": 1250},
}
```

`eco`/`normal` came from stepping frequency and voltage down together on a
NerdOCTAXE-Gamma (8x BM1370) and watching `sharesRejected` /
`duplicateHWNonces` at each step over a 5-minute window:

| Frequency | Voltage (requested / actual) | Power | Result |
|---|---|---|---|
| 700 MHz | 1210 / 1210 mV | 213 W | baseline |
| 400 MHz | 1070 / 1070 mV | 109 W | clean — 0 errors over 5 min |
| 400 MHz | 1060 / **1054** mV | 109 W | voltage sag near the board's absMinVoltage (1050mV), **1 share rejected** |

213 W → 109 W is roughly **49% less power** for ~54% of the hashrate, and the
efficiency (W per TH/s) actually improves slightly at the lower point.

`turbo` is the top of the same board's frequency range (TPS53667 6-phase
variant), stepped up from `normal` in 25MHz/10mV increments over ~50 minutes,
watching chip/VR temperature and rejected shares at each step: 54.1°C chip /
65°C VR at the top, zero rejected shares throughout, **+14% hashrate over
`normal` for +21% power** — a throughput/efficiency tradeoff (worse J/TH),
not a stability issue.

**Retune all of this for your own board/chip before trusting it** — silicon
varies between individual chips and boards, none of these are universal safe
values. Step in small increments at your target frequency and watch
`sharesRejected` (and chip/VR temperature for anything above `normal`) before
you settle on a number. Individual per-ASIC control isn't available on
8-chip chained boards like the NerdOCTAXE (they're a single hash chain on one
voltage rail), so this is necessarily a whole-board profile, not per-chip.

## Example automation: three-tier PV following

Adjust `sensor.pv_surplus` (or whatever your grid-power sensor is called —
mind the sign convention, see below) and the thresholds to your own setup.
`off` below ~50W surplus (not worth running at all), `eco` between 50-250W,
`normal` above 250W. Add a fourth `numeric_state` trigger/choice the same way
if you want `turbo` at some higher surplus threshold — omitted here to keep
the example simple, since `turbo`'s +21% power for +14% hashrate is a much
more marginal trade than `eco` vs. `normal`.

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

## Extended example: forecast + battery-aware following

A plain-surplus automation only looks at *this instant*. It'll happily drain
the battery chasing a `turbo` reading that a cloud kills 30 seconds later,
and it'll shut the miner off during a brief consumption spike even though
the battery's already full and that power has nowhere else to go. This
version adds PV forecast and battery SOC/ETA on top of a grid-surplus
reading, so the profile reacts to where the day's energy is headed instead
of just the current number.

**This is a real, currently-deployed automation** (SolaX inverter/battery
via [solax_modbus](https://github.com/wills106/homeassistant-solax-modbus),
Tasmota grid meter, official **Forecast.Solar** integration with 4 array
orientations) — the templates below were rendered live against real sensor
data and the automation was triggered end-to-end without errors before this
was written up. What's **not** independently validated is the tuning itself
(the 30%/95%/15min/150W/etc. thresholds) — those are this author's first-pass
numbers, not something watched over weeks of real operation. Swap in your
own entity IDs (grid meter, select entity, battery sensors — check
**Developer Tools → States**) and expect to retune the thresholds for your
own battery capacity and consumption pattern.

```yaml
alias: Miner PV+battery-aware power profile
description: >
  Four-tier (off/eco/normal/turbo) on grid surplus (sensor.leistung_2,
  Tasmota meter, negative = feed-in/surplus), extended with battery
  SOC/ETA-to-full and today's remaining PV forecast. Battery protection
  takes priority over the plain surplus tier: low SOC caps the profile,
  a full/near-full battery gets bumped up early since the marginal watt is
  headed for curtailment/export otherwise.
triggers:
  # Original surplus-tier triggers — same 50/250/350W thresholds as a
  # plain-surplus automation, just re-fired here so a fast-changing
  # surplus is still picked up immediately rather than waiting for the
  # timer trigger below.
  - trigger: numeric_state
    entity_id: sensor.leistung_2
    above: -50
    for: { minutes: 5 }
    id: leistung
  - trigger: numeric_state
    entity_id: sensor.leistung_2
    below: -50
    above: -250
    for: { minutes: 5 }
    id: leistung
  - trigger: numeric_state
    entity_id: sensor.leistung_2
    below: -250
    above: -350
    for: { minutes: 5 }
    id: leistung
  - trigger: numeric_state
    entity_id: sensor.leistung_2
    below: -350
    for: { minutes: 5 }
    id: leistung
  - trigger: state
    entity_id: sensor.solax_battery_capacity
    for: { minutes: 5 }
    id: akku
  # Catch-all: re-evaluates every 5 minutes even with no state change, so
  # a battery crossing 95% mid-tier (rather than via a discrete event) or
  # the forecast quietly dropping still gets picked up.
  - trigger: time_pattern
    minutes: "/5"
    id: takt
conditions: []
actions:
  - variables:
      # --- entity IDs below are this author's — swap for your own ---
      ueberschuss_w: "{{ (states('sensor.leistung_2') | float(0)) * -1 }}"
      soc: "{{ states('sensor.solax_battery_capacity') | float(100) }}"
      ladeleistung_w: "{{ states('sensor.solax_battery_power_charge') | float(0) }}"
      akku_kapazitaet_wh: 24000  # usable battery capacity — adjust to yours
      hausverbrauch_w: "{{ states('sensor.hausverbrauch_schnell') | float(0) }}"
      # Sum of all forecast planes/orientations — a single-array setup
      # only needs the one sensor.energy_production_today_remaining term.
      pv_rest_heute_kwh: >
        {{ (states('sensor.energy_production_today_remaining') | float(0))
         + (states('sensor.energy_production_today_remaining_2') | float(0))
         + (states('sensor.energy_production_today_remaining_3') | float(0))
         + (states('sensor.energy_production_today_remaining_4') | float(0)) }}
  - variables:
      # solax_modbus doesn't expose a time-to-full sensor, so it's computed
      # here from SOC + charge power + capacity instead. If your battery
      # integration already provides one, read that directly and drop this.
      eta_minuten: >
        {{ (0 if (ladeleistung_w <= 0 or soc >= 100) else
           (((100 - soc) / 100 * akku_kapazitaet_wh) / ladeleistung_w * 60))
           | round(0) }}
      akku_niedrig: "{{ soc < 30 }}"
      viel_sonne_uebrig: "{{ pv_rest_heute_kwh > 5 }}"
  - variables:
      akku_fast_voll: >
        {{ soc > 95 or (eta_minuten | float(999) > 0 and eta_minuten | float(999) < 15) }}
  - choose:
      # Battery needs the power more than the miner does right now — cap
      # at eco (or off, if there's barely any surplus at all), unless the
      # surplus is big enough for both.
      - conditions:
          - "{{ akku_niedrig and ueberschuss_w < 350 }}"
        sequence:
          - action: select.select_option
            target: { entity_id: select.octaxe_leistungsprofil }
            data: { option: "{{ 'eco' if ueberschuss_w > 50 else 'off' }}" }
      # Battery's done (or nearly) — don't waste the marginal watt on
      # curtailment/export, push it into the miner instead.
      - conditions:
          - "{{ akku_fast_voll and ueberschuss_w > 150 }}"
        sequence:
          - action: select.select_option
            target: { entity_id: select.octaxe_leistungsprofil }
            data: { option: "turbo" }
      - conditions:
          - "{{ ueberschuss_w > 350 }}"
        sequence:
          - action: select.select_option
            target: { entity_id: select.octaxe_leistungsprofil }
            data: { option: "turbo" }
      # Solid surplus, or decent surplus with plenty more sun forecast today.
      - conditions:
          - "{{ ueberschuss_w > 250 or (viel_sonne_uebrig and ueberschuss_w > 150) }}"
        sequence:
          - action: select.select_option
            target: { entity_id: select.octaxe_leistungsprofil }
            data: { option: "normal" }
      - conditions:
          - "{{ ueberschuss_w > 50 }}"
        sequence:
          - action: select.select_option
            target: { entity_id: select.octaxe_leistungsprofil }
            data: { option: "eco" }
    default:
      - action: select.select_option
        target: { entity_id: select.octaxe_leistungsprofil }
        data: { option: "off" }
mode: single
```

`hausverbrauch_w` is read but deliberately **not** used to gate any
decision — the grid-meter reading already nets out house consumption vs.
PV vs. battery flow at the connection point, so gating on it too would be
redundant rather than additive. It's there for logging/future refinement.

It's *not* read from the SolaX integration's own "House Load" sensor —
that one turned out to swing negative (confirmed live: -2775 W at one
point), making it unusable as a plain consumption figure. The dashboard's
own "current consumption" tile is a built-in aggregate badge with no
single backing entity to read from either. What worked instead: a
[Template Sensor helper](https://www.home-assistant.io/integrations/template/)
computing `PV total + grid − battery charge` from the same fast
SolaX/Tasmota sensors already used elsewhere in this automation —

```jinja
{{ (states('sensor.solax_pv_power_total') | float(0))
 + (states('sensor.bungalow_inverter_watts') | float(0))
 + (states('sensor.pv_leistung_channel_1_power') | float(0))
 + (states('sensor.leistung_2') | float(0))
 - (states('sensor.solax_battery_power_charge') | float(0)) }}
```

— validated against a slower-but-trusted reference (an evcc "home power"
sensor) at the same instant: 1788.6 W computed vs. 1786.6 W from evcc,
well within measurement noise, but updating on every source-sensor change
instead of evcc's slower poll cycle. The PV terms are specific to this
setup's three solar sources (SolaX inverter + a second inverter + a
Shelly PV plug) — total them up for however many sources you actually
have, and use whatever your own grid meter and battery-charge-power
entities are.

A `time_pattern` trigger (every 5 minutes) runs alongside the original
`numeric_state`/`for:` triggers rather than replacing them — `for:` on a
continuously-changing power sensor only fires when the state genuinely
stops changing for the whole window, which a battery SOC crossing a
threshold gradually (not via a discrete event) won't reliably do on its
own. The timer catches what the event-based triggers miss.

## Tested against

NerdOCTAXE-Gamma (8x BM1370), firmware v1.1.0-rc1, based on
[ESP-Miner-NerdQAxePlus](https://github.com/shufps/ESP-Miner-NerdQAxePlus).
Should work on any board exposing the same `/api/system/info` +
`PATCH /api/system` schema (Bitaxe/AxeOS family), but the profile wattages
above are specific to this one board and chip batch.
