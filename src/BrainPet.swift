// BrainPet.swift — 100% Native macOS 26 SwiftUI "Liquid Glass" HUD + AppKit Ballistic Desktop Pet
// Uses Apple's official Liquid Glass APIs (developer.apple.com/documentation/technologyoverviews/liquid-glass):
//   - GlassEffectContainer, .glassEffect(.regular, in: .rect(cornerRadius: 28)),
//     .glassEffect(.regular.interactive(), in: .capsule), and .buttonStyle(.glass)
//   - 60 FPS Ballistic Throw & Elastic Wall-Bounce Physics across the Terminal window region
//   - Click-to-open Detail Page (Overview -> Associated Links -> Completion & Added Dates -> Original Raw Text)

import Cocoa
import SwiftUI
import Combine
import CoreGraphics

// MARK: - Data Models

struct TaskItem: Codable, Identifiable {
    let id: Int
    let title: String
    let description: String?
    let raw_text: String?
    let status: String?
    let due_date: String?
    let created_at: String?
    let links_list: [String]?
}

struct IdeaItem: Codable, Identifiable {
    let id: Int
    let title: String
    let summary: String?
    let raw_content: String?
    let due_date: String?
    let created_at: String?
    let links_list: [String]?
}

struct BrainStatePayload: Codable {
    let focus: String
    let tasks: [TaskItem]
    let ideas: [IdeaItem]
    let vault_path: String?
}

struct BridgeResponse: Codable {
    let status: String
    let mode: String?
    let title: String?
    let item_id: Int?
    let reply: String?
    let citations: [String]?
    let status_text: String?
    let state: BrainStatePayload?
}

// MARK: - ViewModel & Python Bridge Runner

class BrainViewModel: ObservableObject {
    @Published var focus: String = ""
    @Published var tasks: [TaskItem] = []
    @Published var ideas: [IdeaItem] = []
    @Published var selectedTab: Int = 0 // 0: Tasks, 1: Ideas, 2: Answers, 3: Detail Page
    @Published var lastListTab: Int = 0

    @Published var inputText: String = ""
    @Published var answerText: String = ""
    @Published var citationsText: String = ""
    @Published var statusText: String = ""
    @Published var isBusy: Bool = false
    @Published var isRoaming: Bool = true

    // Detail Page State
    @Published var detailKind: String = "task" // "task" or "idea"
    @Published var detailId: Int = 0
    @Published var detailTitle: String = ""
    @Published var detailDesc: String = ""
    @Published var detailRawText: String = ""
    @Published var detailDueDate: String = ""
    @Published var detailCreatedAt: String = ""
    @Published var detailStatus: String = "todo"
    @Published var detailLinks: [String] = []
    @Published var newLinkInput: String = ""

    var vaultPath: String = ""
    let projectRoot: String
    let pythonBin: String
    let bridgeScript: String

    var onRoamToggled: ((Bool) -> Void)?
    var onCloseHUD: (() -> Void)?
    var onToast: ((String) -> Void)?

    init(projectRoot: String) {
        self.projectRoot = projectRoot
        let venvPy = (projectRoot as NSString).appendingPathComponent("venv/bin/python3")
        self.pythonBin = FileManager.default.fileExists(atPath: venvPy) ? venvPy : "/usr/bin/python3"
        self.bridgeScript = (projectRoot as NSString).appendingPathComponent("src/brain_bridge.py")
        refreshState()
    }

