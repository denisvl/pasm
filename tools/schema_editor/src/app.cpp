#include "app.h"
#include "schema_registry.h"
#include "schema_parser.h"
#include "yaml_loader.h"
#include "file_browser.h"
#include "form_renderer.h"
#include "c_code_editor.h"

#include <imgui.h>
#include <fstream>
#include <sstream>
#include <nlohmann/json.hpp>

namespace fs = std::filesystem;
using json = nlohmann::json;

static const char* kConfigFile = "pasm_schema_editor.json";

static void syncRawFromDataImpl(Document& doc) {
    YAML::Emitter emitter;
    emitter.SetIndent(2);
    emitter.SetMapFormat(YAML::Block);
    emitter.SetSeqFormat(YAML::Block);
    emitter.SetBoolFormat(YAML::TrueFalseBool);
    emitter << doc.yamlDoc->root();
    doc.rawText = emitter.c_str();
}

static std::string formatFileSize(uintmax_t bytes) {
    if (bytes < 1024) return std::to_string(bytes) + " B";
    if (bytes < 1024 * 1024) return std::to_string(bytes / 1024) + " KB";
    return std::to_string(bytes / (1024 * 1024)) + " MB";
}

App::App()
    : m_schemaRegistry(std::make_unique<SchemaRegistry>())
    , m_fileBrowser(std::make_unique<FileBrowser>())
    , m_schemaParser(std::make_unique<SchemaParser>())
    , m_formRenderer(std::make_unique<FormRenderer>()) {}

App::~App() = default;

Document* App::activeDoc() {
    return &m_documents[m_activeDoc];
}

Document* App::activeDocOrNull() {
    if (m_activeDoc < 0 || m_activeDoc >= (int)m_documents.size())
        return nullptr;
    return &m_documents[m_activeDoc];
}

std::string App::findProjectRoot() const {
    fs::path cwd = fs::current_path();
    if (fs::exists(cwd / "schemas"))
        return cwd.string();
    fs::path parent = cwd;
    while (parent.has_parent_path()) {
        parent = parent.parent_path();
        if (fs::exists(parent / "schemas"))
            return parent.string();
    }
    return cwd.string();
}

bool App::initialize() {
    m_projectRoot = findProjectRoot();
    m_schemasDir = m_projectRoot + "/schemas";
    m_examplesDir = m_projectRoot + "/examples";

    if (!m_schemaRegistry->initialize(m_schemasDir, m_examplesDir)) {
        m_statusMessage = "Failed: schemas/ or examples/ not found from " + m_projectRoot;
        return false;
    }

    m_fileBrowser->initialize(m_schemaRegistry.get());

    loadConfig();

    auto& unmatched = m_schemaRegistry->unmatchedFiles();
    if (unmatched.empty()) {
        m_statusMessage = "Ready";
    } else {
        m_statusMessage = "Ready — " + std::to_string(unmatched.size()) + " unmatched files";
    }

    return true;
}

void App::loadConfig() {
    std::ifstream fin(kConfigFile);
    if (!fin.is_open()) return;
    try {
        json cfg;
        fin >> cfg;
        if (cfg.contains("dark_theme")) {
            m_darkTheme = cfg["dark_theme"].get<bool>();
            if (m_darkTheme)
                ImGui::StyleColorsDark();
            else
                ImGui::StyleColorsLight();
        }
        if (cfg.contains("last_file")) {
            std::string lastFile = cfg["last_file"];
            if (fs::exists(lastFile))
                openFile(lastFile);
        }
        if (cfg.contains("open_dirs")) {
            std::vector<std::string> dirs = cfg["open_dirs"].get<std::vector<std::string>>();
            m_fileBrowser->setOpenDirs(dirs);
        }
        if (cfg.contains("panel_width"))
            m_filePanelWidth = cfg["panel_width"].get<float>();
    } catch (...) {}
}

void App::saveConfig() {
    try {
        json cfg;
        cfg["dark_theme"] = m_darkTheme;
        Document* doc = activeDocOrNull();
        if (doc && doc->isOpen())
            cfg["last_file"] = doc->path();
        cfg["open_dirs"] = m_fileBrowser->getOpenDirs();
        cfg["panel_width"] = m_filePanelWidth;
        std::ofstream fout(kConfigFile);
        fout << cfg.dump(2);
    } catch (...) {}
}

