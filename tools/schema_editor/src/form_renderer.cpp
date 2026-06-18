#include "form_renderer.h"
#include "schema_parser.h"
#include "c_code_editor.h"

#include <imgui.h>
#include <cstring>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <regex>
#include <set>

FormRenderer::FormRenderer()
    : m_ccodeEditor(std::make_unique<CCodeEditor>()) {}

FormRenderer::~FormRenderer() = default;

bool FormRenderer::render(const SchemaField& schema, YAML::Node& data, bool readOnly) {
    m_readOnly = readOnly;
    m_changed = false;

    ImGui::PushID("Form");
    ImGui::PushStyleVar(ImGuiStyleVar_FramePadding, ImVec2(4, 3));

    if (schema.type == "object")
        renderObject(schema, data);
    else if (schema.type == "array")
        renderArray(schema, data);

    ImGui::PopStyleVar();
    ImGui::PopID();

    m_expandAll = false;
    m_collapseAll = false;

    return m_changed;
}

static bool keyExists(YAML::Node& data, const std::string& key) {
    if (!data.IsMap()) return false;
    for (auto it = data.begin(); it != data.end(); ++it) {
        if (it->first.Scalar() == key)
            return true;
    }
    return false;
}

std::string FormRenderer::validate(const SchemaField& field, const YAML::Node& data) const {
    if (!data.IsDefined() || data.IsNull())
        return {};

    if (field.type == "string" || field.type == "enum") {
        std::string val = data.Scalar();
        if (!field.pattern.empty()) {
            try {
                std::regex re(field.pattern);
                if (!std::regex_match(val, re))
                    return "Pattern: " + field.pattern;
            } catch (const std::regex_error&) {}
        }
        if (field.minLength > 0 && (int)val.size() < field.minLength)
            return "Minimum length: " + std::to_string(field.minLength);
        if (field.maxLength > 0 && (int)val.size() > field.maxLength)
            return "Maximum length: " + std::to_string(field.maxLength);
    }

    if (field.type == "integer") {
        int val = data.as<int>(0);
        if (field.minimum != 0 && val < (int)field.minimum)
            return "Minimum: " + std::to_string((int)field.minimum);
        if (field.maximum != 0 && val > (int)field.maximum)
            return "Maximum: " + std::to_string((int)field.maximum);
    }

    if (field.type == "number") {
        double val = data.as<double>(0.0);
        if (field.minimum != 0.0 && val < field.minimum)
            return "Minimum: " + std::to_string(field.minimum);
        if (field.maximum != 0.0 && val > field.maximum)
            return "Maximum: " + std::to_string(field.maximum);
    }

    return {};
}

bool FormRenderer::renderLabel(const SchemaField& field, const std::string& label) {
    bool showDescription = !field.description.empty();
    std::string dispLabel = label.empty() ? field.name : label;

    if (field.required)
        ImGui::TextColored(ImColor(200, 200, 100), "%s *", dispLabel.c_str());
    else
        ImGui::Text("%s", dispLabel.c_str());

    if (showDescription) {
        ImGui::SameLine();
        ImGui::TextDisabled("(?)");
        if (ImGui::IsItemHovered())
            ImGui::SetTooltip("%s", field.description.c_str());
        return true;
    }
    return false;
}

void FormRenderer::ensureNode(YAML::Node& data, const std::string& type) {
    if (data.IsDefined() && !data.IsNull()) return;

    if (type == "object" || type == "oneOf")
        data = YAML::Node(YAML::NodeType::Map);
    else if (type == "array")
        data = YAML::Node(YAML::NodeType::Sequence);
    else if (type == "string" || type == "enum")
        data = YAML::Node("");
    else if (type == "integer")
        data = YAML::Node(0);
    else if (type == "number")
        data = YAML::Node(0.0);
    else if (type == "boolean")
        data = YAML::Node(false);
    else
        data = YAML::Node(YAML::NodeType::Map);
}

