import SwiftUI
import CoreBluetooth
import AppIntents

@main struct OmiBatteryApp: App {
    @StateObject var reader = BatteryReader()
    @Environment(\.scenePhase) var phase
    var body: some Scene {
        WindowGroup {
            ContentView().environmentObject(reader)
                .onChange(of: phase) { _, p in if p == .active { reader.start() } }
        }
    }
}

/// Scan → connect → read Battery Level (0x180F/0x2A19) → disconnect immediately. Never pairs, never stays connected,
/// so the Mac (omi-local) can still sync. Gives up after 15 s.
final class BatteryReader: NSObject, ObservableObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    static let battSvc = CBUUID(string: "180F"), battChr = CBUUID(string: "2A19")
    static let omiSvc = CBUUID(string: "19b10000-e8f2-537e-4f6c-d104768a1214")
    @Published var status = "…"
    @Published var level: Int? = UserDefaults.standard.object(forKey: "level") as? Int
    @Published var at: Date? = UserDefaults.standard.object(forKey: "at") as? Date
    private var cm: CBCentralManager?
    private var target: CBPeripheral?
    private var timer: Timer?
    /// iOS's own peripheral identifier (differs from the Mac's). Set on first successful read.
    @Published var paired: UUID? = (UserDefaults.standard.string(forKey: "paired")).flatMap(UUID.init)
    func reRegister() { UserDefaults.standard.removeObject(forKey: "paired"); paired = nil; start() }

    func start() {
        guard target == nil else { return }
        status = "探しています… / Scanning"
        if cm == nil { cm = CBCentralManager(delegate: self, queue: .main) } else { scan() }
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 15, repeats: false) { [weak self] _ in
            self?.finish("見つかりません（Macと接続中？ボタンを1回押して再試行）/ Not found")
        }
    }
    private var seen: [UUID: CBPeripheral] = [:]
    private func scan() {
        seen = [:]
        if paired == nil {
            DispatchQueue.main.asyncAfter(deadline: .now() + 4) { [weak self] in
                guard let self, self.target == nil, self.paired == nil else { return }
                if self.seen.count == 1, let p = self.seen.values.first { self.connect(p) }
                else if self.seen.count > 1 { self.finish("近くにOmiが\(self.seen.count)台。自分のだけ近づけて再試行 / Several Omis nearby") }
            }
        }
        guard cm?.state == .poweredOn else { return }
        // Already connected by this phone? (shouldn't be, but handle)
        if let p = cm?.retrieveConnectedPeripherals(withServices: [Self.omiSvc]).first(where: { paired == nil || $0.identifier == paired }) { connect(p); return }
        cm?.scanForPeripherals(withServices: nil, options: nil)
    }
    private func connect(_ p: CBPeripheral) {
        cm?.stopScan(); target = p; p.delegate = self
        status = "接続中… / Connecting"; cm?.connect(p, options: nil)
    }
    private func finish(_ s: String) {
        timer?.invalidate(); cm?.stopScan()
        if let p = target { cm?.cancelPeripheralConnection(p) }
        target = nil; status = s
    }
    func centralManagerDidUpdateState(_ c: CBCentralManager) {
        switch c.state {
        case .poweredOn: scan()
        case .unauthorized: finish("Bluetoothの許可が必要（設定 → Omi電池）")
        case .poweredOff: finish("Bluetoothがオフです")
        default: break
        }
    }
    func centralManager(_ c: CBCentralManager, didDiscover p: CBPeripheral, advertisementData ad: [String: Any], rssi: NSNumber) {
        let name = (ad[CBAdvertisementDataLocalNameKey] as? String) ?? p.name ?? ""
        let svcs = (ad[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID]) ?? []
        guard name == "Omi" || name == "Friend" || svcs.contains(Self.omiSvc) else { return }
        if let id = paired, p.identifier != id { return }  // someone else's pendant: ignore
        if paired == nil { seen[p.identifier] = p; return } // first time: collect, decide after a short window
        connect(p)
    }
    func centralManager(_ c: CBCentralManager, didConnect p: CBPeripheral) { p.discoverServices([Self.battSvc]) }
    func centralManager(_ c: CBCentralManager, didFailToConnect p: CBPeripheral, error: Error?) { finish("接続失敗 / Connect failed") }
    func peripheral(_ p: CBPeripheral, didDiscoverServices error: Error?) {
        guard let s = p.services?.first(where: { $0.uuid == Self.battSvc }) else { return finish("電池サービスなし") }
        p.discoverCharacteristics([Self.battChr], for: s)
    }
    func peripheral(_ p: CBPeripheral, didDiscoverCharacteristicsFor s: CBService, error: Error?) {
        guard let ch = s.characteristics?.first(where: { $0.uuid == Self.battChr }) else { return finish("電池特性なし") }
        p.readValue(for: ch)
    }
    func peripheral(_ p: CBPeripheral, didUpdateValueFor ch: CBCharacteristic, error: Error?) {
        guard let b = ch.value?.first else { return finish("読み取り失敗") }
        level = Int(b); at = Date()
        if paired == nil { paired = p.identifier; UserDefaults.standard.set(p.identifier.uuidString, forKey: "paired") }
        UserDefaults.standard.set(level, forKey: "level"); UserDefaults.standard.set(at, forKey: "at")
        finish("OK（切断済み / disconnected）")
    }
}

struct ContentView: View {
    @EnvironmentObject var r: BatteryReader
    var body: some View {
        VStack(spacing: 16) {
            Text("Omi").font(.headline).foregroundStyle(.secondary)
            Text(r.level.map { "\($0)%" } ?? "--%").font(.system(size: 96, weight: .bold, design: .rounded))
                .foregroundStyle((r.level ?? 100) <= 20 ? .red : .primary)
            if let at = r.at { Text(at, style: .relative).font(.footnote).foregroundStyle(.secondary) + Text(" ago") .font(.footnote).foregroundStyle(.secondary) }
            Text(r.status).font(.callout).multilineTextAlignment(.center)
            Button("再読み込み / Refresh") { r.start() }.buttonStyle(.borderedProminent)
            Text(r.paired == nil ? "未登録：最初に読めたペンダントを登録します" : "登録済みのペンダントのみ読みます").font(.caption2).foregroundStyle(.secondary)
            Button("このペンダントを登録し直す / Re-register") { r.reRegister() }.font(.footnote)
        }.padding()
    }
}

/// "Omiの電池" in Shortcuts / Siri / Action button — opens the app, which reads on activation.
struct OpenBatteryIntent: AppIntent {
    static var title: LocalizedStringResource = "Omiの電池を見る"
    static var openAppWhenRun = true
    func perform() async throws -> some IntentResult { .result() }
}
struct OmiShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: OpenBatteryIntent(), phrases: ["\(.applicationName)で電池を見る", "Check Omi battery with \(.applicationName)"],
                    shortTitle: "Omi電池", systemImageName: "battery.75percent")
    }
}
