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

The plain-surplus version above only looks at *this instant*. It'll happily
drain your battery chasing a `turbo` reading that a cloud kills 30 seconds
later, and it'll shut the miner off during a brief consumption spike even
though the battery's already full and that power has nowhere else to go.
This version adds three more signals: how much sun is still forecast today,
how full the battery already is (and how soon it'll top up), and a
smoothed house-consumption baseline so short-lived spikes don't flip the
profile back and forth.

**This logic is a design sketch, not something measured against real
hardware/data like the profile wattages above** — treat the thresholds as a
starting point and watch how it actually behaves for a few days before
trusting it unattended.

Entity IDs below assume the official **Forecast.Solar** integration
(`sensor.energy_production_today_remaining`, kWh remaining for the rest of
today). Swap in your own if you use Solcast or your inverter vendor's own
forecast instead.

For **SolaX**, `sensor.battery_soc` should map to whatever your SolaX
integration calls the battery capacity/SOC sensor — with the popular
[solax_modbus](https://github.com/wills106/homeassistant-solax-modbus) HACS
integration this is typically something like `sensor.solax_battery_capacity`
(exact name depends on your inverter model/prefix — check **Developer
Tools → States** and filter for `battery` to get your real entity ID rather
than trusting this name blindly). solax_modbus does **not** expose a
time-to-full sensor directly, so `battery_eta_full_min` needs to be computed
rather than read — a template helper for that is below. If you're on a
different SolaX integration (cloud-API based) that does expose one, use that
directly instead and skip the template.

```yaml
# Template helper (Settings -> Devices & Services -> Helpers -> Template ->
# Template a sensor), computing minutes-to-full from SOC + battery capacity
# + current charge power. Adjust entity IDs and battery_capacity_kwh to
# your actual system.
- name: "Battery Time To Full"
  unit_of_measurement: "min"
  state: >
    {% set soc = states('sensor.solax_battery_capacity') | float(100) %}
    {% set charge_power_w = states('sensor.solax_battery_power_charge') | float(0) %}
    {% set battery_capacity_kwh = 10.0 %}  {# your usable battery capacity #}
    {% if charge_power_w <= 0 or soc >= 100 %}
      0
    {% else %}
      {{ (((100 - soc) / 100 * battery_capacity_kwh * 1000) / charge_power_w * 60) | round(0) }}
    {% endif %}
```

`sensor.house_average_consumption` is meant to be a helper you create
yourself (e.g. a `Statistics` or `derivative` helper with a 10-15 min window
over your house-load sensor) — it exists purely to stop the miner flapping
on a kettle or oven cycling on.

```yaml
alias: Miner PV+battery-aware power profile
description: >
  Extends the plain-surplus automation with today's remaining PV forecast,
  battery state of charge / time-to-full, and a smoothed house-consumption
  baseline, so the profile reacts to where the day's energy is headed
  instead of just this instant's surplus reading.
triggers:
  - trigger: time_pattern
    minutes: "/5"
conditions: []
actions:
  - variables:
      # --- ADJUST THESE ENTITY IDS to match your own setup ---
      pv_surplus: "{{ states('sensor.pv_surplus') | float(0) }}"
      pv_forecast_remaining_kwh: "{{ states('sensor.energy_production_today_remaining') | float(0) }}"
      battery_soc: "{{ states('sensor.battery_soc') | float(100) }}"
      battery_eta_full_min: "{{ states('sensor.battery_time_to_full') | float(999) }}"
      house_avg_consumption: "{{ states('sensor.house_average_consumption') | float(0) }}"

      # Battery is low: that marginal watt is worth more to the house/
      # battery right now than to the miner. Cap at "eco" even with some
      # surplus; force "off" if there's barely any surplus at all.
      battery_low: "{{ battery_soc < 30 }}"
      # Battery is effectively full, or about to be within a few minutes:
      # the marginal watt is now worth more to the miner than the battery,
      # since it's headed for curtailment/grid export otherwise. Lean into
      # turbo rather than waiting for a bigger instantaneous surplus.
      battery_topped_up: "{{ battery_soc > 95 or battery_eta_full_min < 15 }}"
      # Meaningful sun left today -> safe to spend surplus now instead of
      # holding back "just in case" for a shortfall that likely won't come.
      strong_forecast_left: "{{ pv_forecast_remaining_kwh > 5 }}"
      # Smoothed baseline instead of the raw instantaneous surplus, so a
      # kettle or oven cycling on for a few minutes doesn't flip the
      # profile back and forth.
      effective_surplus: "{{ pv_surplus - (house_avg_consumption * 0.2) }}"
  - choose:
      # Battery needs the power more than the miner does right now.
      - conditions:
          - "{{ battery_low and effective_surplus < 250 }}"
        sequence:
          - action: select.select_option
            target: { entity_id: select.nerdoctaxe_power_profile }
            data: { option: "off" }
      # Battery's done (or nearly), and there's real surplus -> don't waste it.
      - conditions:
          - "{{ battery_topped_up and effective_surplus > 100 }}"
        sequence:
          - action: select.select_option
            target: { entity_id: select.nerdoctaxe_power_profile }
            data: { option: "turbo" }
      # Solid surplus, or decent surplus with plenty more sun forecast today.
      - conditions:
          - "{{ effective_surplus > 250 or (strong_forecast_left and effective_surplus > 100) }}"
        sequence:
          - action: select.select_option
            target: { entity_id: select.nerdoctaxe_power_profile }
            data: { option: "normal" }
      - conditions:
          - "{{ effective_surplus > 50 }}"
        sequence:
          - action: select.select_option
            target: { entity_id: select.nerdoctaxe_power_profile }
            data: { option: "eco" }
    default:
      - action: select.select_option
        target: { entity_id: select.nerdoctaxe_power_profile }
        data: { option: "off" }
mode: single
```

A `time_pattern` trigger (every 5 minutes) is used instead of a `state`
trigger with `for:` — a `for:` duration on a continuously-changing power
sensor practically never fires, since it requires the state to stop
changing entirely for that whole window. Polling on a timer sidesteps that
and reads all the current values fresh each time.

`effective_surplus` subtracting a fraction of `house_avg_consumption` is one
way to build in a safety margin against baseline load that a laggy
`pv_surplus` sensor hasn't caught up to yet — the `0.2` factor is a guess,
not a measurement; tune it against your own sensor's actual lag and noise.

## Tested against

NerdOCTAXE-Gamma (8x BM1370), firmware v1.1.0-rc1, based on
[ESP-Miner-NerdQAxePlus](https://github.com/shufps/ESP-Miner-NerdQAxePlus).
Should work on any board exposing the same `/api/system/info` +
`PATCH /api/system` schema (Bitaxe/AxeOS family), but the profile wattages
above are specific to this one board and chip batch.