void App::render() {
    handleShortcuts();

    renderMenuBar();

    if (m_showDemoWindow)
        ImGui::ShowDemoWindow(&m_showDemoWindow);

    if (m_showAbout) {
        ImGui::OpenPopup("About Schema Editor");
        m_showAbout = false;
    }
    if (ImGui::BeginPopupModal("About Schema Editor", nullptr, ImGuiWindowFlags_AlwaysAutoResize)) {
        ImGui::Text("PASM Schema Editor v0.1");
        ImGui::Separator();
        ImGui::Text("A schema-driven YAML editor for PASM definitions.");
        ImGui::Text("Project root: %s", m_projectRoot.c_str());
        if (ImGui::Button("Close"))
            ImGui::CloseCurrentPopup();
        ImGui::EndPopup();
    }

    if (m_showUnmatched) {
        ImGui::Begin("Unmatched Files", &m_showUnmatched, ImGuiWindowFlags_AlwaysAutoResize);
        auto& unmatched = m_schemaRegistry->unmatchedFiles();
        if (unmatched.empty()) {
            ImGui::TextColored(ImColor(100, 200, 100), "All YAML files have a matching schema.");
        } else {
            ImGui::TextColored(ImColor(200, 100, 100), "%zu file(s) without schema:", unmatched.size());
            ImGui::Separator();
            for (auto& f : unmatched)
                ImGui::BulletText("%s", f.c_str());
        }
        ImGui::End();
    }

    renderConfirmDialog();
    renderSaveAsDialog();
    renderNewFileDialog();

    if (m_showSchemaInspector) {
        ImGui::Begin("Schema Inspector", &m_showSchemaInspector, ImGuiWindowFlags_AlwaysAutoResize);
        Document* doc = activeDocOrNull();
        if (!doc || doc->schemaPath.empty()) {
            ImGui::TextDisabled("No schema loaded");
        } else {
            ImGui::Text("Schema: %s", doc->schemaTitle.c_str());
            ImGui::Text("File: %s", doc->schemaPath.c_str());
            ImGui::Separator();
            std::ifstream fin(doc->schemaPath);
            if (fin.is_open()) {
                std::stringstream ss;
                ss << fin.rdbuf();
                std::string schemaText = ss.str();
                ImGui::BeginChild("SchemaText", ImVec2(500, 400), true);
                ImGui::TextUnformatted(schemaText.c_str());
                ImGui::EndChild();
            } else {
                ImGui::TextColored(ImColor(200, 100, 100), "Cannot read schema file");
            }
        }
        ImGui::End();
    }

    if (m_showFindInFiles)
        renderFindInFiles();

    ImVec2 avail = ImGui::GetContentRegionAvail();
    float statusHeight = ImGui::GetFrameHeight() + ImGui::GetStyle().ItemSpacing.y;

    ImGui::BeginChild("MainArea", ImVec2(avail.x, avail.y - statusHeight), false);

    // Resizable left panel
    m_filePanelWidth = std::max(140.0f, std::min(m_filePanelWidth, avail.x * 0.5f));

    ImGui::BeginChild("FilePanel", ImVec2(m_filePanelWidth, 0), true);
    ImGui::Text("File Browser");
    ImGui::Separator();
    ImGui::BeginChild("FileTreeScroll");
    m_fileBrowser->render();
    ImGui::EndChild();
    ImGui::EndChild();

    ImGui::SameLine();

    // Vertical splitter handle (span full height)
    ImGui::PushStyleColor(ImGuiCol_Button, ImVec4(0,0,0,0));
    ImGui::PushStyleColor(ImGuiCol_ButtonActive, ImVec4(0.5f,0.5f,0.5f,0.3f));
    ImGui::PushStyleColor(ImGuiCol_ButtonHovered, ImVec4(0.5f,0.5f,0.5f,0.2f));
    const float splitterW = 6.0f;
    float panelH = ImGui::GetContentRegionAvail().y;
    ImGui::InvisibleButton("##split", ImVec2(splitterW, panelH));
    ImGui::PopStyleColor(3);
    if (ImGui::IsItemActive() && ImGui::IsMouseDragging(0, 0))
        m_filePanelWidth += ImGui::GetIO().MouseDelta.x;
    if (ImGui::IsItemHovered())
        ImGui::SetMouseCursor(ImGuiMouseCursor_ResizeEW);

    ImGui::SameLine();

    ImGui::BeginChild("EditorPanel", ImVec2(0, 0), true);

    renderTabBar();

    Document* doc = activeDocOrNull();
    if (doc && doc->isOpen()) {
        std::string filename = fs::path(doc->path()).filename().string();
        ImGui::Text("%s", filename.c_str());
        if (!doc->schemaTitle.empty()) {
            ImGui::SameLine();
            ImGui::TextDisabled("(%s)", doc->schemaTitle.c_str());
        }
        if (doc->yamlDoc->isDirty()) {
            ImGui::SameLine();
            ImGui::TextColored(ImColor(200, 200, 100), "(modified)");
        }
        if (doc->readOnly) {
            ImGui::SameLine();
            ImGui::TextColored(ImColor(200, 100, 100), "(read-only)");
        }

        if (checkFileChanged(*doc)) {
            ImGui::SameLine();
            ImGui::TextColored(ImColor(255, 100, 0), "(changed on disk!)");
            ImGui::SameLine();
            if (ImGui::SmallButton("Reload")) {
                std::string savedPath = doc->path();
                closeDocument(m_activeDoc);
                openFile(savedPath);
            }
        }

        ImGui::SameLine(0, 12);
        if (doc->rawMode)
            ImGui::TextColored(ImColor(100, 200, 255), "[Raw]");
        else
            ImGui::TextDisabled("[Form]");
        ImGui::SameLine();
        if (ImGui::SmallButton(doc->rawMode ? "Form View" : "Raw View")) {
            if (!doc->rawMode) {
                syncRawFromDataImpl(*doc);
                doc->rawParseError.clear();
            }
            doc->rawMode = !doc->rawMode;
        }

        ImGui::Separator();

        // File info bar
        std::error_code ec;
        auto fsize = fs::file_size(doc->path(), ec);
        if (ec == std::error_code{}) {
            ImGui::TextDisabled("%s", formatFileSize(fsize).c_str());
            if (!doc->rawMode) {
                ImGui::SameLine();
                int keyCount = 0;
                if (doc->yamlDoc->root().IsMap())
                    keyCount = (int)doc->yamlDoc->root().size();
                ImGui::TextDisabled("  |  %d top-level key(s)", keyCount);
            }
            ImGui::Separator();
        }

        if (doc->rawMode) {
            renderRawEditor(*doc);
        } else if (doc->schema) {
            renderEditorPanel();
        } else {
            ImGui::TextColored(ImColor(200, 100, 100), "No schema found for this file.");
            ImGui::Text("The file was loaded but no matching schema could be determined.");
            ImGui::Separator();
            if (ImGui::Button("Switch to Raw View")) {
                syncRawFromDataImpl(*doc);
                doc->rawParseError.clear();
                doc->rawMode = true;
            }
        }
    } else {
        ImGui::SetCursorPosY(ImGui::GetContentRegionAvail().y * 0.3f);
        ImGui::SetCursorPosX(ImGui::GetContentRegionAvail().x * 0.15f);
        ImGui::TextDisabled("Select a YAML file from the browser to begin editing");
    }

    ImGui::EndChild(); // EditorPanel
    ImGui::EndChild(); // MainArea

    renderStatusBar();

    if (m_fileBrowser->hasSelectionChanged()) {
        std::string file = m_fileBrowser->selectedFile();
        if (!file.empty())
            openFile(file);
        m_fileBrowser->clearSelectionChanged();
    }
}

