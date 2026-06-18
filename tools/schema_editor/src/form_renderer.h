#pragma once

#include <string>
#include <memory>
#include <unordered_map>
#include <yaml-cpp/yaml.h>

struct SchemaField;
class CCodeEditor;

class FormRenderer {
public:
    FormRenderer();
    ~FormRenderer();

    bool render(const SchemaField& schema, YAML::Node& data, bool readOnly = false);
    void expandAll() { m_expandAll = true; }
    void collapseAll() { m_collapseAll = true; }

    struct ValidationError {
        std::string path;
        std::string message;
    };
    std::vector<ValidationError> collectErrors(const SchemaField& schema, const YAML::Node& data) const;

private:
    void collectErrorsRec(const SchemaField& field, const YAML::Node& data,
                          std::vector<ValidationError>& out, const std::string& prefix) const;

private:
    void renderField(const SchemaField& field, YAML::Node& data, const std::string& label = "", float maxLabelWidth = 0.0f);
    void renderString(const SchemaField& field, YAML::Node& data);
    void renderInteger(const SchemaField& field, YAML::Node& data);
    void renderNumber(const SchemaField& field, YAML::Node& data);
    void renderBoolean(const SchemaField& field, YAML::Node& data);
    void renderEnum(const SchemaField& field, YAML::Node& data);
    void renderArray(const SchemaField& field, YAML::Node& data);
    void renderObject(const SchemaField& field, YAML::Node& data);
    void renderAdditionalProperties(const SchemaField& schema, YAML::Node& data);
    void renderOneOf(const SchemaField& field, YAML::Node& data);

    void ensureNode(YAML::Node& data, const std::string& type);
    bool renderLabel(const SchemaField& field, const std::string& label);
    std::string validate(const SchemaField& field, const YAML::Node& data) const;

    static constexpr int kPageSize = 50;

    bool m_readOnly = false;
    bool m_changed = false;
    bool m_expandAll = false;
    bool m_collapseAll = false;
    std::unique_ptr<CCodeEditor> m_ccodeEditor;
    std::unordered_map<unsigned int, int> m_arrayPages;
};