    func runBridge(args: [String], completion: @escaping (BridgeResponse?) -> Void) {
        let py = self.pythonBin
        let script = self.bridgeScript
        let root = self.projectRoot
        DispatchQueue.global(qos: .userInitiated).async {
            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: py)
            proc.arguments = [script] + args
            proc.currentDirectoryURL = URL(fileURLWithPath: root)

            let outPipe = Pipe()
            proc.standardOutput = outPipe
            proc.standardError = Pipe()

            do {
                try proc.run()
                proc.waitUntilExit()
                let data = outPipe.fileHandleForReading.readDataToEndOfFile()
                let decoded = try? JSONDecoder().decode(BridgeResponse.self, from: data)
                DispatchQueue.main.async {
                    completion(decoded)
                }
            } catch {
                DispatchQueue.main.async {
                    completion(nil)
                }
            }
        }
    }

    func applyState(_ st: BrainStatePayload?) {
        guard let st = st else { return }
        self.focus = st.focus
        self.tasks = st.tasks
        self.ideas = st.ideas
        if let vp = st.vault_path {
            self.vaultPath = vp
        }
        // Keep Detail Page synced if open
        if selectedTab == 3 {
            if detailKind == "task", let t = tasks.first(where: { $0.id == detailId }) {
                loadTaskIntoDetail(t)
            } else if detailKind == "idea", let d = ideas.first(where: { $0.id == detailId }) {
                loadIdeaIntoDetail(d)
            }
        }
    }

    func refreshState() {
        runBridge(args: ["state"]) { [weak self] resp in
            self?.applyState(resp?.state)
        }
    }

    func submitInput() {
        let trimmed = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        inputText = ""
        isBusy = true
        statusText = "Processing…"

        runBridge(args: ["submit", trimmed]) { [weak self] resp in
            guard let self = self else { return }
            self.isBusy = false
            guard let resp = resp, resp.status == "success" else {
                self.statusText = "Could not process input"
                return
            }
            self.applyState(resp.state)
            self.statusText = resp.status_text ?? ""

            if resp.mode == "question" {
                self.answerText = resp.reply ?? ""
                if let cites = resp.citations, !cites.isEmpty {
                    self.citationsText = "Sources: " + cites.joined(separator: " • ")
                } else {
                    self.citationsText = ""
                }
                self.switchTab(2)
            } else if resp.mode == "task" {
                self.switchTab(0)
                if let t = resp.title { self.onToast?("\(String(t.prefix(15)))") }
            } else if resp.mode == "idea" {
                self.switchTab(1)
                if let t = resp.title { self.onToast?("\(String(t.prefix(15)))") }
            }
        }
    }

    func ingestDroppedItem(_ raw: String) {
        isBusy = true
        statusText = "Refining drop..."
        runBridge(args: ["submit", raw]) { [weak self] resp in
            guard let self = self else { return }
            self.isBusy = false
            guard let resp = resp, resp.status == "success" else { return }
            self.applyState(resp.state)
            self.statusText = resp.status_text ?? ""
            if resp.mode == "task" {
                self.switchTab(0)
                if let t = resp.title { self.onToast?("\(String(t.prefix(15)))") }
            } else {
                self.switchTab(1)
                if let t = resp.title { self.onToast?("\(String(t.prefix(15)))") }
            }
        }
    }

    func switchTab(_ idx: Int) {
        if idx < 3 {
            lastListTab = idx
        }
        selectedTab = idx
    }

    func openTaskDetail(_ t: TaskItem) {
        loadTaskIntoDetail(t)
        selectedTab = 3
    }

    func openIdeaDetail(_ d: IdeaItem) {
        loadIdeaIntoDetail(d)
        selectedTab = 3
    }

    private func loadTaskIntoDetail(_ t: TaskItem) {
        detailKind = "task"
        detailId = t.id
        detailTitle = t.title
        detailDesc = (t.description?.isEmpty == false) ? t.description! : t.title
        detailRawText = t.raw_text ?? t.title
        detailDueDate = t.due_date ?? ""
        detailCreatedAt = t.created_at ?? "-"
        detailStatus = t.status ?? "todo"
        detailLinks = t.links_list ?? []
    }

    private func loadIdeaIntoDetail(_ d: IdeaItem) {
        detailKind = "idea"
        detailId = d.id
        detailTitle = d.title
        detailDesc = (d.summary?.isEmpty == false) ? d.summary! : d.title
        detailRawText = d.raw_content ?? (d.summary ?? d.title)
        detailDueDate = d.due_date ?? ""
        detailCreatedAt = d.created_at ?? "-"
        detailStatus = "idea"
        detailLinks = d.links_list ?? []
    }

    func toggleTask(_ id: Int) {
        runBridge(args: ["toggle_task", String(id)]) { [weak self] resp in
            self?.applyState(resp?.state)
            self?.onToast?("Completed")
        }
    }

    func deleteTask(_ id: Int) {
        runBridge(args: ["delete_task", String(id)]) { [weak self] resp in
            self?.applyState(resp?.state)
        }
    }

    func deleteIdea(_ id: Int) {
        runBridge(args: ["delete_idea", String(id)]) { [weak self] resp in
            self?.applyState(resp?.state)
        }
    }

    func clearCompleted() {
        runBridge(args: ["clear_done"]) { [weak self] resp in
            self?.applyState(resp?.state)
        }
    }

    func clearFocus() {
        runBridge(args: ["clear_focus"]) { [weak self] resp in
            self?.applyState(resp?.state)
        }
    }

    func addLinkToCurrentDetail() {
        let u = newLinkInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !u.isEmpty, detailId > 0 else { return }
        newLinkInput = ""
        runBridge(args: ["add_link", detailKind, String(detailId), u]) { [weak self] resp in
            self?.applyState(resp?.state)
        }
    }

    func removeLinkFromCurrentDetail(_ url: String) {
        guard detailId > 0 else { return }
        runBridge(args: ["remove_link", detailKind, String(detailId), url]) { [weak self] resp in
            self?.applyState(resp?.state)
        }
    }

    func saveDetailDueDate() {
        guard detailId > 0 else { return }
        let d = detailDueDate.trimmingCharacters(in: .whitespacesAndNewlines)
        runBridge(args: ["set_due", detailKind, String(detailId), d]) { [weak self] resp in
            self?.applyState(resp?.state)
        }
    }

    func toggleRoam() {
        isRoaming.toggle()
        onRoamToggled?(isRoaming)
    }
}

// MARK: - Native macOS 26 SwiftUI Liquid Glass Views