void App::renderTabBar() {
    if (m_documents.empty()) return;

    ImGuiTabBarFlags tabFlags = ImGuiTabBarFlags_Reorderable | ImGuiTabBarFlags_AutoSelectNewTabs;
    if (ImGui::BeginTabBar("##DocTabs", tabFlags)) {
        int toClose = -1;
        for (int i = 0; i < (int)m_documents.size(); i++) {
            auto& doc = m_documents[i];
            std::string label = fs::path(doc.path()).filename().string();
            if (doc.yamlDoc->isDirty()) label += " *";

            bool open = true;
            bool selected = (i == m_activeDoc);
            ImGuiTabItemFlags itemFlags = 0;
            if (selected)
                itemFlags |= ImGuiTabItemFlags_SetSelected;

            if (ImGui::BeginTabItem(label.c_str(), &open, itemFlags)) {
                if (ImGui::IsItemHovered())
                    ImGui::SetTooltip("%s", doc.path().c_str());
                if (i != m_activeDoc)
                    m_activeDoc = i;
                ImGui::EndTabItem();
            }

            if (!open)
                toClose = i;
        }

        if (toClose >= 0)
            closeDocument(toClose);

        ImGui::EndTabBar();
    }
}

void App::renderMenuBar() {
    ImGui::BeginMainMenuBar();

    Document* doc = activeDocOrNull();

    if (ImGui::BeginMenu("File")) {
        if (ImGui::MenuItem("New File...", "Ctrl+N")) {
            m_showNewFile = true;
            std::string def = m_examplesDir + "/untitled.yaml";
            size_t n = def.copy(m_newFilePath, sizeof(m_newFilePath) - 1);
            m_newFilePath[n] = '\0';
        }
        bool canSave = doc && doc->isOpen() && doc->yamlDoc->isDirty();
        if (ImGui::MenuItem("Save", "Ctrl+S", false, canSave))
            saveFile();
        bool canSaveAs = doc && doc->isOpen();
        if (ImGui::MenuItem("Save As...", "Ctrl+Shift+S", false, canSaveAs)) {
            m_showSaveAs = true;
            std::string cur = doc->path();
            size_t n = cur.copy(m_saveAsPath, sizeof(m_saveAsPath) - 1);
            m_saveAsPath[n] = '\0';
        }
        ImGui::Separator();
        bool canClose = doc && doc->isOpen();
        if (ImGui::MenuItem("Close", "Ctrl+Shift+W", false, canClose))
            closeFile();
        ImGui::Separator();
        if (!m_recentFiles.empty() && ImGui::BeginMenu("Recent Files")) {
            for (auto it = m_recentFiles.rbegin(); it != m_recentFiles.rend(); ++it) {
                if (ImGui::MenuItem(it->c_str()))
                    openFile(*it);
            }
            ImGui::EndMenu();
        }
        if (ImGui::MenuItem("Quit", "Ctrl+Q"))
            requestQuit();
        ImGui::EndMenu();
    }

    if (ImGui::BeginMenu("View")) {
        ImGui::MenuItem("ImGui Demo", nullptr, &m_showDemoWindow);
        ImGui::MenuItem("Unmatched Files", nullptr, &m_showUnmatched);
        ImGui::MenuItem("Schema Inspector", nullptr, &m_showSchemaInspector);
        ImGui::MenuItem("Find in Files", "Ctrl+Shift+F", &m_showFindInFiles);
        ImGui::Separator();
        if (doc && ImGui::MenuItem("Toggle Raw YAML Mode", nullptr, &doc->rawMode)) {
            if (doc->rawMode)
                syncRawFromDataImpl(*doc);
        } else if (!doc) {
            ImGui::MenuItem("Toggle Raw YAML Mode", nullptr, false, false);
        }
        ImGui::Separator();
        if (ImGui::MenuItem("Toggle Dark/Light Theme", "Ctrl+T"))
            toggleTheme();
        if (ImGui::MenuItem("Rescan Examples")) {
            SchemaRegistry newReg;
            if (newReg.initialize(m_schemasDir, m_examplesDir)) {
                *m_schemaRegistry = std::move(newReg);
                m_fileBrowser->initialize(m_schemaRegistry.get());
                setStatus("Rescanned");
            }
        }
        ImGui::EndMenu();
    }

    if (ImGui::BeginMenu("Help")) {
        if (ImGui::MenuItem("About")) m_showAbout = true;
        ImGui::EndMenu();
    }

    ImGui::EndMainMenuBar();
}

void App::renderStatusBar() {
    ImVec2 avail = ImGui::GetContentRegionAvail();
    float statusHeight = ImGui::GetFrameHeight() + ImGui::GetStyle().ItemSpacing.y;

    ImGui::BeginChild("StatusBar", ImVec2(avail.x, statusHeight), false);
    ImGui::Separator();

    Document* doc = activeDocOrNull();
    std::string status;
    if (doc && doc->isOpen()) {
        status = fs::path(doc->path()).filename().string();
        if (doc->yamlDoc->isDirty())
            status += " (modified)";
        if (doc->rawMode)
            status += " [raw]";
    }
    if (!m_statusMessage.empty()) {
        if (!status.empty()) status += " | ";
        status += m_statusMessage;
    }
    if (status.empty())
        status = "Ready";

    ImGui::Text("%s", status.c_str());
    ImGui::EndChild();
}