void FormRenderer::renderField(const SchemaField& field, YAML::Node& data, const std::string& label, float maxLabelWidth) {
    ImGui::PushID(field.name.c_str());

    std::string dispLabel = label.empty() ? field.name : label;

    if (field.isCCodeField && field.type == "string") {
        renderLabel(field, dispLabel);
        std::string val = data.IsDefined() && !data.IsNull() ? data.Scalar() : "";
        if (m_ccodeEditor->render(dispLabel, val, m_readOnly)) {
            data = val;
            m_changed = true;
        }
        ImGui::PopID();
        return;
    }

    if (field.type == "oneOf") {
        renderOneOf(field, data);
        ImGui::PopID();
        return;
    }

    if (field.type == "object") {
        ImGuiTreeNodeFlags flags = ImGuiTreeNodeFlags_SpanFullWidth;
        if (field.properties.empty() && !field.hasAdditionalProperties)
            flags |= ImGuiTreeNodeFlags_Leaf;

        std::string header = dispLabel;
        if (field.required) header += " *";

        bool open = ImGui::TreeNodeEx(header.c_str(), flags);

        if (!field.description.empty() && open) {
            ImGui::SameLine();
            ImGui::TextDisabled("(?)");
            if (ImGui::IsItemHovered())
                ImGui::SetTooltip("%s", field.description.c_str());
        }

        if (open) {
            ImGui::Indent();
            renderObject(field, data);
            ImGui::Unindent();
            ImGui::TreePop();
        }
        ImGui::PopID();
        return;
    }

    if (field.type == "array") {
        renderArray(field, data);
        ImGui::PopID();
        return;
    }

    // Simple scalar field: label + widget
    bool showDesc = renderLabel(field, dispLabel);

    if (maxLabelWidth > 0.0f) {
        ImGui::SameLine();
        ImGui::SetCursorPosX(maxLabelWidth);
        ImGui::SetNextItemWidth(-1);
    } else {
        float labelWidth = ImGui::CalcTextSize(dispLabel.c_str()).x
                         + (showDesc ? ImGui::GetStyle().ItemInnerSpacing.x + ImGui::GetTextLineHeight() : 0)
                         + (field.required ? ImGui::CalcTextSize(" *").x : 0)
                         + ImGui::GetStyle().FramePadding.x * 2;
        float widgetWidth = ImGui::GetContentRegionAvail().x - labelWidth - ImGui::GetStyle().ItemSpacing.x;
        widgetWidth = std::max(widgetWidth, 120.0f);
        ImGui::SameLine();
        ImGui::SetNextItemWidth(widgetWidth);
    }

    std::string err = validate(field, data);
    if (!err.empty()) {
        ImGui::PushStyleColor(ImGuiCol_FrameBg, ImVec4(0.4f, 0.15f, 0.15f, 1.0f));
        ImGui::PushStyleColor(ImGuiCol_FrameBgHovered, ImVec4(0.5f, 0.15f, 0.15f, 1.0f));
        ImGui::PushStyleColor(ImGuiCol_FrameBgActive, ImVec4(0.5f, 0.15f, 0.15f, 1.0f));
    }

    if (field.type == "string") renderString(field, data);
    else if (field.type == "integer") renderInteger(field, data);
    else if (field.type == "number") renderNumber(field, data);
    else if (field.type == "boolean") renderBoolean(field, data);
    else if (field.type == "enum") renderEnum(field, data);

    if (!err.empty()) {
        ImGui::PopStyleColor(3);
        if (ImGui::IsItemHovered())
            ImGui::SetTooltip("Validation: %s", err.c_str());
    }

    ImGui::PopID();
}

