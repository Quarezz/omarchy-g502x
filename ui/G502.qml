import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

BarWidget {
  id: root
  moduleName: "morf.g502x"

  readonly property bool showPercentage: Model.isOn(setting("showPercentage", true))
  readonly property int lowBatteryPercent: {
    var value = Number(setting("lowBatteryPercent", 15))
    if (!isFinite(value)) return 15
    return Math.max(5, Math.min(40, Math.round(value)))
  }

  property var status: ({})
  readonly property bool mousePresent: status.present === true
  readonly property string deviceTitle: Model.shortName(status.model)
  readonly property int batteryPercent: Model.parsePercent(status.percent)
  readonly property real batteryFraction: batteryPercent < 0 ? 0 : batteryPercent / 100
  readonly property bool charging: status.charging === true
  readonly property bool discharging: status.discharging === true
  readonly property bool fullyCharged: status.full === true
  readonly property bool lowBattery: mousePresent && discharging && batteryPercent >= 0 && batteryPercent <= lowBatteryPercent
  readonly property string mouseIcon: Model.mouseIcon()
  readonly property int dpi: Model.parseDpi(status.dpi)
  readonly property var dpiPresets: Model.dpiPresets()
  readonly property color batteryColor: {
    var band = Model.batteryBand(batteryPercent)
    if (band === "red") return bar ? bar.urgent : Color.urgent
    if (band === "yellow") return "#e0c35a"
    if (band === "green") return "#62c46f"
    return bar ? bar.barForeground : Color.foreground
  }
  readonly property string modeLabel: {
    if (!mousePresent) return "Not connected"
    if (fullyCharged) return "Fully charged"
    if (charging) return "Charging"
    if (discharging) return "Discharging"
    return String(status.status || "Standing by")
  }

  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false
  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false
  property bool dpiBusy: false

  function open() { if (panelLoader.item) panelLoader.item.open() }
  function close() { if (panelLoader.item) panelLoader.item.close() }
  function togglePanel() { if (panelLoader.item) panelLoader.item.toggle() }
  function closeForPopoutSwitch() { if (panelLoader.item) panelLoader.item.closeForPopoutSwitch() }

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    target.bar = root.bar
    target.settings = root.settings
    target.anchorItem = button
    target.hostWidget = root
  }

  function scriptPath(name) {
    var url = String(Qt.resolvedUrl("../scripts/" + name))
    return decodeURIComponent(url.replace(/^file:\/\//, ""))
  }

  function refresh() {
    if (!statusProc.running && !dpiSetProc.running) statusProc.running = true
  }

  function applyStatus(raw) {
    var next = Model.parseStatus(raw)
    if (!next || typeof next !== "object") return
    var keys = Object.keys(next)
    if (keys.length === 0) return
    status = next
  }

  function setDpi(value) {
    var next = Model.parseDpi(value)
    if (next <= 0 || dpiSetProc.running) return
    var merged = {}
    for (var key in status) merged[key] = status[key]
    merged.dpi = next
    status = merged
    dpiBusy = true
    dpiSetProc.command = ["/usr/bin/python3", root.scriptPath("status.py"), "--set-dpi", String(next)]
    dpiSetProc.running = true
  }

  function nudgeDpi(delta) {
    root.setDpi(Model.nextDpi(root.dpi, delta))
  }

  function checkLowBattery() {
    var state = Model.shouldWarnLowBattery(batteryPercent, discharging, lowBatteryPercent, persisted.notifiedLowBattery)
    persisted.notifiedLowBattery = state.notifiedLowBattery
    if (state.notify) sendLowBatteryWarning(state.level)
  }

  function sendLowBatteryWarning(level) {
    Quickshell.execDetached([
      "omarchy-notification-send",
      "-g", root.mouseIcon,
      "-u", "critical",
      "--app-name", "G502 X",
      "Time to recharge!",
      deviceTitle + " is down to " + level + "%",
      "-t", "30000"
    ])
  }

  visible: mousePresent
  implicitWidth: mousePresent ? button.implicitWidth : 0
  implicitHeight: mousePresent ? button.implicitHeight : 0

  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()
  onMousePresentChanged: if (!mousePresent) close()
  onBatteryPercentChanged: checkLowBattery()
  onDischargingChanged: checkLowBattery()
  onOpenedChanged: if (opened) refresh()
  Component.onCompleted: {
    refresh()
    checkLowBattery()
  }

  PersistentProperties {
    id: persisted
    reloadableId: "morf-g502x"
    property bool notifiedLowBattery: false
  }

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Popup.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  IpcHandler {
    target: "morf.g502x"

    function open() { root.open() }
    function close() { root.close() }
    function show() { root.open() }
    function hide() { root.close() }
    function toggle() { root.togglePanel() }
    function refresh() { root.refresh() }
  }

  Process {
    id: statusProc
    command: ["/usr/bin/python3", root.scriptPath("status.py")]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.applyStatus(text)
    }
    stderr: StdioCollector { waitForEnd: true }
  }

  Process {
    id: dpiSetProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.applyStatus(text)
    }
    stderr: StdioCollector { waitForEnd: true }
    onExited: root.dpiBusy = false
  }

  Timer {
    interval: root.opened ? 5000 : 12000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  Timer {
    interval: 30000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.checkLowBattery()
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    useActiveColor: false
    foreground: root.batteryColor
    text: root.mouseIcon
    slotSize: Style.bar.iconSlot
    tooltipText: ""
    onPressed: function(b) {
      if (!root.mousePresent) return
      root.togglePanel()
    }
  }
}
