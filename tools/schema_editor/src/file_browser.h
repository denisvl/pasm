#pragma once

#include <string>
#include <vector>
#include <set>

class SchemaRegistry;

class FileBrowser {
public:
    FileBrowser() = default;

    void initialize(SchemaRegistry* registry);
    void render();

    std::string selectedFile() const { return m_selectedFile; }
    bool hasSelectionChanged() const { return m_selectionChanged; }
    void clearSelectionChanged() { m_selectionChanged = false; }

    void setOpenDirs(const std::vector<std::string>& dirs);
    std::vector<std::string> getOpenDirs() const;

private:
    void renderFilterTabs();
    void renderTree();
    void renderDirectory(const std::string& dirPath, const std::string& relPath);
    bool matchesActiveFilter(const std::string& relPath) const;
    bool matchesSearchFilter(const std::string& filename) const;

    SchemaRegistry* m_registry = nullptr;
    std::vector<std::string> m_filterLabels;
    std::vector<int> m_filterSchemaIndices;
    std::string m_selectedFile;
    bool m_selectionChanged = false;
    int m_activeFilter = 0;
    char m_searchFilter[128] = "";
    std::set<std::string> m_openDirs;
};