void FormRenderer::renderObject(const SchemaField& field, YAML::Node& data) {
    ensureNode(data, "object");

    // Compute max label pixel width for aligned scalar widgets
    float maxLabelWidth = 0.0f;
    for (const auto& prop : field.properties) {
        if (prop.type == "object" || prop.type == "array" || prop.type == "oneOf")
            continue;
        if (prop.isCCodeField && prop.type == "string")
            continue;
        float w = ImGui::CalcTextSize(prop.name.c_str()).x
                + (prop.required ? ImGui::CalcTextSize(" *").x : 0)
                + (!prop.description.empty() ? ImGui::GetStyle().ItemInnerSpacing.x + ImGui::GetTextLineHeight() : 0)
                + ImGui::GetStyle().FramePadding.x * 2;
        maxLabelWidth = std::max(maxLabelWidth, w);
    }

    for (const auto& prop : field.properties) {
        std::string key = prop.name;

        bool existed = keyExists(data, key);
        if (!existed && !prop.required)
            continue;

        if (!existed && prop.required) {
            YAML::Node defaultNode;
            if (prop.type == "string")
                defaultNode = YAML::Node("");
            else if (prop.type == "integer")
                defaultNode = YAML::Node(0);
            else if (prop.type == "number")
                defaultNode = YAML::Node(0.0);
            else if (prop.type == "boolean")
                defaultNode = YAML::Node(false);
            else if (prop.type == "object" || prop.type == "oneOf")
                defaultNode = YAML::Node(YAML::NodeType::Map);
            else if (prop.type == "array")
                defaultNode = YAML::Node(YAML::NodeType::Sequence);
            data[prop.name] = defaultNode;
        }

        YAML::Node child = data[prop.name];
        renderField(prop, child, "", maxLabelWidth);
    }

    if (field.hasAdditionalProperties) {
        renderAdditionalProperties(field, data);
    } else {
        // Show unknown fields not covered by schema
        std::vector<std::string> unknownKeys;
        for (auto it = data.begin(); it != data.end(); ++it) {
            std::string key = it->first.Scalar();
            bool found = false;
            for (const auto& prop : field.properties) {
                if (prop.name == key) { found = true; break; }
            }
            if (!found) unknownKeys.push_back(key);
        }
        if (!unknownKeys.empty()) {
            ImGui::Separator();
            ImGui::TextColored(ImColor(200, 150, 50), "Contains %zu unknown field(s):", unknownKeys.size());
            ImGui::SameLine();
            ImGui::TextDisabled("(not in schema)");
            ImGui::Indent();
            for (const auto& key : unknownKeys) {
                ImGui::PushID(key.c_str());
                ImGui::Text("%s:", key.c_str());
                ImGui::SameLine();
                YAML::Node val = data[key];
                if (val.IsScalar()) {
                    std::string s = val.Scalar();
                    char buf[4096];
                    size_t n = s.copy(buf, sizeof(buf) - 1);
                    buf[n] = '\0';
                    ImGui::SetNextItemWidth(-1);
                    if (!m_readOnly) {
                        if (ImGui::InputText("##val", buf, sizeof(buf))) {
                            data[key] = std::string(buf);
                            m_changed = true;
                        }
                    } else {
                        ImGui::Text("%s", buf);
                    }
                } else {
                    ImGui::TextDisabled("%s", val.IsSequence() ? "[array]" : val.IsMap() ? "{...}" : "?");
                }
                ImGui::PopID();
            }
            ImGui::Unindent();
        }
    }

    ImGui::Unindent();
}

std::vector<FormRenderer::ValidationError> FormRenderer::collectErrors(
    const SchemaField& schema, const YAML::Node& data) const {
    std::vector<ValidationError> out;
    collectErrorsRec(schema, data, out, "");
    return out;
}