@available(macOS 26.0, *)
struct SummaryCardView: View {
    let badge: String
    let title: String
    let subtitle: String
    let dueDate: String?
    let linkCount: Int
    let isTask: Bool
    let isDone: Bool
    let onTapCard: () -> Void
    let onToggleCheck: (() -> Void)?
    let onDelete: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .center, spacing: 8) {
                if isTask, let toggle = onToggleCheck {
                    Button(action: toggle) {
                        Image(systemName: isDone ? "checkmark.circle.fill" : "circle")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(.primary)
                    }
                    .buttonStyle(.plain)
                }

                Text(badge)
                    .font(.system(size: 9.5, weight: .bold))
                    .tracking(0.5)
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .glassEffect(.regular, in: .capsule)

                Text(title)
                    .font(.system(size: 13.5, weight: .semibold))
                    .foregroundStyle(.primary)
                    .lineLimit(2)

                Spacer()

                Button(action: onDelete) {
                    Image(systemName: "xmark")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(.secondary)
                        .frame(width: 22, height: 22)
                }
                .buttonStyle(.glass)
            }

            if !subtitle.isEmpty && subtitle.lowercased() != title.lowercased() {
                Text(subtitle)
                    .font(.system(size: 12, weight: .regular))
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 7)
                    .background(Color.black.opacity(0.16), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            }

            HStack(spacing: 10) {
                if let due = dueDate, !due.isEmpty {
                    Label("Complete by \(due)", systemImage: "calendar")
                        .font(.system(size: 10.5, weight: .medium))
                        .foregroundStyle(.secondary)
                }
                if linkCount > 0 {
                    Label("\(linkCount) link\(linkCount > 1 ? "s" : "")", systemImage: "link")
                        .font(.system(size: 10.5, weight: .medium))
                        .foregroundStyle(.secondary)
                }
                Spacer()
                HStack(spacing: 3) {
                    Text("Details")
                    Image(systemName: "chevron.right")
                }
                .font(.system(size: 10.5, weight: .medium))
                .foregroundStyle(.tertiary)
            }
        }
        .padding(13)
        .glassEffect(.regular.interactive(), in: .rect(cornerRadius: 18))
        .contentShape(Rectangle())
        .onTapGesture {
            onTapCard()
        }
    }
}

@available(macOS 26.0, *)
struct DetailPageView: View {
    @ObservedObject var vm: BrainViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Top Detail Navigation Bar
            HStack(spacing: 8) {
                Button {
                    vm.switchTab(vm.lastListTab)
                } label: {
                    Label("Back", systemImage: "chevron.left")
                        .font(.system(size: 11.5, weight: .semibold))
                }
                .buttonStyle(.glass)

                Text(vm.detailKind == "task" ? "TASK DETAILS" : "IDEA DETAILS")
                    .font(.system(size: 10, weight: .bold))
                    .tracking(0.6)
                    .foregroundStyle(.secondary)

                Spacer()

                if vm.detailKind == "task" {
                    Button {
                        vm.toggleTask(vm.detailId)
                    } label: {
                        Label(
                            vm.detailStatus == "done" ? "Completed" : "Mark Complete",
                            systemImage: vm.detailStatus == "done" ? "checkmark.circle.fill" : "circle"
                        )
                        .font(.system(size: 11, weight: .semibold))
                    }
                    .buttonStyle(.glass)
                }
            }