void App::renderConfirmDialog() {
    if (m_pendingAction == ConfirmAction::None)
        return;

    ImGui::OpenPopup("Unsaved Changes");

    if (ImGui::BeginPopupModal("Unsaved Changes", nullptr, ImGuiWindowFlags_AlwaysAutoResize)) {
        ImGui::Text("Save changes before closing?");
        ImGui::Separator();

        if (m_pendingAction == ConfirmAction::CloseFile && m_pendingDocIdx >= 0 &&
            m_pendingDocIdx < (int)m_documents.size()) {
            auto& d = m_documents[m_pendingDocIdx];
            ImGui::Text("File: %s", fs::path(d.path()).filename().c_str());
            if (ImGui::Button("Save", ImVec2(120, 0))) {
                int prevActive = m_activeDoc;
                m_activeDoc = m_pendingDocIdx;
                saveFile();
                m_activeDoc = prevActive;
                m_documents[m_pendingDocIdx].yamlDoc->clearDirty();
                doEraseDoc(m_pendingDocIdx);
                m_pendingAction = ConfirmAction::None;
                ImGui::CloseCurrentPopup();
                if (!m_pendingFile.empty()) {
                    openFile(m_pendingFile);
                    m_pendingFile.clear();
                }
            }
            ImGui::SameLine();
            if (ImGui::Button("Discard", ImVec2(120, 0))) {
                doEraseDoc(m_pendingDocIdx);
                m_pendingAction = ConfirmAction::None;
                ImGui::CloseCurrentPopup();
                if (!m_pendingFile.empty()) {
                    openFile(m_pendingFile);
                    m_pendingFile.clear();
                }
            }
        } else if (m_pendingAction == ConfirmAction::Quit) {
            if (ImGui::Button("Save All", ImVec2(120, 0))) {
                for (int i = 0; i < (int)m_documents.size(); i++) {
                    m_activeDoc = i;
                    saveFile();
                }
                m_documents.clear();
                m_activeDoc = -1;
                m_pendingAction = ConfirmAction::None;
                m_wantsToQuit = true;
                ImGui::CloseCurrentPopup();
            }
            ImGui::SameLine();
            if (ImGui::Button("Discard All", ImVec2(120, 0))) {
                m_documents.clear();
                m_activeDoc = -1;
                m_pendingAction = ConfirmAction::None;
                m_wantsToQuit = true;
                ImGui::CloseCurrentPopup();
            }
        }

        ImGui::SameLine();
        if (ImGui::Button("Cancel", ImVec2(120, 0))) {
            m_pendingFile.clear();
            m_pendingAction = ConfirmAction::None;
            ImGui::CloseCurrentPopup();
        }
        ImGui::EndPopup();
    }
}

void App::renderEditorPanel() {
    Document* doc = activeDocOrNull();
    if (!doc) return;

    // Validation error summary
    auto errors = m_formRenderer->collectErrors(*doc->schema, doc->yamlDoc->root());
    if (!errors.empty()) {
        ImVec4 color = (errors.size() > 0) ? ImVec4(1, 0.2f, 0.2f, 1) : ImVec4(0.5f, 1, 0.5f, 1);
        ImGui::TextColored(color, "%zu validation error(s)", errors.size());
        if (ImGui::IsItemHovered() && ImGui::IsMouseClicked(0)) {
            ImGui::OpenPopup("ValidationErrors");
        }
        if (ImGui::BeginPopup("ValidationErrors")) {
            ImGui::TextColored(ImVec4(1, 0.2f, 0.2f, 1), "Validation Errors");
            ImGui::Separator();
            for (auto& e : errors) {
                ImGui::TextColored(ImVec4(0.8f, 0.6f, 0.2f, 1), "%s", e.path.c_str());
                ImGui::SameLine();
                ImGui::TextDisabled("  %s", e.message.c_str());
            }
            ImGui::EndPopup();
        }
    }

    ImGui::BeginChild("FormScroll", ImVec2(0, -ImGui::GetFrameHeightWithSpacing() - 4));
    bool changed = m_formRenderer->render(*doc->schema, doc->yamlDoc->root(), false);
    if (changed) {
        pushUndo();
        doc->yamlDoc->markDirty();
    }
    ImGui::EndChild();

    ImGui::Separator();

    if (doc->schema && !doc->rawMode) {
        if (ImGui::SmallButton("Expand All")) {
            m_formRenderer->expandAll();
        }
        ImGui::SameLine();
        if (ImGui::SmallButton("Collapse All")) {
            m_formRenderer->collapseAll();
        }
        ImGui::SameLine();
        ImGui::Text("|");
        ImGui::SameLine();
    }

    if (doc->schema && !doc->readOnly) {
        if (ImGui::Button("Format All C Code")) {
            int count = 0;
            formatAllCCode(*doc->schema, doc->yamlDoc->root(), count);
            if (count > 0) {
                doc->yamlDoc->markDirty();
                setStatus("Formatted " + std::to_string(count) + " C code field(s)");
            } else {
                setStatus("No C code fields to format");
            }
        }
        ImGui::SameLine();
    }

    if (doc->yamlDoc->isDirty()) {
        if (ImGui::Button("Save Changes"))
            saveFile();
        ImGui::SameLine();
        if (ImGui::Button("Revert")) {
            std::string path = doc->path();
            closeDocument(m_activeDoc);
            openFile(path);
        }
        ImGui::SameLine();
        if (!doc->undoStack.empty()) {
            if (ImGui::SmallButton("Undo"))
                undo();
            ImGui::SameLine();
            ImGui::TextDisabled("(%zu)", doc->undoStack.size());
            ImGui::SameLine();
        }
        ImGui::Text("Unsaved changes");
    } else {
        ImGui::TextDisabled("No unsaved changes");
    }
}

