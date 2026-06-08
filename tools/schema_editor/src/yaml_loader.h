#pragma once

#include <string>
#include <yaml-cpp/yaml.h>

class YamlDocument {
public:
    YamlDocument() = default;

    bool load(const std::string& path);
    bool save();
    bool saveAs(const std::string& path);

    YAML::Node& root() { return m_root; }
    const YAML::Node& root() const { return m_root; }
    const std::string& path() const { return m_path; }
    std::string dirPath() const;

    bool isOpen() const { return !m_path.empty(); }
    bool isDirty() const { return m_dirty; }
    void markDirty() { m_dirty = true; }
    void clearDirty() { m_dirty = false; }
    void close();

    std::string lastError() const { return m_lastError; }

private:
    YAML::Node m_root;
    std::string m_path;
    bool m_dirty = false;
    std::string m_lastError;
};