            ScrollView(.vertical, showsIndicators: false) {
                VStack(alignment: .leading, spacing: 10) {
                    // 1. Detailed Task / Idea Overview
                    VStack(alignment: .leading, spacing: 6) {
                        Text(vm.detailTitle)
                            .font(.system(size: 15, weight: .bold))
                            .foregroundStyle(.primary)
                        Text(vm.detailDesc)
                            .font(.system(size: 12.5, weight: .regular))
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(13)
                    .glassEffect(.regular, in: .rect(cornerRadius: 16))

                    // 2. Associated Links
                    VStack(alignment: .leading, spacing: 8) {
                        Text("ASSOCIATED LINKS")
                            .font(.system(size: 9.5, weight: .bold))
                            .tracking(0.6)
                            .foregroundStyle(.secondary)

                        if vm.detailLinks.isEmpty {
                            Text("No associated links yet.")
                                .font(.system(size: 11.5))
                                .foregroundStyle(.tertiary)
                        } else {
                            ForEach(vm.detailLinks, id: \.self) { link in
                                HStack(spacing: 6) {
                                    Button {
                                        if let u = URL(string: link) {
                                            NSWorkspace.shared.open(u)
                                        }
                                    } label: {
                                        HStack(spacing: 5) {
                                            Image(systemName: "link")
                                            Text(URL(string: link)?.host ?? link)
                                                .lineLimit(1)
                                            Spacer()
                                            Image(systemName: "arrow.up.right")
                                        }
                                        .font(.system(size: 11.5, weight: .medium))
                                    }
                                    .buttonStyle(.glass)

                                    Button {
                                        vm.removeLinkFromCurrentDetail(link)
                                    } label: {
                                        Image(systemName: "xmark")
                                            .font(.system(size: 10, weight: .bold))
                                    }
                                    .buttonStyle(.glass)
                                }
                            }
                        }

                        // Inline Add Link Capsule
                        HStack(spacing: 8) {
                            Image(systemName: "plus.circle")
                                .foregroundStyle(.secondary)
                            TextField("", text: $vm.newLinkInput)
                                .textFieldStyle(.plain)
                                .font(.system(size: 12))
                                .onSubmit {
                                    vm.addLinkToCurrentDetail()
                                }
                            Button("Add Link") {
                                vm.addLinkToCurrentDetail()
                            }
                            .font(.system(size: 11, weight: .semibold))
                            .buttonStyle(.glass)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .glassEffect(.regular.interactive(), in: .capsule)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(13)
                    .glassEffect(.regular, in: .rect(cornerRadius: 16))

                    // 3. Schedule & Timestamps (To Be Completed By + Date Added)
                    VStack(alignment: .leading, spacing: 8) {
                        Text("SCHEDULE & TIMESTAMPS")
                            .font(.system(size: 9.5, weight: .bold))
                            .tracking(0.6)
                            .foregroundStyle(.secondary)

                        HStack {
                            Label("To Be Completed By", systemImage: "calendar.badge.clock")
                                .font(.system(size: 12, weight: .medium))
                            Spacer()
                            TextField("YYYY-MM-DD", text: $vm.detailDueDate)
                                .textFieldStyle(.plain)
                                .font(.system(size: 11.5, weight: .semibold))
                                .multilineTextAlignment(.center)
                                .frame(width: 110)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .glassEffect(.regular.interactive(), in: .capsule)
                                .onSubmit {
                                    vm.saveDetailDueDate()
                                }
                        }

                        Label("Date Added: \(vm.detailCreatedAt)", systemImage: "clock")
                            .font(.system(size: 11.5))
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(13)
                    .glassEffect(.regular, in: .rect(cornerRadius: 16))

                    // 4. Original Raw Text Kept at Last for Future Reference
                    VStack(alignment: .leading, spacing: 5) {
                        Text("ORIGINAL RAW TEXT (REFERENCE)")
                            .font(.system(size: 9.5, weight: .bold))
                            .tracking(0.6)
                            .foregroundStyle(.tertiary)
                        Text("\"\(vm.detailRawText)\"")
                            .font(.system(size: 11.5, weight: .regular))
                            .italic()
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(13)
                    .glassEffect(.regular, in: .rect(cornerRadius: 16))
                }
                .padding(.vertical, 2)
            }
            .frame(height: 290)
        }
    }
}

@available(macOS 26.0, *)
struct BrainHUDView: View {
    @ObservedObject var vm: BrainViewModel

    var body: some View {
        GlassEffectContainer(spacing: 12) {
            VStack(spacing: 12) {
                // ─── TOP BAR: Brand | Top-Middle [Focus Pill] + [Move / Rest Pill] | Circular Close ───
                HStack(spacing: 8) {
                    Text("Brain")
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(.primary)

                    Spacer()

                    // Top-Middle Focus Pill
                    HStack(spacing: 5) {
                        Image(systemName: "scope")
                            .font(.system(size: 11, weight: .semibold))
                        Text(vm.focus.isEmpty ? "Focus: Off" : "Focus: \(String(vm.focus.prefix(14)))")
                            .font(.system(size: 11.5, weight: .semibold))
                        if !vm.focus.isEmpty {
                            Button {
                                vm.clearFocus()
                            } label: {
                                Image(systemName: "xmark.circle.fill")
                                    .font(.system(size: 11))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 11)
                    .padding(.vertical, 5)
                    .glassEffect(.regular.interactive(), in: .capsule)

                    // Top-Middle Move / Rest Toggle Button right beside Focus
                    Button {
                        vm.toggleRoam()
                    } label: {
                        HStack(spacing: 5) {
                            Circle()
                                .fill(vm.isRoaming ? Color.primary : Color.secondary)
                                .frame(width: 6, height: 6)
                            Text(vm.isRoaming ? "Moving" : "Resting")
                                .font(.system(size: 11.5, weight: .semibold))
                        }
                    }
                    .buttonStyle(.glass)

                    Spacer()

                    // Circular Liquid Glass Close Button
                    Button {
                        vm.onCloseHUD?()
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 11, weight: .bold))
                            .frame(width: 24, height: 24)
                    }
                    .buttonStyle(.glass)
                }

                // ─── SEGMENTED LIQUID GLASS PILL BAR ([ Tasks ] [ Ideas ] [ Answers ]) ───
                if vm.selectedTab < 3 {
                    HStack(spacing: 6) {
                        ForEach(0..<3, id: \.self) { idx in
                            let label = idx == 0 ? "Tasks (\(vm.tasks.count))" : (idx == 1 ? "Ideas (\(vm.ideas.count))" : "Answers")
                            Button {
                                vm.switchTab(idx)
                            } label: {
                                Text(label)
                                    .font(.system(size: 12, weight: vm.selectedTab == idx ? .bold : .medium))
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 5)
                            }
                            .buttonStyle(.glass)
                        }
                    }
                }

                // ─── MAIN CONTENT AREA ───
                if vm.selectedTab == 0 {
                    // TASKS LIST
                    VStack(spacing: 6) {
                        HStack {
                            Text("\(vm.tasks.count) pending")
                                .font(.system(size: 11, weight: .medium))
                                .foregroundStyle(.secondary)
                            Spacer()
                            Button("Clear Completed") {
                                vm.clearCompleted()
                            }
                            .font(.system(size: 11, weight: .medium))
                            .buttonStyle(.plain)
                            .foregroundStyle(.secondary)
                        }
                        .padding(.horizontal, 4)

                        ScrollView(.vertical, showsIndicators: false) {
                            if vm.tasks.isEmpty {
                                Text("No pending tasks")
                                    .font(.system(size: 13, weight: .medium))
                                    .foregroundStyle(.secondary)
                                    .frame(maxWidth: .infinity, minHeight: 220)
                            } else {
                                VStack(spacing: 9) {
                                    ForEach(vm.tasks) { task in
                                        SummaryCardView(
                                            badge: "TASK",
                                            title: task.title,
                                            subtitle: task.description ?? "",
                                            dueDate: task.due_date,
                                            linkCount: task.links_list?.count ?? 0,
                                            isTask: true,
                                            isDone: task.status == "done",
                                            onTapCard: { vm.openTaskDetail(task) },
                                            onToggleCheck: { vm.toggleTask(task.id) },
                                            onDelete: { vm.deleteTask(task.id) }
                                        )
                                    }
                                }
                                .padding(.vertical, 2)
                            }
                        }
                        .frame(height: 265)
                    }
                } else if vm.selectedTab == 1 {
                    // IDEAS LIST
                    ScrollView(.vertical, showsIndicators: false) {
                        if vm.ideas.isEmpty {
                            Text("No Idea Boxes yet")
                                .font(.system(size: 13, weight: .medium))
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, minHeight: 240)
                        } else {
                            VStack(spacing: 9) {
                                ForEach(vm.ideas) { idea in
                                    SummaryCardView(
                                        badge: "IDEA",
                                        title: idea.title,
                                        subtitle: idea.summary ?? "",
                                        dueDate: idea.due_date,
                                        linkCount: idea.links_list?.count ?? 0,
                                        isTask: false,
                                        isDone: false,
                                        onTapCard: { vm.openIdeaDetail(idea) },
                                        onToggleCheck: nil,
                                        onDelete: { vm.deleteIdea(idea.id) }
                                    )
                                }
                            }
                            .padding(.vertical, 2)
                        }
                    }
                    .frame(height: 288)
                } else if vm.selectedTab == 2 {
                    // DIRECT ANSWERS VIEW
                    VStack(alignment: .leading, spacing: 8) {
                        ScrollView(.vertical, showsIndicators: false) {
                            Text(vm.answerText.isEmpty ? "Ask any question below for a direct answer." : vm.answerText)
                                .font(.system(size: 13, weight: .regular))
                                .foregroundStyle(.primary)
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(14)
                        }
                        .frame(height: 255)
                        .glassEffect(.regular, in: .rect(cornerRadius: 18))

                        if !vm.citationsText.isEmpty {
                            Text(vm.citationsText)
                                .font(.system(size: 10.5, weight: .medium))
                                .foregroundStyle(.secondary)
                                .lineLimit(2)
                        }
                    }
                } else {
                    // DETAIL PAGE VIEW
                    DetailPageView(vm: vm)
                }

                // --- BOTTOM APPLE LIQUID GLASS CAPSULE INPUT BAR ---
                HStack(spacing: 10) {
                    TextField("", text: $vm.inputText)
                        .textFieldStyle(.plain)
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(.primary)
                        .onSubmit {
                            vm.submitInput()
                        }

                    Button {
                        vm.submitInput()
                    } label: {
                        Image(systemName: "arrow.up")
                            .font(.system(size: 12, weight: .bold))
                            .frame(width: 26, height: 26)
                    }
                    .buttonStyle(.glass)
                }
                .padding(.leading, 16)
                .padding(.trailing, 6)
                .padding(.vertical, 6)
                .glassEffect(.regular.interactive(), in: .capsule)

                if !vm.statusText.isEmpty {
                    Text(vm.statusText)
                        .font(.system(size: 10.5, weight: .medium))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 4)
                }
            }
            .padding(18)
            .glassEffect(.regular, in: .rect(cornerRadius: 30))
        }
        .frame(width: 420)
    }
}