void App::renderRawEditor(Document& doc) {
    if (!doc.rawParseError.empty()) {
        ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(1, 0.3f, 0.3f, 1));
        ImGui::TextWrapped("Parse Error: %s", doc.rawParseError.c_str());
        ImGui::PopStyleColor();
        ImGui::Separator();
    }

    // Find/Replace bar
    if (doc.findBarOpen) {
        ImGui::Separator();
        float barHeight = ImGui::GetFrameHeightWithSpacing() * 2 + 6;
        ImGui::BeginChild("##findBar", ImVec2(0, barHeight), false);

        ImGui::Text("Find");
        ImGui::SameLine();
        ImGui::SetNextItemWidth(200);
        if (ImGui::InputText("##findInput", doc.findText, sizeof(doc.findText))) {
            buildFindMatches(doc);
        }
        ImGui::SameLine();

        bool hasFind = strlen(doc.findText) > 0 && !doc.findMatches.empty();
        if (ImGui::SmallButton("Prev") && hasFind) {
            doc.findCurrentIdx--;
            if (doc.findCurrentIdx < 0) doc.findCurrentIdx = (int)doc.findMatches.size() - 1;
        }
        ImGui::SameLine();
        if (ImGui::SmallButton("Next") && hasFind) {
            doc.findCurrentIdx++;
            if (doc.findCurrentIdx >= (int)doc.findMatches.size()) doc.findCurrentIdx = 0;
        }
        ImGui::SameLine();
        if (hasFind)
            ImGui::Text("  %d/%d", doc.findCurrentIdx + 1, (int)doc.findMatches.size());
        else
            ImGui::TextDisabled("  no matches");

        ImGui::SameLine();
        ImGui::Text("  Rep");
        ImGui::SameLine();
        ImGui::SetNextItemWidth(150);
        ImGui::InputText("##repInput", doc.replaceText, sizeof(doc.replaceText));
        ImGui::SameLine();

        if (ImGui::SmallButton("Rep") && hasFind) {
            replaceFindMatch(doc);
        }
        ImGui::SameLine();
        if (ImGui::SmallButton("Rep All") && !doc.findMatches.empty()) {
            replaceFindAll(doc);
        }

        if (ImGui::IsKeyPressed(ImGuiKey_Escape)) {
            doc.findBarOpen = false;
        }

        ImGui::EndChild();
        ImGui::Separator();
    }

    ImGui::BeginChild("RawScroll", ImVec2(0, -ImGui::GetFrameHeightWithSpacing() - 4));

    constexpr size_t kBufSize = 1024 * 1024;
    doc.rawText.resize(kBufSize - 1);

    if (ImGui::InputTextMultiline(
        "##raw",
        doc.rawText.data(), kBufSize,
        ImVec2(-FLT_MIN, -FLT_MIN),
        ImGuiInputTextFlags_AllowTabInput
    )) {
        doc.findMatches.clear();
        doc.findCurrentIdx = -1;
    }

    doc.rawText.resize(strlen(doc.rawText.c_str()));

    if (doc.findBarOpen && !doc.findMatches.empty() && doc.findCurrentIdx >= 0) {
        size_t pos = doc.findMatches[doc.findCurrentIdx];
        int line = 1;
        for (size_t i = 0; i < pos && i < doc.rawText.size(); i++) {
            if (doc.rawText[i] == '\n') line++;
        }
        ImGui::TextColored(ImVec4(0.4f, 0.8f, 1.0f, 1.0f), "Match at line %d", line);
    }

    ImGui::EndChild();

    ImGui::Separator();
    if (ImGui::Button("Apply Raw to Form")) {
        pushUndo();
        try {
            YAML::Node parsed = YAML::Load(doc.rawText);
            if (!parsed.IsDefined())
                parsed = YAML::Node(YAML::NodeType::Map);
            doc.yamlDoc->root() = parsed;
            doc.yamlDoc->markDirty();
            doc.rawParseError.clear();
            setStatus("Applied raw YAML to form");
        } catch (const YAML::Exception& e) {
            doc.rawParseError = e.what();
        }
    }
    ImGui::SameLine();
    if (ImGui::Button("Sync from Form")) {
        syncRawFromDataImpl(doc);
        doc.rawParseError.clear();
        setStatus("Synced raw view from form");
    }
    ImGui::SameLine();
    if (ImGui::Button(doc.findBarOpen ? "Hide Find" : "Find / Replace")) {
        doc.findBarOpen = !doc.findBarOpen;
        if (doc.findBarOpen)
            buildFindMatches(doc);
    }
    ImGui::SameLine();
    if (doc.yamlDoc->isDirty()) {
        if (ImGui::Button("Save Changes"))
            saveFile();
        ImGui::SameLine();
        ImGui::Text("Unsaved changes");
    } else {
        ImGui::TextDisabled("No unsaved changes");
    }
}

void App::buildFindMatches(Document& doc) {
    doc.findMatches.clear();
    doc.findCurrentIdx = -1;
    if (strlen(doc.findText) == 0) return;
    std::string needle(doc.findText);
    const std::string& haystack = doc.rawText;
    for (size_t pos = 0; ; ) {
        pos = haystack.find(needle, pos);
        if (pos == std::string::npos) break;
        doc.findMatches.push_back(pos);
        pos += needle.size();
    }
    if (!doc.findMatches.empty())
        doc.findCurrentIdx = 0;
}

void App::replaceFindMatch(Document& doc) {
    if (doc.findMatches.empty() || doc.findCurrentIdx < 0) return;
    size_t pos = doc.findMatches[doc.findCurrentIdx];
    std::string needle(doc.findText);
    std::string repl(doc.replaceText);
    std::string text(doc.rawText);
    text.replace(pos, needle.size(), repl);
    doc.rawText = text;
    doc.yamlDoc->markDirty();
    buildFindMatches(doc);
}

void App::replaceFindAll(Document& doc) {
    if (doc.findMatches.empty()) return;
    std::string needle(doc.findText);
    std::string repl(doc.replaceText);
    std::string text(doc.rawText);
    size_t pos = 0;
    int count = 0;
    while ((pos = text.find(needle, pos)) != std::string::npos) {
        text.replace(pos, needle.size(), repl);
        pos += repl.size();
        count++;
    }
    doc.rawText = text;
    doc.yamlDoc->markDirty();
    buildFindMatches(doc);
    setStatus("Replaced " + std::to_string(count) + " occurrence(s)");
}

