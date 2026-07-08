"""Constants for the NerdAxe/NerdQAxe/NerdOCTAXE integration."""

DOMAIN = "nerdaxe"

DEFAULT_SCAN_INTERVAL = 30  # seconds
DEFAULT_PORT = 80

# ESP-Miner-family REST API (AxeOS / NerdOS)
API_INFO_PATH = "/api/system/info"
API_SETTINGS_PATH = "/api/system"
API_SHUTDOWN_PATH = "/api/system/shutdown"
API_RESTART_PATH = "/api/system/restart"

CONF_HOST = "host"

ATTR_FREQUENCY = "frequency"
ATTR_CORE_VOLTAGE = "coreVoltage"

# Power profiles: (frequency MHz, coreVoltage mV).
# "eco" was hand-tuned by stepping frequency and voltage down together and
# watching sharesRejected/duplicateHWNonces for a NerdOCTAXE-Gamma (8x
# BM1370) — 1070mV was the last point with zero errors over a 5-minute
# window; 1060mV showed voltage-regulation sag (1060 requested -> ~1054
# actual, near the board's absMinVoltage of 1050) and the first rejected
# share. Re-tune per board/chip if you use this on different hardware.
#
# "turbo" is the top of the board's own frequency dropdown (TPS53667 6-phase
# variant), stepped up from "normal" in 25MHz/10mV increments over ~50min —
# 54.1°C chip / 65°C VR at the top, zero rejected shares throughout, +14%
# hashrate over "normal" for +21% power (worse J/TH — a throughput/efficiency
# tradeoff, not a stability one).
PROFILES: dict[str, dict[str, int]] = {
    "eco": {ATTR_FREQUENCY: 400, ATTR_CORE_VOLTAGE: 1070},
    "normal": {ATTR_FREQUENCY: 700, ATTR_CORE_VOLTAGE: 1210},
    "turbo": {ATTR_FREQUENCY: 800, ATTR_CORE_VOLTAGE: 1250},
}

# Not a frequency/voltage pair — POSTs /api/system/shutdown instead, which
# disables the ASICs and voltage regulators (~0.06W measured) while leaving
# WiFi/HTTP alive. There is no API call that clears the firmware's internal
# shutdown flag other than a full restart (verified against firmware source:
# main/tasks/power_management_task.cpp only sets m_shutdown=false at
# construction, never elsewhere), so waking up from "off" means POSTing
# /api/system/restart and waiting for the device to come back.
OFF_PROFILE = "off"

DEFAULT_PROFILE = "normal"

# How long to poll for the device to come back after a restart-triggered wake.
WAKE_TIMEOUT_S = 40
WAKE_POLL_INTERVAL_S = 2