// MARK: - Floating Liquid Glass HUD NSPanel

class HUDPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }

    init(contentRect: NSRect) {
        super.init(
            contentRect: contentRect,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        self.isFloatingPanel = true
        self.level = .statusBar
        self.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        self.isOpaque = false
        self.backgroundColor = .clear
        self.hasShadow = true
        self.hidesOnDeactivate = false
    }
}

// MARK: - Pixel-Art Pet View & 60 FPS Ballistic Throw Window

class PetSpriteView: NSView {
    var currentImage: NSImage?
    var facingRight: Bool = false
    var toastText: String = ""

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        self.wantsLayer = true
        self.layer?.backgroundColor = NSColor.clear.cgColor
        self.registerForDraggedTypes([.fileURL, .URL, .string])
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    var onDropItem: ((String) -> Void)?
    var onDragHover: ((Bool) -> Void)?

    override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
        onDragHover?(true)
        return .copy
    }

    override func draggingExited(_ sender: NSDraggingInfo?) {
        onDragHover?(false)
    }

    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        onDragHover?(false)
        let pb = sender.draggingPasteboard
        if let urls = pb.readObjects(forClasses: [NSURL.self], options: nil) as? [URL], let first = urls.first {
            onDropItem?(first.isFileURL ? first.path : first.absoluteString)
            return true
        }
        if let str = pb.string(forType: .string), !str.isEmpty {
            onDropItem?(str)
            return true
        }
        return false
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        guard let ctx = NSGraphicsContext.current else { return }

        // 1. Subtle Ground Shadow Oval
        NSColor(calibratedWhite: 0.0, alpha: 0.32).setFill()
        let shadowRect = NSRect(x: (bounds.width - 76) / 2, y: 8, width: 76, height: 10)
        NSBezierPath(ovalIn: shadowRect).fill()

        // 2. Razor-Sharp Nearest-Neighbor 2D Pixel-Art Sprite
        if let img = currentImage {
            ctx.imageInterpolation = .none
            ctx.saveGraphicsState()
            let drawW: CGFloat = 128
            let drawH: CGFloat = 128
            let dx = (bounds.width - drawW) / 2
            let dy: CGFloat = 14

            if !facingRight {
                let xform = NSAffineTransform()
                xform.translateX(by: dx + drawW, yBy: dy)
                xform.scaleX(by: -1.0, yBy: 1.0)
                xform.concat()
                img.draw(in: NSRect(x: 0, y: 0, width: drawW, height: drawH))
            } else {
                img.draw(in: NSRect(x: dx, y: dy, width: drawW, height: drawH))
            }
            ctx.restoreGraphicsState()
        }
    }
}