void App::openFile(const std::string& path) {
    // If already open, switch to that tab
    for (int i = 0; i < (int)m_documents.size(); i++) {
        if (m_documents[i].path() == path) {
            m_activeDoc = i;
            return;
        }
    }

    // Prompt if there's a dirty document to close (but we're opening a NEW one, so just add)
    Document doc;
    doc.yamlDoc = std::make_unique<YamlDocument>();

    // Check read-only status and record modification time
    {
        std::error_code ec;
        auto perms = fs::status(path, ec).permissions();
        doc.readOnly = ec ? true : (perms & fs::perms::owner_write) == fs::perms::none;
        doc.modTime = fs::last_write_time(path, ec);
        doc.fileChangedWarn = false;
    }

    // Always try to load raw text first (for broken YAML recovery)
    {
        std::ifstream fin(path);
        if (!fin.is_open()) {
            setStatus("Error: Cannot read " + path);
            return;
        }
        std::stringstream ss;
        ss << fin.rdbuf();
        doc.rawText = ss.str();
        doc.rawParseError.clear();
    }

    if (!doc.yamlDoc->load(path)) {
        setStatus("YAML error in " + fs::path(path).filename().string());
        doc.schema.reset();
        doc.schemaName.clear();
        doc.schemaTitle.clear();
        doc.schemaPath.clear();
        doc.rawMode = true;
        doc.rawParseError = doc.yamlDoc->lastError();
        doc.yamlDoc->close();
        doc.yamlDoc->root() = YAML::Node(YAML::NodeType::Map);
        m_documents.push_back(std::move(doc));
        m_activeDoc = (int)m_documents.size() - 1;
        saveConfig();
        return;
    }

    std::string relStr = path;
    std::string rootStr = fs::path(m_projectRoot).string();
    if (path.find(rootStr) == 0 && rootStr.size() < path.size())
        relStr = path.substr(rootStr.size() + 1);

    auto* schemaInfo = m_schemaRegistry->findSchemaForFile(relStr);
    if (schemaInfo) {
        doc.schema = std::make_unique<SchemaField>(
            m_schemaParser->parseFile(schemaInfo->schemaPath));
        doc.schemaName = schemaInfo->name;
        doc.schemaTitle = schemaInfo->displayName;
        doc.schemaPath = schemaInfo->schemaPath;
        m_statusMessage = "Opened " + relStr + " (" + schemaInfo->displayName + ")";
    } else {
        doc.schema.reset();
        doc.schemaName.clear();
        doc.schemaTitle.clear();
        doc.schemaPath.clear();
        m_statusMessage = "Opened " + relStr + " (no schema match)";
        doc.rawMode = true;
    }

    syncRawFromDataImpl(doc);
    doc.rawParseError.clear();
    doc.yamlDoc->clearDirty();

    // Track recent files (max 10)
    {
        auto it = std::find(m_recentFiles.begin(), m_recentFiles.end(), path);
        if (it != m_recentFiles.end())
            m_recentFiles.erase(it);
        m_recentFiles.push_back(path);
        if (m_recentFiles.size() > 10)
            m_recentFiles.erase(m_recentFiles.begin());
    }

    m_documents.push_back(std::move(doc));
    m_activeDoc = (int)m_documents.size() - 1;
    saveConfig();
}

void App::closeDocument(int idx) {
    if (idx < 0 || idx >= (int)m_documents.size()) return;
    auto& doc = m_documents[idx];
    if (doc.yamlDoc && doc.yamlDoc->isDirty()) {
        m_pendingAction = ConfirmAction::CloseFile;
        m_pendingDocIdx = idx;
        return;
    }
    doEraseDoc(idx);
}

void App::doEraseDoc(int idx) {
    m_documents.erase(m_documents.begin() + idx);
    if (m_activeDoc >= (int)m_documents.size())
        m_activeDoc = (int)m_documents.size() - 1;
    else if (m_activeDoc > idx)
        m_activeDoc--;
    saveConfig();
    if (m_documents.empty())
        m_activeDoc = -1;
    setStatus("Closed");
}

void App::closeFile() {
    if (m_activeDoc < 0 || m_activeDoc >= (int)m_documents.size()) return;
    closeDocument(m_activeDoc);
}

void App::saveFile() {
    Document* doc = activeDocOrNull();
    if (!doc || !doc->isOpen()) return;

    if (doc->readOnly) {
        setStatus("Cannot save: file is read-only");
        return;
    }

    if (doc->rawMode) {
        pushUndo();
        try {
            YAML::Node parsed = YAML::Load(doc->rawText);
            if (!parsed.IsDefined())
                parsed = YAML::Node(YAML::NodeType::Map);
            doc->yamlDoc->root() = parsed;
            doc->rawParseError.clear();
        } catch (const YAML::Exception& e) {
            doc->rawParseError = e.what();
            setStatus("Save error: parse failed — " + std::string(e.what()));
            return;
        }
    }

    if (doc->yamlDoc->save()) {
        setStatus("Saved");
        saveConfig();
    } else {
        setStatus("Save error: " + doc->yamlDoc->lastError());
    }
}

void App::saveAs(const std::string& path) {
    Document* doc = activeDocOrNull();
    if (!doc || !doc->isOpen()) return;

    if (doc->rawMode) {
        pushUndo();
        try {
            YAML::Node parsed = YAML::Load(doc->rawText);
            if (!parsed.IsDefined())
                parsed = YAML::Node(YAML::NodeType::Map);
            doc->yamlDoc->root() = parsed;
            doc->rawParseError.clear();
        } catch (const YAML::Exception& e) {
            doc->rawParseError = e.what();
            setStatus("Save As error: parse failed — " + std::string(e.what()));
            return;
        }
    }

    if (doc->yamlDoc->saveAs(path)) {
        setStatus("Saved as " + path);
        saveConfig();
        doc->readOnly = false;
        std::error_code ec;
        doc->modTime = fs::last_write_time(path, ec);
        doc->fileChangedWarn = false;
    } else {
        setStatus("Save As error: " + doc->yamlDoc->lastError());
    }
}

void App::formatAllCCode(const SchemaField& field, YAML::Node data, int& count) {
    if (field.isCCodeField && data.IsDefined() && !data.IsNull()) {
        if (field.type == "string") {
            std::string val = data.Scalar();
            std::string formatted;
            if (CCodeEditor::FormatCCode(val, formatted) && formatted != val) {
                data = formatted;
                count++;
            }
        } else if (field.type == "object") {
            for (auto it = data.begin(); it != data.end(); ++it) {
                if (it->second.IsDefined() && it->second.IsScalar()) {
                    std::string val = it->second.Scalar();
                    std::string formatted;
                    if (CCodeEditor::FormatCCode(val, formatted) && formatted != val) {
                        it->second = formatted;
                        count++;
                    }
                }
            }
        }
    }
    if (field.type == "array" && field.items && data.IsSequence()) {
        for (size_t i = 0; i < data.size(); i++)
            formatAllCCode(*field.items, data[i], count);
    }
    if (field.type == "object" || field.type == "oneOf") {
        for (const auto& prop : field.properties) {
            if (data[prop.name].IsDefined())
                formatAllCCode(prop, data[prop.name], count);
        }
        for (const auto& variant : field.oneOfVariants) {
            for (const auto& prop : variant) {
                if (data[prop.name].IsDefined())
                    formatAllCCode(prop, data[prop.name], count);
            }
        }
    }
}

