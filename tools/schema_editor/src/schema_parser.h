#pragma once

#include <string>
#include <vector>
#include <memory>
#include <unordered_set>
#include <nlohmann/json.hpp>

struct SchemaField {
    std::string name;
    std::string type;
    bool required = false;
    std::string description;
    std::string pattern;
    double minimum = 0;
    double maximum = 0;
    int minLength = 0;
    int maxLength = 0;
    int minItems = 0;
    int maxItems = 0;
    std::vector<std::string> enumValues;
    std::shared_ptr<SchemaField> items;
    std::vector<SchemaField> properties;
    std::vector<std::vector<SchemaField>> oneOfVariants;
    bool isCCodeField = false;
    bool hasAdditionalProperties = false;
    std::shared_ptr<SchemaField> additionalPropertiesSchema;
};

class SchemaParser {
public:
    SchemaParser();

    SchemaField parseFile(const std::string& schemaPath);

    static bool isCCodeFieldName(const std::string& name);

private:
    SchemaField parseSchemaObject(const std::string& name, const nlohmann::json& obj, bool required);
    void detectCCodeFields(SchemaField& field);
    nlohmann::json resolveRef(const std::string& ref, const nlohmann::json& root) const;

    const nlohmann::json* m_rootSchema = nullptr;
};