void FormRenderer::collectErrorsRec(
    const SchemaField& field, const YAML::Node& data,
    std::vector<ValidationError>& out, const std::string& prefix) const {
    if (!data.IsDefined() || data.IsNull()) return;

    std::string fullName = prefix.empty() ? field.name : prefix + "." + field.name;

    // Validate scalar fields directly
    if (field.type == "string" || field.type == "integer" || field.type == "number") {
        std::string err = validate(field, data);
        if (!err.empty())
            out.push_back({fullName, err});
    }

    if (field.type == "object" || field.type == "oneOf") {
        // Validate object fields
        for (const auto& prop : field.properties) {
            if (data[prop.name].IsDefined() && !data[prop.name].IsNull())
                collectErrorsRec(prop, data[prop.name], out, fullName);
        }
        // Unknown keys (additionalProperties) - no validation to report
    }

    if (field.type == "array" && field.items && data.IsSequence()) {
        for (size_t i = 0; i < data.size(); i++) {
            std::string itemPrefix = fullName + "[" + std::to_string(i) + "]";
            if (field.items->type == "object" || field.items->type == "oneOf") {
                for (const auto& prop : field.items->properties) {
                    if (data[i][prop.name].IsDefined() && !data[i][prop.name].IsNull())
                        collectErrorsRec(prop, data[i][prop.name], out, itemPrefix);
                }
            } else {
                std::string err = validate(*field.items, data[i]);
                if (!err.empty())
                    out.push_back({itemPrefix, err});
            }
        }
    }

    // oneOf variants
    for (const auto& variant : field.oneOfVariants) {
        for (const auto& prop : variant) {
            if (data[prop.name].IsDefined() && !data[prop.name].IsNull())
                collectErrorsRec(prop, data[prop.name], out, fullName);
        }
    }
}

void FormRenderer::renderString(const SchemaField& field, YAML::Node& data) {
    ensureNode(data, "string");

    char buf[4096];
    std::string val = data.Scalar();
    size_t len = val.copy(buf, sizeof(buf) - 1);
    buf[len] = '\0';

    if (ImGui::InputText("##val", buf, sizeof(buf))) {
        data = std::string(buf);
        m_changed = true;
    }
}

void FormRenderer::renderInteger(const SchemaField& field, YAML::Node& data) {
    ensureNode(data, "integer");

    int val = data.as<int>(0);

    if (field.minimum != 0 || field.maximum != 0) {
        int mn = (int)field.minimum;
        int mx = (int)field.maximum;
        if (ImGui::SliderInt("##val", &val, mn, mx)) {
            data = val;
            m_changed = true;
        }
    } else {
        if (ImGui::InputInt("##val", &val, 1, 10)) {
            data = val;
            m_changed = true;
        }
    }
}

void FormRenderer::renderNumber(const SchemaField& field, YAML::Node& data) {
    ensureNode(data, "number");

    float val = data.as<float>(0.0f);

    if (ImGui::InputFloat("##val", &val, 0.1f, 1.0f, "%.4f")) {
        data = (double)val;
        m_changed = true;
    }
}

void FormRenderer::renderBoolean(const SchemaField& field, YAML::Node& data) {
    ensureNode(data, "boolean");

    bool val = data.as<bool>(false);

    if (ImGui::Checkbox("##val", &val)) {
        data = val;
        m_changed = true;
    }
}

void FormRenderer::renderEnum(const SchemaField& field, YAML::Node& data) {
    if (field.enumValues.empty()) {
        renderString(field, data);
        return;
    }

    ensureNode(data, "string");

    std::string val = data.IsDefined() && !data.IsNull() ? data.Scalar() : "";
    int current = 0;
    for (int i = 0; i < (int)field.enumValues.size(); i++) {
        if (field.enumValues[i] == val) {
            current = i;
            break;
        }
    }

    if (current >= (int)field.enumValues.size())
        current = 0;

    const char* preview = field.enumValues[current].c_str();
    if (ImGui::BeginCombo("##val", preview)) {
        // Filter input
        ImGuiID filterId = ImGui::GetID("enum_filter");
        char* filterBuf = (char*)ImGui::GetStateStorage()->GetVoidPtrRef(filterId);
        static char s_filterBuf[128] = "";
        if (!filterBuf) {
            ImGui::GetStateStorage()->SetVoidPtr(filterId, s_filterBuf);
            filterBuf = s_filterBuf;
            filterBuf[0] = '\0';
        }

        ImGui::SetNextItemWidth(-1);
        ImGui::InputTextWithHint("##filter", "Filter...", filterBuf, 128);
        std::string filterStr(filterBuf);
        std::transform(filterStr.begin(), filterStr.end(), filterStr.begin(), ::tolower);

        bool matchFound = false;
        for (int i = 0; i < (int)field.enumValues.size(); i++) {
            std::string item = field.enumValues[i];
            std::string itemLower = item;
            std::transform(itemLower.begin(), itemLower.end(), itemLower.begin(), ::tolower);
            if (!filterStr.empty() && itemLower.find(filterStr) == std::string::npos)
                continue;

            bool selected = (i == current);
            if (ImGui::Selectable(item.c_str(), selected)) {
                data = item;
                m_changed = true;
                filterBuf[0] = '\0'; // Clear filter on selection
                ImGui::CloseCurrentPopup();
            }
            if (selected && filterStr.empty())
                ImGui::SetItemDefaultFocus();
            matchFound = true;
        }

        if (!matchFound)
            ImGui::TextDisabled("No matching values");

        ImGui::EndCombo();
    }
}

