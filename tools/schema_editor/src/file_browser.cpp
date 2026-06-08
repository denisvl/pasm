#include "file_browser.h"
#include "schema_registry.h"

#include <imgui.h>
#include <filesystem>
#include <algorithm>

namespace fs = std::filesystem;

void FileBrowser::initialize(SchemaRegistry* registry) {
    m_registry = registry;

    m_filterLabels = {"All"};
    m_filterSchemaIndices = {-1};
    for (int i = 0; i < (int)registry->schemas().size(); i++) {
        m_filterLabels.push_back(registry->schemas()[i].displayName);
        m_filterSchemaIndices.push_back(i);
    }
}

bool FileBrowser::matchesSearchFilter(const std::string& filename) const {
    if (m_searchFilter[0] == '\0') return true;
    std::string filter = m_searchFilter;
    std::string fname = filename;
    std::transform(filter.begin(), filter.end(), filter.begin(), ::tolower);
    std::transform(fname.begin(), fname.end(), fname.begin(), ::tolower);
    return fname.find(filter) != std::string::npos;
}

void FileBrowser::setOpenDirs(const std::vector<std::string>& dirs) {
    m_openDirs.clear();
    for (auto& d : dirs)
        m_openDirs.insert(d);
}

std::vector<std::string> FileBrowser::getOpenDirs() const {
    std::vector<std::string> out;
    for (auto& d : m_openDirs)
        out.push_back(d);
    return out;
}

void FileBrowser::render() {
    renderFilterTabs();

    ImGui::SetNextItemWidth(-1);
    ImGui::InputTextWithHint("##filter", "Search files...", m_searchFilter, sizeof(m_searchFilter));

    ImGui::Separator();

    ImGui::BeginChild("FileTree", ImVec2(0, 0), false, ImGuiWindowFlags_HorizontalScrollbar);
    renderTree();
    ImGui::EndChild();
}

void FileBrowser::renderFilterTabs() {
    if (ImGui::BeginTabBar("SchemaFilter", ImGuiTabBarFlags_FittingPolicyScroll)) {
        for (int i = 0; i < (int)m_filterLabels.size(); i++) {
            bool selected = (m_activeFilter == i);
            if (ImGui::TabItemButton(m_filterLabels[i].c_str(), selected ? ImGuiTabItemFlags_SetSelected : 0)) {
                if (m_activeFilter != i) {
                    m_activeFilter = i;
                    m_selectionChanged = true;
                }
            }
        }
        ImGui::EndTabBar();
    }
}

bool FileBrowser::matchesActiveFilter(const std::string& relPath) const {
    if (m_activeFilter == 0) return true;

    int schemaIdx = m_filterSchemaIndices[m_activeFilter];
    if (schemaIdx < 0 || schemaIdx >= (int)m_registry->schemas().size())
        return false;

    const auto* schema = &m_registry->schemas()[schemaIdx];
    const auto* matched = m_registry->findSchemaForFile(relPath);
    return matched == schema;
}

void FileBrowser::renderTree() {
    std::string examplesDir = m_registry->examplesDir();
    if (!fs::exists(examplesDir)) {
        ImGui::TextColored(ImColor(255, 100, 100), "examples/ not found");
        return;
    }

    renderDirectory(examplesDir, "");
}

void FileBrowser::renderDirectory(const std::string& dirPath, const std::string& relPath) {
    std::vector<fs::path> dirs;
    std::vector<fs::path> files;

    for (auto& entry : fs::directory_iterator(dirPath)) {
        auto name = entry.path().filename().string();
        if (name[0] == '.') continue;

        if (entry.is_directory())
            dirs.push_back(entry.path());
        else if (entry.path().extension() == ".yaml")
            files.push_back(entry.path());
    }

    std::sort(dirs.begin(), dirs.end());
    std::sort(files.begin(), files.end());

    for (auto& dir : dirs) {
        std::string dirRel = relPath.empty()
            ? dir.filename().string()
            : relPath + "/" + dir.filename().string();
        std::string label = "📁 " + dir.filename().string();

        bool hasVisibleContent = false;
        for (auto& f : files) {
            std::string fileRel = dirRel + "/" + f.filename().string();
            if (matchesActiveFilter(fileRel)) {
                hasVisibleContent = true;
                break;
            }
        }
        if (!hasVisibleContent) {
            for (auto& subdir : dirs) {
                // check subdirs for content - simplified: always show dirs
                hasVisibleContent = true;
                break;
            }
        }

        // Show directory with open/close state tracking
        bool isOpen = m_openDirs.find(dirRel) != m_openDirs.end();
        ImGuiTreeNodeFlags dirFlags = ImGuiTreeNodeFlags_SpanFullWidth;
        if (isOpen)
            ImGui::SetNextItemOpen(true);

        bool dirOpen = ImGui::TreeNodeEx(label.c_str(), dirFlags);
        if (dirOpen) {
            m_openDirs.insert(dirRel);
        } else {
            m_openDirs.erase(dirRel);
        }

        if (dirOpen) {
            renderDirectory(dir.string(), dirRel);
            ImGui::TreePop();
        }
    }

    for (auto& file : files) {
        std::string fileRel = relPath.empty()
            ? file.filename().string()
            : relPath + "/" + file.filename().string();

        if (!matchesActiveFilter(fileRel))
            continue;
        if (!matchesSearchFilter(file.filename().string()))
            continue;

        std::string label = "📄 " + file.filename().string();
        bool selected = (m_selectedFile == file.string());

        ImGuiTreeNodeFlags flags = ImGuiTreeNodeFlags_Leaf | ImGuiTreeNodeFlags_NoTreePushOnOpen
                                 | ImGuiTreeNodeFlags_SpanFullWidth;
        if (selected)
            flags |= ImGuiTreeNodeFlags_Selected;

        ImGui::TreeNodeEx(label.c_str(), flags);

        if (ImGui::IsItemClicked() && !selected) {
            m_selectedFile = file.string();
            m_selectionChanged = true;
        }

        // Right-click context menu
        if (ImGui::BeginPopupContextItem()) {
            if (ImGui::MenuItem("Open")) {
                m_selectedFile = file.string();
                m_selectionChanged = true;
                ImGui::CloseCurrentPopup();
            }
            if (ImGui::MenuItem("Copy Path")) {
                ImGui::SetClipboardText(file.string().c_str());
                ImGui::CloseCurrentPopup();
            }
            if (ImGui::MenuItem("Open in File Manager")) {
                std::string cmd = "xdg-open \"";
                cmd += file.parent_path().string() + "\"";
                std::system(cmd.c_str());
                ImGui::CloseCurrentPopup();
            }
            ImGui::EndPopup();
        }

        const auto* schema = m_registry->findSchemaForFile(fileRel);
        if (schema) {
            ImGui::SameLine(ImGui::GetContentRegionAvail().x - 120);
            ImGui::TextColored(ImColor(140, 140, 140), "%s", schema->displayName.c_str());
        }
    }
}
