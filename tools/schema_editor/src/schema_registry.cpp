#include "schema_registry.h"

#include <filesystem>
#include <fstream>
#include <algorithm>
#include <iostream>

namespace fs = std::filesystem;

bool SchemaRegistry::initialize(const std::string& schemasDir, const std::string& examplesDir) {
    m_schemasDir = schemasDir;
    m_examplesDir = examplesDir;

    if (!fs::exists(m_schemasDir) || !fs::exists(m_examplesDir))
        return false;

    m_schemas.clear();

    auto addSchema = [&](const std::string& name, const std::string& displayName) {
        std::string path = m_schemasDir + "/" + name;
        if (fs::exists(path)) {
            m_schemas.push_back({name, path, displayName});
        }
    };

    addSchema("processor_schema.json", "Processors");
    addSchema("system_schema.json", "Systems");
    addSchema("ic_schema.json", "ICs");
    addSchema("device_schema.json", "Devices");
    addSchema("host_schema.json", "Hosts");
    addSchema("cartridge_schema.json", "Cartridges");
    addSchema("runtime_keyboard_map_schema.json", "Keyboards");
    addSchema("runtime_controller_map_schema.json", "Controllers");
    addSchema("keyboard-keymapper.schema.json", "Key Mappers");
    addSchema("controller-mapper.schema.json", "Ctrl Mappers");

    scanExamples();
    return !m_schemas.empty();
}

void SchemaRegistry::scanExamples() {
    m_unmatched.clear();

    if (!fs::exists(m_examplesDir))
        return;

    for (auto& entry : fs::recursive_directory_iterator(m_examplesDir)) {
        if (!entry.is_regular_file())
            continue;
        auto path = entry.path();
        if (path.extension() != ".yaml")
            continue;

        std::string relPath = fs::relative(path, fs::path(m_examplesDir).parent_path()).string();
        if (findSchemaForFile(relPath) == nullptr) {
            m_unmatched.push_back(relPath);
        }
    }
}

const SchemaInfo* SchemaRegistry::findSchemaForFile(const std::string& yamlPath) const {
    struct Match {
        int index;
        int priority;
    };
    Match best = {-1, -1};

    std::string lower = yamlPath;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

    for (int i = 0; i < (int)m_schemas.size(); i++) {
        int prio = -1;

        if (m_schemas[i].displayName == "Processors") {
            if (lower.find("/processors/") != std::string::npos)
                prio = 100;
        }
        else if (m_schemas[i].displayName == "Systems") {
            if (lower.find("/systems/") != std::string::npos)
                prio = 100;
        }
        else if (m_schemas[i].displayName == "ICs") {
            if (lower.find("/ics/") != std::string::npos)
                prio = 100;
        }
        else if (m_schemas[i].displayName == "Devices") {
            if (lower.find("/devices/") != std::string::npos)
                prio = 100;
        }
        else if (m_schemas[i].displayName == "Cartridges") {
            if (lower.find("/cartridges/") != std::string::npos)
                prio = 100;
        }
        else if (m_schemas[i].displayName == "Ctrl Mappers") {
            if (lower.find("_controller_mapper") != std::string::npos)
                prio = 200;
        }
        else if (m_schemas[i].displayName == "Controllers") {
            if (lower.find("host_controller_") != std::string::npos)
                prio = 150;
        }
        else if (m_schemas[i].displayName == "Key Mappers") {
            if (lower.find("_keyboard_mapper") != std::string::npos ||
                lower.find("_console_mapper") != std::string::npos)
                prio = 200;
        }
        else if (m_schemas[i].displayName == "Keyboards") {
            if (lower.find("host_keyboard") != std::string::npos ||
                lower.find("host_console_") != std::string::npos)
                prio = 150;
        }
        else if (m_schemas[i].displayName == "Hosts") {
            if (lower.find("/hosts/") != std::string::npos)
                prio = 50;
        }

        if (prio > best.priority) {
            best = {i, prio};
        }
    }

    if (best.index >= 0)
        return &m_schemas[best.index];
    return nullptr;
}
