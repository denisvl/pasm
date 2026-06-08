#pragma once

#include <string>
#include <vector>

struct SchemaInfo {
    std::string name;
    std::string schemaPath;
    std::string displayName;
};

class SchemaRegistry {
public:
    SchemaRegistry() = default;

    bool initialize(const std::string& schemasDir, const std::string& examplesDir);

    const SchemaInfo* findSchemaForFile(const std::string& yamlPath) const;
    const std::vector<SchemaInfo>& schemas() const { return m_schemas; }
    const std::vector<std::string>& unmatchedFiles() const { return m_unmatched; }

    const std::string& schemasDir() const { return m_schemasDir; }
    const std::string& examplesDir() const { return m_examplesDir; }

private:
    void scanExamples();
    int matchPriority(const std::string& path) const;

    std::vector<SchemaInfo> m_schemas;
    std::vector<std::string> m_unmatched;
    std::string m_schemasDir;
    std::string m_examplesDir;
};