void FormRenderer::renderArray(const SchemaField& field, YAML::Node& data) {
    ensureNode(data, "array");

    char header[128];
    int count = (int)data.size();
    snprintf(header, sizeof(header), "%s [%d items]", field.name.c_str(), count);

    ImGuiTreeNodeFlags flags = ImGuiTreeNodeFlags_SpanFullWidth;
    if (count == 0)
        flags |= ImGuiTreeNodeFlags_Leaf;

    // Track page state for this array widget
    ImGuiID pageId = ImGui::GetID(field.name.c_str());
    int& page = m_arrayPages[pageId];
    int totalPages = (count + kPageSize - 1) / kPageSize;
    if (totalPages < 1) totalPages = 1;
    if (page >= totalPages) page = totalPages - 1;

    if (m_expandAll) ImGui::SetNextItemOpen(true);
    if (m_collapseAll) ImGui::SetNextItemOpen(false);
    bool open = ImGui::TreeNodeEx(header, flags);

    if (!field.description.empty()) {
        ImGui::SameLine();
        ImGui::TextDisabled("(?)");
        if (ImGui::IsItemHovered())
            ImGui::SetTooltip("%s", field.description.c_str());
    }

    if (open) {
        // Pagination controls (shown before item area so page count is visible)
        bool pageChanged = false;
        if (count > kPageSize) {
            ImGui::Text("Page %d of %d", page + 1, totalPages);
            ImGui::SameLine();
            if (ImGui::SmallButton("< Prev") && page > 0) { page--; pageChanged = true; }
            ImGui::SameLine();
            if (ImGui::SmallButton("Next >") && page < totalPages - 1) { page++; pageChanged = true; }
            ImGui::Separator();
        }

        if (!m_readOnly) {
            if (ImGui::Button("+ Add Item")) {
                YAML::Node newItem;
                if (field.items) {
                    if (field.items->type == "object" || field.items->type == "oneOf")
                        newItem = YAML::Node(YAML::NodeType::Map);
                    else if (field.items->type == "string" || field.items->type == "enum")
                        newItem = YAML::Node("");
                    else if (field.items->type == "integer")
                        newItem = YAML::Node(0);
                    else if (field.items->type == "number")
                        newItem = YAML::Node(0.0);
                    else if (field.items->type == "boolean")
                        newItem = YAML::Node(false);
                }
                data.push_back(newItem);
                m_changed = true;
                // Jump to last page so user sees the new item
                page = totalPages;
            }
            ImGui::SameLine();
            ImGui::TextDisabled("%s", "Add a new item to this list");
        }

        if (count > 0 && field.items) {
            if (!pageChanged && count <= kPageSize)
                ImGui::Separator();

            int removeIdx = -1;
            int moveIdx = -1;
            bool moveUp = false;

            int start = page * kPageSize;
            int end = std::min(count, start + kPageSize);

            for (int i = start; i < end; i++) {
                ImGui::PushID(i);

                char itemLabel[32];
                snprintf(itemLabel, sizeof(itemLabel), "[%d]", i);

                if (field.items->type == "object") {
                    if (m_expandAll) ImGui::SetNextItemOpen(true);
                    if (m_collapseAll) ImGui::SetNextItemOpen(false);
                    bool itemOpen = ImGui::TreeNodeEx(itemLabel,
                        ImGuiTreeNodeFlags_SpanFullWidth);

                    if (!m_readOnly) {
                        ImGui::SameLine();
                        if (i > 0 && ImGui::SmallButton("^")) {
                            moveIdx = i;
                            moveUp = true;
                        }
                        ImGui::SameLine();
                        if (i < count - 1 && ImGui::SmallButton("v")) {
                            moveIdx = i;
                            moveUp = false;
                        }
                        ImGui::SameLine();
                        if (ImGui::SmallButton("x")) {
                            removeIdx = i;
                        }
                    }

                    if (itemOpen) {
                        ImGui::Indent();
                        YAML::Node child = data[i];
                        renderObject(*field.items, child);
                        ImGui::Unindent();
                        ImGui::TreePop();
                    }
                } else {
                    bool isCCodeArr = field.items->isCCodeField && field.items->type == "string";
                    bool isPrimitive = !isCCodeArr && (field.items->type == "string" || field.items->type == "integer" ||
                                                       field.items->type == "number" || field.items->type == "boolean");

                    if (isCCodeArr) {
                        std::string val = data[i].IsDefined() && !data[i].IsNull() ? data[i].Scalar() : "";
                        if (m_ccodeEditor->render(itemLabel, val, m_readOnly)) {
                            data[i] = val;
                            m_changed = true;
                        }
                    } else if (isPrimitive) {
                        ImGui::TextDisabled("%d.", i);
                        ImGui::SameLine();
                        YAML::Node child = data[i];
                        renderField(*field.items, child, "");
                    } else {
                        YAML::Node child = data[i];
                        renderField(*field.items, child, itemLabel);
                    }

                    if (!m_readOnly) {
                        ImGui::SameLine();
                        if (i > 0 && ImGui::SmallButton("^")) {
                            moveIdx = i;
                            moveUp = true;
                        }
                        ImGui::SameLine();
                        if (i < count - 1 && ImGui::SmallButton("v")) {
                            moveIdx = i;
                            moveUp = false;
                        }
                        ImGui::SameLine();
                        if (ImGui::SmallButton("x")) {
                            removeIdx = i;
                        }
                    }
                }

                ImGui::PopID();
            }

            // Handle removal (rebuild sequence without removed item)
            if (removeIdx >= 0) {
                YAML::Node newSeq(YAML::NodeType::Sequence);
                for (int i = 0; i < count; i++) {
                    if (i != removeIdx)
                        newSeq.push_back(data[i]);
                }
                data = newSeq;
                m_changed = true;
                if (page >= totalPages && page > 0)
                    page--;
            }

            // Handle move up/down
            if (moveIdx >= 0) {
                int swap = moveUp ? moveIdx - 1 : moveIdx + 1;
                if (swap >= 0 && swap < count) {
                    YAML::Node tmp = YAML::Clone(data[moveIdx]);
                    data[moveIdx] = YAML::Clone(data[swap]);
                    data[swap] = tmp;
                    m_changed = true;
                }
            }
        }

        ImGui::TreePop();
    }
}

