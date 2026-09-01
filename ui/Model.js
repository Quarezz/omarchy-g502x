function shortName(model) {
  var name = String(model || "G502 X")
  name = name.replace(/^Logitech\s+/i, "")
  name = name.replace(/\s+LIGHTSPEED$/i, "")
  name = name.replace(/\s+LS$/i, "")
  name = name.replace(/\s+/g, " ").replace(/^\s+|\s+$/g, "")
  return name || "G502 X"
}

function mouseIcon() {
  return "󰍽"
}

function parseStatus(raw) {
  try {
    var next = JSON.parse(String(raw || "").replace(/^\s+|\s+$/g, ""))
    return next && typeof next === "object" ? next : {}
  } catch (e) {
    return {}
  }
}

function parsePercent(value) {
  if (value === null || value === undefined || value === "") return -1
  var n = Number(value)
  if (!isFinite(n)) return -1
  return Math.max(0, Math.min(100, Math.round(n)))
}

function parseDpi(value) {
  if (value === null || value === undefined || value === "") return -1
  var n = Number(value)
  if (!isFinite(n) || n <= 0) return -1
  return Math.round(n)
}

function formatDpi(dpi) {
  var value = parseDpi(dpi)
  if (value <= 0) return "—"
  return String(value) + " DPI"
}

function dpiPresets() {
  return [400, 800, 1600, 3200, 6400]
}

function nextDpi(current, delta) {
  var list = dpiPresets()
  var value = parseDpi(current)
  var step = Number(delta)
  if (!isFinite(step) || step === 0) return value
  var idx = -1
  var best = 0
  var bestDist = 1e9
  for (var i = 0; i < list.length; i++) {
    if (list[i] === value) idx = i
    var dist = Math.abs(list[i] - value)
    if (dist < bestDist) {
      bestDist = dist
      best = i
    }
  }
  if (idx < 0) idx = best
  idx = Math.max(0, Math.min(list.length - 1, idx + (step > 0 ? 1 : -1)))
  return list[idx]
}

function batteryBand(percent) {
  var n = parsePercent(percent)
  if (n < 0) return "unknown"
  if (n < 25) return "red"
  if (n < 50) return "yellow"
  return "green"
}

function chargeLabel(low, full, charging, discharging) {
  if (low) return "Low"
  if (full) return "Full"
  if (charging) return "Plugged in"
  if (discharging) return "On battery"
  return "—"
}

function isOn(value) {
  return value === true || value === "true" || value === 1 || value === "1"
}

function shouldWarnLowBattery(percent, discharging, threshold, alreadyNotified) {
  var level = Number(percent)
  var limit = Number(threshold)
  if (!isFinite(level) || level < 0 || !isFinite(limit)) {
    return { level: -1, notify: false, notifiedLowBattery: false }
  }
  var low = discharging && level <= limit
  return {
    level: level,
    notify: low && !alreadyNotified,
    notifiedLowBattery: low
  }
}

if (typeof module !== "undefined") {
  module.exports = {
    shortName: shortName,
    mouseIcon: mouseIcon,
    parseStatus: parseStatus,
    parsePercent: parsePercent,
    parseDpi: parseDpi,
    formatDpi: formatDpi,
    dpiPresets: dpiPresets,
    nextDpi: nextDpi,
    batteryBand: batteryBand,
    chargeLabel: chargeLabel,
    isOn: isOn,
    shouldWarnLowBattery: shouldWarnLowBattery
  }
}
