#include "yaml_loader.h"

#include <fstream>
#include <filesystem>

namespace fs = std::filesystem;

bool YamlDocument::load(const std::string& path) {
    if (!fs::exists(path)) {
        m_lastError = "File not found: " + path;
        return false;
    }

    try {
        m_root = YAML::LoadFile(path);
        if (!m_root.IsDefined()) {
            m_root = YAML::Node(YAML::NodeType::Map);
        }
        m_path = path;
        m_dirty = false;
        m_lastError.clear();
        return true;
    }
    catch (const YAML::Exception& e) {
        m_lastError = "YAML parse error: ";
        m_lastError += e.what();
        return false;
    }
}

bool YamlDocument::save() {
    if (m_path.empty()) {
        m_lastError = "No file path set";
        return false;
    }
    return saveAs(m_path);
}

bool YamlDocument::saveAs(const std::string& path) {
    try {
        YAML::Emitter emitter;
        emitter.SetIndent(2);
        emitter.SetMapFormat(YAML::Block);
        emitter.SetSeqFormat(YAML::Block);
        emitter.SetBoolFormat(YAML::TrueFalseBool);

        emitter << m_root;

        std::ofstream fout(path);
        if (!fout.is_open()) {
            m_lastError = "Cannot write: " + path;
            return false;
        }
        fout << emitter.c_str();
        fout.close();

        m_path = path;
        m_dirty = false;
        m_lastError.clear();
        return true;
    }
    catch (const YAML::Exception& e) {
        m_lastError = "YAML write error: ";
        m_lastError += e.what();
        return false;
    }
}

std::string YamlDocument::dirPath() const {
    if (m_path.empty()) return "";
    return fs::path(m_path).parent_path().string();
}

void YamlDocument::close() {
    m_root = YAML::Node();
    m_path.clear();
    m_dirty = false;
    m_lastError.clear();
}