void FormRenderer::renderAdditionalProperties(const SchemaField& field, YAML::Node& data) {
    ensureNode(data, "object");

    ImGui::Separator();
    ImGui::Text("Additional Properties:");
    ImGui::Indent();

    std::vector<std::string> keys;
    for (auto it = data.begin(); it != data.end(); ++it)
        keys.push_back(it->first.Scalar());

    std::string removeKey;
    for (const auto& key : keys) {
        bool isNamedProp = false;
        for (const auto& prop : field.properties) {
            if (prop.name == key) {
                isNamedProp = true;
                break;
            }
        }
        if (isNamedProp) continue;

        ImGui::PushID(key.c_str());

        if (field.additionalPropertiesSchema && field.additionalPropertiesSchema->isCCodeField) {
            // Show key as label, value as C code editor
            ImGui::Text("%s:", key.c_str());
            std::string val = data[key].IsDefined() && !data[key].IsNull() ? data[key].Scalar() : "";
            if (m_ccodeEditor->render(key, val, m_readOnly)) {
                data[key] = val;
                m_changed = true;
            }
        } else {
            char keyBuf[256];
            size_t kl = key.copy(keyBuf, sizeof(keyBuf) - 1);
            keyBuf[kl] = '\0';
            ImGui::SetNextItemWidth(150.0f);
            if (ImGui::InputText("##key", keyBuf, sizeof(keyBuf))) {
                // Key renamed: copy value to new key, remove old
                std::string newKey(keyBuf);
                if (newKey != key && !newKey.empty()) {
                    data[newKey] = data[key];
                    removeKey = key;
                    m_changed = true;
                }
            }
            ImGui::SameLine();

            std::string val = data[key].IsDefined() && !data[key].IsNull() ? data[key].Scalar() : "";
            char valBuf[4096];
            size_t vl = val.copy(valBuf, sizeof(valBuf) - 1);
            valBuf[vl] = '\0';
            ImGui::SetNextItemWidth(-60.0f);
            if (ImGui::InputText("##val", valBuf, sizeof(valBuf))) {
                data[key] = std::string(valBuf);
                m_changed = true;
            }
        }

        ImGui::SameLine();
        if (!m_readOnly && ImGui::SmallButton("x")) {
            removeKey = key;
        }

        ImGui::PopID();
    }

    if (removeKey.empty() && !m_readOnly) {
        if (ImGui::Button("+ Add Key")) {
            std::string newKey = "new_key";
            int suffix = 1;
            while (data[newKey])
                newKey = "new_key_" + std::to_string(suffix++);
            data[newKey] = YAML::Node("");
            m_changed = true;
        }
    }

    if (!removeKey.empty()) {
        data.remove(removeKey);
        m_changed = true;
    }

    ImGui::Unindent();
}