void App::pushUndo() {
    Document* doc = activeDocOrNull();
    if (!doc || !doc->isOpen()) return;
    doc->undoStack.push_back(YAML::Clone(doc->yamlDoc->root()));
    if (doc->undoStack.size() > 50)
        doc->undoStack.erase(doc->undoStack.begin());
    doc->redoStack.clear();
}

void App::undo() {
    Document* doc = activeDocOrNull();
    if (!doc || doc->undoStack.empty() || !doc->isOpen()) return;
    doc->redoStack.push_back(YAML::Clone(doc->yamlDoc->root()));
    doc->yamlDoc->root() = YAML::Clone(doc->undoStack.back());
    doc->undoStack.pop_back();
    doc->yamlDoc->markDirty();
    syncRawFromDataImpl(*doc);
    setStatus("Undo (" + std::to_string(doc->undoStack.size()) + " remaining)");
}

void App::redo() {
    Document* doc = activeDocOrNull();
    if (!doc || doc->redoStack.empty() || !doc->isOpen()) return;
    doc->undoStack.push_back(YAML::Clone(doc->yamlDoc->root()));
    doc->yamlDoc->root() = YAML::Clone(doc->redoStack.back());
    doc->redoStack.pop_back();
    doc->yamlDoc->markDirty();
    syncRawFromDataImpl(*doc);
    setStatus("Redo");
}

bool App::checkFileChanged(Document& doc) {
    if (!doc.isOpen()) return false;
    std::error_code ec;
    auto newTime = fs::last_write_time(doc.path(), ec);
    if (ec) return false;
    if (newTime != doc.modTime) {
        if (!doc.fileChangedWarn)
            setStatus("File changed on disk — reload or save to overwrite");
        doc.fileChangedWarn = true;
        return true;
    }
    doc.fileChangedWarn = false;
    return false;
}

void App::handleShortcuts() {
    ImGuiIO& io = ImGui::GetIO();
    if (!io.WantCaptureKeyboard) return;

    bool ctrl = io.KeyCtrl;
    bool shift = io.KeyShift;
    Document* doc = activeDocOrNull();

    if (ctrl && !shift && ImGui::IsKeyPressed(ImGuiKey_N, false)) {
        m_showNewFile = true;
        std::string def = m_examplesDir + "/untitled.yaml";
        size_t n = def.copy(m_newFilePath, sizeof(m_newFilePath) - 1);
        m_newFilePath[n] = '\0';
    }
    if (ctrl && !shift && ImGui::IsKeyPressed(ImGuiKey_S, false) && doc && doc->isOpen() && doc->yamlDoc->isDirty())
        saveFile();
    if (ctrl && shift && ImGui::IsKeyPressed(ImGuiKey_S, false) && doc && doc->isOpen()) {
        m_showSaveAs = true;
        std::string cur = doc->path();
        size_t n = cur.copy(m_saveAsPath, sizeof(m_saveAsPath) - 1);
        m_saveAsPath[n] = '\0';
    }
    if (ctrl && shift && ImGui::IsKeyPressed(ImGuiKey_W, false))
        closeFile();
    if (ctrl && !shift && ImGui::IsKeyPressed(ImGuiKey_W, false) && !m_documents.empty()) {
        closeFile();
    }
    if (ctrl && !shift && ImGui::IsKeyPressed(ImGuiKey_Tab, false) && m_documents.size() > 1) {
        m_activeDoc = (m_activeDoc + 1) % (int)m_documents.size();
    }
    if (ctrl && shift && ImGui::IsKeyPressed(ImGuiKey_Tab, false) && m_documents.size() > 1) {
        m_activeDoc = (m_activeDoc - 1 + (int)m_documents.size()) % (int)m_documents.size();
    }
    if (ctrl && !shift && ImGui::IsKeyPressed(ImGuiKey_Q, false))
        requestQuit();
    if (ctrl && !shift && ImGui::IsKeyPressed(ImGuiKey_R, false) && doc && doc->isOpen()) {
        if (!doc->rawMode)
            syncRawFromDataImpl(*doc);
        doc->rawMode = !doc->rawMode;
    }
    if (ctrl && !shift && ImGui::IsKeyPressed(ImGuiKey_T, false))
        toggleTheme();
    if (ctrl && !shift && ImGui::IsKeyPressed(ImGuiKey_Z, false))
        undo();
    if (ctrl && !shift && ImGui::IsKeyPressed(ImGuiKey_Y, false))
        redo();
    if (ctrl && shift && ImGui::IsKeyPressed(ImGuiKey_Z, false))
        redo();
    if (ctrl && !shift && ImGui::IsKeyPressed(ImGuiKey_Equal, false)) {
        float& scale = io.FontGlobalScale;
        scale = std::min(scale + 0.1f, 2.0f);
        setStatus("Zoom " + std::to_string((int)(scale * 100)) + "%");
    }
    if (ctrl && !shift && ImGui::IsKeyPressed(ImGuiKey_Minus, false)) {
        float& scale = io.FontGlobalScale;
        scale = std::max(scale - 0.1f, 0.5f);
        setStatus("Zoom " + std::to_string((int)(scale * 100)) + "%");
    }
    if (ctrl && !shift && ImGui::IsKeyPressed(ImGuiKey_0, false)) {
        io.FontGlobalScale = 1.0f;
        setStatus("Zoom 100%");
    }
    if (ctrl && shift && ImGui::IsKeyPressed(ImGuiKey_F, false)) {
        m_showFindInFiles = !m_showFindInFiles;
        if (m_showFindInFiles && strlen(m_ffQuery) > 0)
            doFindInFiles();
    }
    if (ctrl && !shift && ImGui::IsKeyPressed(ImGuiKey_F, false) && doc && doc->isOpen() && doc->rawMode) {
        doc->findBarOpen = !doc->findBarOpen;
        if (doc->findBarOpen)
            buildFindMatches(*doc);
    }
}