// MARK: - App Controller (60 FPS Ballistic Throw Physics & Terminal Window Bounds)

@available(macOS 26.0, *)
class AppDelegate: NSObject, NSApplicationDelegate {
    var petWindow: NSPanel!
    var petView: PetSpriteView!
    var hudPanel: HUDPanel!
    var vm: BrainViewModel!

    var framesIdle: [NSImage] = []
    var framesWalk: [NSImage] = []
    var framesEat: [NSImage] = []
    var framesThink: [NSImage] = []

    var state: String = "idle" // "idle", "wander", "thrown", "eating", "thinking"
    var frameIdx: Int = 0
    var facingRight: Bool = false

    // Ballistic Throw & Roam Physics
    var posX: CGFloat = 600
    var posY: CGFloat = 200
    var throwVX: CGFloat = 0
    var throwVY: CGFloat = 0
    var dragSamples: [(TimeInterval, NSPoint)] = []
    var isDragging: Bool = false
    var dragOffset: NSPoint = .zero
    var dragStartScreen: NSPoint = .zero

    var roamTarget: NSPoint? = nil
    var pauseTicks: Int = 18
    var tickCounter: Int = 0
    var physicsTimer: Timer?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)

        let root = FileManager.default.currentDirectoryPath
        vm = BrainViewModel(projectRoot: root)

        loadSprites(root: root)
        setupPetWindow()
        setupHUDPanel()

        vm.onRoamToggled = { [weak self] roaming in
            guard let self = self else { return }
            if !roaming {
                self.state = "idle"
                self.roamTarget = nil
            } else {
                self.pauseTicks = 5
            }
        }
        vm.onCloseHUD = { [weak self] in
            self?.hudPanel.orderOut(nil)
        }
        vm.onToast = { [weak self] _ in
            self?.positionHUDAbovePet()
        }

        // 60 FPS unified physics & sprite timer (16.6ms)
        physicsTimer = Timer.scheduledTimer(withTimeInterval: 0.016, repeats: true) { [weak self] _ in
            self?.onTick()
        }
    }

    func loadSprites(root: String) {
        let crouchDir = (root as NSString).appendingPathComponent("assets/greninja_crouch")
        func loadRow(_ r: Int) -> [NSImage] {
            var arr: [NSImage] = []
            for c in 0..<8 {
                let p = (crouchDir as NSString).appendingPathComponent("frame_\(r)_\(c).png")
                if let img = NSImage(contentsOfFile: p) {
                    arr.append(img)
                }
            }
            return arr
        }
        framesIdle = loadRow(0)
        framesWalk = loadRow(1)
        framesEat = loadRow(2)
        framesThink = loadRow(3)
    }

    /// Queries macOS WindowServer for the active Terminal window bounds (converted to Cocoa bottom-left screen coords).
    func getTerminalMovementBounds() -> NSRect {
        let screenFrame = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 40, width: 1440, height: 860)
        let fullScreenHeight = NSScreen.main?.frame.height ?? 900

        let opts: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
        if let infoList = CGWindowListCopyWindowInfo(opts, kCGNullWindowID) as? [[String: Any]] {
            for entry in infoList {
                if let owner = entry[kCGWindowOwnerName as String] as? String,
                   ["Terminal", "iTerm2", "Warp"].contains(owner),
                   let b = entry[kCGWindowBounds as String] as? [String: CGFloat],
                   let w = b["Width"], let h = b["Height"], w >= 420, h >= 280,
                   let cgX = b["X"], let cgY = b["Y"] {
                    // Convert CoreGraphics top-left Y to Cocoa bottom-left Y
                    let cocoaY = fullScreenHeight - (cgY + h)
                    return NSRect(x: cgX, y: cocoaY, width: w, height: h)
                }
            }
        }
        return screenFrame
    }

    func setupPetWindow() {
        let bounds = getTerminalMovementBounds()
        let w: CGFloat = 156
        let h: CGFloat = 156
        posX = max(bounds.minX + 40, bounds.maxX - w - 230)
        posY = max(bounds.minY + 30, bounds.minY + 40)

        petWindow = NSPanel(
            contentRect: NSRect(x: posX, y: posY, width: w, height: h),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        petWindow.isFloatingPanel = true
        petWindow.level = .statusBar
        petWindow.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        petWindow.isOpaque = false
        petWindow.backgroundColor = .clear
        petWindow.hasShadow = false
        petWindow.hidesOnDeactivate = false

        petView = PetSpriteView(frame: NSRect(x: 0, y: 0, width: w, height: h))
        petView.currentImage = framesIdle.first
        petView.onDragHover = { [weak self] hovering in
            self?.state = hovering ? "eating" : "idle"
        }
        petView.onDropItem = { [weak self] dropped in
            guard let self = self else { return }
            self.state = "thinking"
            self.vm.ingestDroppedItem(dropped)
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                self.state = "idle"
                self.showHUD()
            }
        }

        petWindow.contentView = petView
        petWindow.orderFrontRegardless()

        // Mouse Tracking for Click vs Drag vs Ballistic Flick/Throw
        NSEvent.addLocalMonitorForEvents(matching: [.leftMouseDown, .leftMouseDragged, .leftMouseUp, .rightMouseDown]) { [weak self] event in
            guard let self = self else { return event }
            if event.window == self.petWindow {
                self.handlePetMouseEvent(event)
                return nil
            }
            return event
        }
    }

    func setupHUDPanel() {
        hudPanel = HUDPanel(contentRect: NSRect(x: 0, y: 0, width: 420, height: 470))
        let hosting = NSHostingView(rootView: BrainHUDView(vm: vm))
        hosting.frame = hudPanel.contentView!.bounds
        hosting.autoresizingMask = [.width, .height]
        hudPanel.contentView = hosting
    }

    func handlePetMouseEvent(_ event: NSEvent) {
        let mouseScreen = NSEvent.mouseLocation
        switch event.type {
        case .leftMouseDown:
            throwVX = 0
            throwVY = 0
            if state == "thrown" { state = "idle" }
            isDragging = false
            dragStartScreen = mouseScreen
            dragOffset = NSPoint(x: mouseScreen.x - petWindow.frame.origin.x, y: mouseScreen.y - petWindow.frame.origin.y)
            dragSamples.removeAll()
            dragSamples.append((ProcessInfo.processInfo.systemUptime, mouseScreen))

        case .leftMouseDragged:
            let dist = hypot(mouseScreen.x - dragStartScreen.x, mouseScreen.y - dragStartScreen.y)
            if dist > 4 {
                isDragging = true
                let bounds = getTerminalMovementBounds()
                let w = petWindow.frame.width
                let h = petWindow.frame.height
                let nx = max(bounds.minX + 4, min(bounds.maxX - w - 4, mouseScreen.x - dragOffset.x))
                let ny = max(bounds.minY + 4, min(bounds.maxY - h - 4, mouseScreen.y - dragOffset.y))

                if nx > posX { facingRight = true }
                else if nx < posX { facingRight = false }

                posX = nx
                posY = ny
                petWindow.setFrameOrigin(NSPoint(x: posX, y: posY))
                if hudPanel.isVisible {
                    positionHUDAbovePet()
                }

                let now = ProcessInfo.processInfo.systemUptime
                dragSamples.append((now, mouseScreen))
                if dragSamples.count > 6 {
                    dragSamples.removeFirst()
                }
            }

        case .leftMouseUp:
            if !isDragging {
                toggleHUD()
            } else {
                isDragging = false
                let now = ProcessInfo.processInfo.systemUptime
                dragSamples.append((now, mouseScreen))
                if dragSamples.count >= 2 {
                    let first = dragSamples.first!
                    let last = dragSamples.last!
                    let dt = max(0.008, last.0 - first.0)
                    if dt < 0.35 {
                        let vxSec = (last.1.x - first.1.x) / CGFloat(dt)
                        let vySec = (last.1.y - first.1.y) / CGFloat(dt)
                        // Convert px/sec to px per 16ms frame with a punchy 1.55x throw multiplier
                        var vxFrame = (vxSec * 0.016) * 1.55
                        var vyFrame = (vySec * 0.016) * 1.55
                        let speed = hypot(vxFrame, vyFrame)
                        if speed > 3.0 {
                            let maxSpeed: CGFloat = 68.0
                            if speed > maxSpeed {
                                vxFrame = (vxFrame / speed) * maxSpeed
                                vyFrame = (vyFrame / speed) * maxSpeed
                            }
                            throwVX = vxFrame
                            throwVY = vyFrame
                            state = "thrown"
                            return
                        }
                    }
                }
                pauseTicks = 30
            }

        case .rightMouseDown:
            let menu = NSMenu()
            menu.addItem(withTitle: "Open Brain", action: #selector(toggleHUD), keyEquivalent: "")
            menu.addItem(withTitle: vm.isRoaming ? "Rest in Place" : "Allow Pet to Move", action: #selector(toggleRoamMenu), keyEquivalent: "")
            menu.addItem(NSMenuItem.separator())
            menu.addItem(withTitle: "Quit", action: #selector(quitApp), keyEquivalent: "q")
            NSMenu.popUpContextMenu(menu, with: event, for: petView)

        default:
            break
        }
    }

    @objc func toggleRoamMenu() {
        vm.toggleRoam()
    }

    @objc func quitApp() {
        NSApp.terminate(nil)
    }

    @objc func toggleHUD() {
        if hudPanel.isVisible {
            hudPanel.orderOut(nil)
        } else {
            showHUD()
        }
    }

    func showHUD() {
        vm.refreshState()
        positionHUDAbovePet()
        hudPanel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func positionHUDAbovePet() {
        let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 40, width: 1440, height: 860)
        let hudW: CGFloat = 420
        let hudH: CGFloat = 470
        let petFrame = petWindow.frame

        var x = petFrame.midX - (hudW / 2)
        var y = petFrame.maxY + 10

        x = max(screen.minX + 18, min(screen.maxX - hudW - 18, x))
        if y + hudH > screen.maxY - 14 {
            y = max(screen.minY + 18, petFrame.minY - hudH - 10)
        }
        hudPanel.setFrame(NSRect(x: x, y: y, width: hudW, height: hudH), display: true)
    }

    func pickNextRoamTarget() {
        let b = getTerminalMovementBounds()
        let w = petWindow.frame.width
        let h = petWindow.frame.height
        let minX = b.minX + 12
        let maxX = max(minX + 20, b.maxX - w - 12)
        let minY = b.minY + 12
        let maxY = max(minY + 20, b.maxY - h - 12)

        let angle = CGFloat.random(in: 0..<(2 * .pi))
        let dist = CGFloat.random(in: 140...380)
        let tx = max(minX, min(maxX, posX + cos(angle) * dist))
        let ty = max(minY, min(maxY, posY + sin(angle) * dist * 0.75))
        roamTarget = NSPoint(x: tx, y: ty)
        facingRight = (tx >= posX)
    }

    func onTick() {
        tickCounter += 1

        // 1. 60 FPS Ballistic Throw & Elastic Wall Bounce across Terminal Region
        if state == "thrown" {
            let b = getTerminalMovementBounds()
            let w = petWindow.frame.width
            let h = petWindow.frame.height
            let minX = b.minX + 4
            let maxX = max(minX + 10, b.maxX - w - 4)
            let minY = b.minY + 4
            let maxY = max(minY + 10, b.maxY - h - 4)

            posX += throwVX
            posY += throwVY

            if posX <= minX {
                posX = minX
                throwVX = -throwVX * 0.76
                facingRight = true
            } else if posX >= maxX {
                posX = maxX
                throwVX = -throwVX * 0.76
                facingRight = false
            }

            if posY <= minY {
                posY = minY
                throwVY = -throwVY * 0.76
            } else if posY >= maxY {
                posY = maxY
                throwVY = -throwVY * 0.76
            }

            facingRight = (throwVX >= 0)
            petWindow.setFrameOrigin(NSPoint(x: posX, y: posY))
            if hudPanel.isVisible {
                positionHUDAbovePet()
            }

            throwVX *= 0.95
            throwVY *= 0.95

            if hypot(throwVX, throwVY) < 0.65 {
                throwVX = 0
                throwVY = 0
                state = "idle"
                pauseTicks = 30
            }
        }
        // 2. Natural Autonomous Roaming across Terminal Region (every 3rd tick ~ 20 FPS movement)
        else if tickCounter % 3 == 0 {
            let activelyUsing = isDragging || hudPanel.isVisible || state == "eating" || state == "thinking"
            if !vm.isRoaming || activelyUsing {
                if state == "wander" { state = "idle" }
            } else {
                if pauseTicks > 0 {
                    state = "idle"
                    pauseTicks -= 1
                    if pauseTicks == 0 {
                        pickNextRoamTarget()
                        state = "wander"
                    }
                } else {
                    if roamTarget == nil { pickNextRoamTarget() }
                    if let target = roamTarget {
                        let dx = target.x - posX
                        let dy = target.y - posY
                        let dist = hypot(dx, dy)
                        let step: CGFloat = 2.8
                        if dist <= step + 1.0 {
                            posX = target.x
                            posY = target.y
                            petWindow.setFrameOrigin(NSPoint(x: posX, y: posY))
                            roamTarget = nil
                            state = "idle"
                            pauseTicks = Int.random(in: 35...80)
                        } else {
                            posX += (dx / dist) * step
                            posY += (dy / dist) * step
                            facingRight = (dx >= 0)
                            state = "wander"
                            petWindow.setFrameOrigin(NSPoint(x: posX, y: posY))
                        }
                    }
                }
            }
        }

        // 3. Sprite Frame Advance (every 6th tick ~ 10 FPS crisp pixel timing)
        if tickCounter % 6 == 0 {
            frameIdx += 1
            let bank: [NSImage]
            switch state {
            case "wander", "thrown": bank = framesWalk
            case "eating": bank = framesEat
            case "thinking": bank = framesThink
            default: bank = framesIdle
            }
            if !bank.isEmpty {
                petView.currentImage = bank[frameIdx % bank.count]
                petView.facingRight = facingRight
                petView.needsDisplay = true
            }
        }
    }
}

// MARK: - Main Entry Point

if #available(macOS 26.0, *) {
    let app = NSApplication.shared
    let delegate = AppDelegate()
    app.delegate = delegate
    app.run()
}