void FormRenderer::renderOneOf(const SchemaField& field, YAML::Node& data) {
    ensureNode(data, "object");

    int currentVariant = 0;
    for (int i = 0; i < (int)field.oneOfVariants.size(); i++) {
        bool matches = true;
        for (const auto& prop : field.oneOfVariants[i]) {
            if (prop.required && !keyExists(data, prop.name)) {
                matches = false;
                break;
            }
        }
        if (matches) {
            currentVariant = i;
            break;
        }
    }

    int chosenVariant = currentVariant;
    std::string comboLabel = "Variant " + std::to_string(currentVariant + 1) + " of "
                             + std::to_string(field.oneOfVariants.size());
    if (ImGui::BeginCombo(field.name.c_str(), comboLabel.c_str())) {
        for (int i = 0; i < (int)field.oneOfVariants.size(); i++) {
            bool selected = (i == chosenVariant);
            std::string label = "Variant " + std::to_string(i + 1);
            if (ImGui::Selectable(label.c_str(), selected))
                chosenVariant = i;
            if (selected)
                ImGui::SetItemDefaultFocus();
        }
        ImGui::EndCombo();
    }

    if (chosenVariant != currentVariant) {
        data = YAML::Node(YAML::NodeType::Map);
        currentVariant = chosenVariant;
        m_changed = true;
    }

    if (!field.description.empty()) {
        ImGui::SameLine();
        ImGui::TextDisabled("(?)");
        if (ImGui::IsItemHovered())
            ImGui::SetTooltip("%s", field.description.c_str());
    }

    ImGui::Indent();
    for (const auto& prop : field.oneOfVariants[currentVariant]) {
        bool existed = keyExists(data, prop.name);
        if (!existed && !prop.required)
            continue;

        if (!existed && prop.required) {
            YAML::Node defaultNode;
            if (prop.type == "string" || prop.type == "enum")
                defaultNode = YAML::Node("");
            else if (prop.type == "integer")
                defaultNode = YAML::Node(0);
            else
                defaultNode = YAML::Node(YAML::NodeType::Map);
            data[prop.name] = defaultNode;
        }

        YAML::Node child = data[prop.name];
        renderField(prop, child);
    }
    ImGui::Unindent();
}