void App::toggleTheme() {
    m_darkTheme = !m_darkTheme;
    if (m_darkTheme)
        ImGui::StyleColorsDark();
    else
        ImGui::StyleColorsLight();
    saveConfig();
    setStatus(m_darkTheme ? "Dark theme" : "Light theme");
}

void App::renderSaveAsDialog() {
    if (!m_showSaveAs) return;
    ImGui::OpenPopup("Save As");
    m_showSaveAs = false;

    if (ImGui::BeginPopupModal("Save As", nullptr, ImGuiWindowFlags_AlwaysAutoResize)) {
        ImGui::Text("Save file as:");
        ImGui::SetNextItemWidth(400);
        ImGui::InputText("##path", m_saveAsPath, sizeof(m_saveAsPath));
        ImGui::Separator();
        if (ImGui::Button("Save")) {
            std::string path(m_saveAsPath);
            if (!path.empty()) {
                saveAs(path);
                ImGui::CloseCurrentPopup();
            }
        }
        ImGui::SameLine();
        if (ImGui::Button("Cancel"))
            ImGui::CloseCurrentPopup();
        ImGui::EndPopup();
    }
}

void App::renderNewFileDialog() {
    if (!m_showNewFile) return;
    ImGui::OpenPopup("New File");
    m_showNewFile = false;

    if (ImGui::BeginPopupModal("New File", nullptr, ImGuiWindowFlags_AlwaysAutoResize)) {
        ImGui::Text("Create new YAML file:");
        ImGui::SetNextItemWidth(400);
        ImGui::InputText("##path", m_newFilePath, sizeof(m_newFilePath));
        ImGui::Separator();
        if (ImGui::Button("Create")) {
            std::string path(m_newFilePath);
            if (!path.empty()) {
                std::ofstream fout(path);
                if (fout.is_open()) {
                    fout << "# New file\n";
                    fout.close();
                    openFile(path);
                    setStatus("Created " + path);
                } else {
                    setStatus("Error: Cannot create " + path);
                }
                ImGui::CloseCurrentPopup();
            }
        }
        ImGui::SameLine();
        if (ImGui::Button("Cancel"))
            ImGui::CloseCurrentPopup();
        ImGui::EndPopup();
    }
}

void App::renderFindInFiles() {
    if (!m_showFindInFiles) return;

    ImGui::Begin("Find in Files", &m_showFindInFiles, ImGuiWindowFlags_AlwaysAutoResize);
    ImGui::SetNextItemWidth(300);
    bool search = ImGui::InputTextWithHint("##ffquery", "Search across all YAML files...",
                                            m_ffQuery, sizeof(m_ffQuery),
                                            ImGuiInputTextFlags_EnterReturnsTrue);
    ImGui::SameLine();
    ImGui::Checkbox("Case", &m_ffCaseSensitive);
    ImGui::SameLine();
    if (ImGui::Button("Search") || search) {
        doFindInFiles();
    }

    if (m_ffResults.empty() && strlen(m_ffQuery) > 0) {
        ImGui::TextDisabled("No matches");
    }

    ImGui::BeginChild("##ffResults", ImVec2(550, 400), true);
    int resultIdx = 0;
    for (auto& r : m_ffResults) {
        ImGui::PushID(resultIdx++);

        std::string filename = fs::path(r.path).filename().string();
        ImGui::TextColored(ImVec4(0.3f, 0.7f, 1, 1), "%s", filename.c_str());
        ImGui::SameLine();
        ImGui::TextDisabled(":%d  ", r.line);
        ImGui::SameLine();
        bool clicked = ImGui::Selectable(r.text.c_str(), false, ImGuiSelectableFlags_AllowOverlap);
        if (clicked)
            openFile(r.path);

        ImGui::PopID();
    }
    ImGui::EndChild();

    ImGui::TextDisabled("%zu result(s)", m_ffResults.size());
    ImGui::End();
}

void App::doFindInFiles() {
    m_ffResults.clear();
    std::string query(m_ffQuery);
    if (query.empty()) return;

    std::error_code ec;
    auto opts = m_ffCaseSensitive ? std::string::npos : 0; // 0 means case-insensitive with std::string::find? No, std::string is always case-sensitive

    // Actually let's use simple find. If case-insensitive, we convert to lower
    std::string queryLower = query;
    if (!m_ffCaseSensitive) {
        std::transform(queryLower.begin(), queryLower.end(), queryLower.begin(), ::tolower);
    }

    for (auto& entry : fs::recursive_directory_iterator(m_examplesDir, ec)) {
        if (ec) break;
        if (!entry.is_regular_file()) continue;
        auto ext = entry.path().extension().string();
        if (ext != ".yaml" && ext != ".yml") continue;

        std::ifstream fin(entry.path());
        if (!fin) continue;

        std::string line;
        int lineNum = 0;
        while (std::getline(fin, line)) {
            lineNum++;
            std::string searchLine = line;
            if (!m_ffCaseSensitive) {
                std::transform(searchLine.begin(), searchLine.end(), searchLine.begin(), ::tolower);
            }
            if (searchLine.find(queryLower) != std::string::npos) {
                // Trim long lines
                if (line.size() > 200)
                    line = line.substr(0, 200) + "...";
                m_ffResults.push_back({entry.path().string(), lineNum, line});
            }
        }
    }
}

void App::requestQuit() {
    saveConfig();
    // Check if any document is dirty
    bool anyDirty = false;
    for (auto& d : m_documents) {
        if (d.isOpen() && d.yamlDoc->isDirty()) {
            anyDirty = true;
            break;
        }
    }
    if (anyDirty) {
        m_pendingAction = ConfirmAction::Quit;
        m_pendingDocIdx = -1; // signal "all documents"
    } else {
        m_wantsToQuit = true;
    }
}

void App::setStatus(const std::string& msg) {
    m_statusMessage = msg;
}
