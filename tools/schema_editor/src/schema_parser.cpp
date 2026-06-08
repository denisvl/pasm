#include "schema_parser.h"

#include <fstream>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

SchemaParser::SchemaParser() = default;

static const std::unordered_set<std::string> s_ccodeNames = {
    "behavior", "snippets", "callback_handlers", "handler_bodies",
    "api_declarations", "api_impl", "reset", "reset_post",
    "initial", "args", "returns"
};

bool SchemaParser::isCCodeFieldName(const std::string& name) {
    return s_ccodeNames.find(name) != s_ccodeNames.end();
}

void SchemaParser::detectCCodeFields(SchemaField& field) {
    if (isCCodeFieldName(field.name)) {
        field.isCCodeField = true;
    }
    if (field.hasAdditionalProperties &&
        field.additionalPropertiesSchema &&
        field.additionalPropertiesSchema->type == "string") {
        field.additionalPropertiesSchema->isCCodeField =
            isCCodeFieldName(field.name);
    }
    for (auto& prop : field.properties) {
        detectCCodeFields(prop);
    }
    if (field.items) {
        detectCCodeFields(*field.items);
    }
    for (auto& variant : field.oneOfVariants) {
        for (auto& prop : variant) {
            detectCCodeFields(prop);
        }
    }
}

json SchemaParser::resolveRef(const std::string& ref, const json& root) const {
    if (ref.empty() || ref.compare(0, 2, "#/") != 0)
        return nullptr;

    std::string path = ref.substr(2);
    std::stringstream ss(path);
    std::string segment;
    json current = root;

    while (std::getline(ss, segment, '/')) {
        if (current.contains(segment))
            current = current[segment];
        else
            return nullptr;
    }
    return current;
}

SchemaField SchemaParser::parseFile(const std::string& schemaPath) {
    std::ifstream file(schemaPath);
    if (!file.is_open())
        return {};

    json schema;
    file >> schema;
    m_rootSchema = &schema;

    SchemaField root;
    root.name = "root";
    root.type = "object";

    std::vector<std::string> requiredProps;
    if (schema.contains("required"))
        requiredProps = schema["required"].get<std::vector<std::string>>();

    if (schema.contains("properties")) {
        for (auto it = schema["properties"].begin(); it != schema["properties"].end(); ++it) {
            bool req = std::find(requiredProps.begin(), requiredProps.end(), it.key()) != requiredProps.end();
            root.properties.push_back(parseSchemaObject(it.key(), it.value(), req));
        }
    }

    if (schema.contains("additionalProperties") && schema["additionalProperties"].is_object()) {
        root.hasAdditionalProperties = true;
        root.additionalPropertiesSchema = std::make_shared<SchemaField>(
            parseSchemaObject("additional", schema["additionalProperties"], false));
    }

    for (auto& prop : root.properties)
        detectCCodeFields(prop);

    m_rootSchema = nullptr;
    return root;
}

SchemaField SchemaParser::parseSchemaObject(const std::string& name, const json& obj, bool required) {
    SchemaField field;
    field.name = name;
    field.required = required;

    if (obj.contains("$ref")) {
        if (m_rootSchema) {
            auto resolved = resolveRef(obj["$ref"], *m_rootSchema);
            if (!resolved.is_null())
                return parseSchemaObject(name, resolved, required);
        }
        field.type = "string";
        return field;
    }

    if (obj.contains("oneOf") && obj["oneOf"].is_array()) {
        field.type = "oneOf";
        for (const auto& variant : obj["oneOf"]) {
            std::vector<SchemaField> variantFields;

            if (variant.contains("required") && variant["required"].is_array()) {
                for (const auto& req : variant["required"]) {
                    SchemaField f;
                    f.name = req.get<std::string>();
                    f.type = "string";
                    f.required = true;
                    variantFields.push_back(std::move(f));
                }
            }

            if (variant.contains("properties")) {
                std::vector<std::string> vreq;
                if (variant.contains("required"))
                    vreq = variant["required"].get<std::vector<std::string>>();

                for (auto it = variant["properties"].begin(); it != variant["properties"].end(); ++it) {
                    bool r = std::find(vreq.begin(), vreq.end(), it.key()) != vreq.end();
                    variantFields.push_back(parseSchemaObject(it.key(), it.value(), r));
                }
            }

            field.oneOfVariants.push_back(std::move(variantFields));
        }
        return field;
    }

    if (obj.contains("type")) {
        std::string type = obj["type"];
        field.type = type;

        if (type == "string") {
            if (obj.contains("enum")) {
                field.type = "enum";
                for (const auto& e : obj["enum"])
                    field.enumValues.push_back(e.is_string() ? e.get<std::string>() : e.dump());
            }
            if (obj.contains("pattern")) field.pattern = obj["pattern"];
            if (obj.contains("minLength")) field.minLength = obj["minLength"];
            if (obj.contains("maxLength")) field.maxLength = obj["maxLength"];
        }
        else if (type == "integer") {
            if (obj.contains("minimum")) field.minimum = obj["minimum"];
            if (obj.contains("maximum")) field.maximum = obj["maximum"];
        }
        else if (type == "number") {
            if (obj.contains("minimum")) field.minimum = obj["minimum"];
            if (obj.contains("maximum")) field.maximum = obj["maximum"];
        }
        else if (type == "array") {
            if (obj.contains("items")) {
                field.items = std::make_shared<SchemaField>(
                    parseSchemaObject("item", obj["items"], false));
            }
            if (obj.contains("minItems")) field.minItems = obj["minItems"];
            if (obj.contains("maxItems")) field.maxItems = obj["maxItems"];
        }
        else if (type == "object") {
            std::vector<std::string> reqProps;
            if (obj.contains("required"))
                reqProps = obj["required"].get<std::vector<std::string>>();

            if (obj.contains("properties")) {
                for (auto it = obj["properties"].begin(); it != obj["properties"].end(); ++it) {
                    bool r = std::find(reqProps.begin(), reqProps.end(), it.key()) != reqProps.end();
                    field.properties.push_back(parseSchemaObject(it.key(), it.value(), r));
                }
            }

            if (obj.contains("additionalProperties") && obj["additionalProperties"].is_object()) {
                field.hasAdditionalProperties = true;
                field.additionalPropertiesSchema = std::make_shared<SchemaField>(
                    parseSchemaObject("additional", obj["additionalProperties"], false));
            }
        }
    }

    if (obj.contains("description")) field.description = obj["description"];

    return field;
}
