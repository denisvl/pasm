#include "c_code_editor.h"

#include <imgui.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <algorithm>

#ifdef _WIN32
#include <io.h>
#else
#include <unistd.h>
#endif

namespace fs = std::filesystem;

CCodeEditor::CCodeEditor() {
    m_buffer.resize(65536);
}

CCodeEditor::~CCodeEditor() = default;

bool CCodeEditor::checkClangFormat() {
    m_checkedFormat = true;

#ifdef _WIN32
    FILE* pipe = _popen("where clang-format 2>nul", "r");
#else
    FILE* pipe = popen("which clang-format 2>/dev/null", "r");
#endif

    if (!pipe) return false;
    char buf[256];
    m_clangFormatFound = (fgets(buf, sizeof(buf), pipe) != nullptr);
    pclose(pipe);
    return m_clangFormatFound;
}

bool CCodeEditor::runClangFormat(const std::string& input, std::string& output) {
    auto tmpDir = fs::temp_directory_path();
    auto tmpPath = tmpDir / "pasm_format_XXXXXX";

    std::string tmpStr = tmpPath.string();

#ifdef _WIN32
    if (_mktemp_s(&tmpStr[0], tmpStr.size() + 1) != 0) return false;
    tmpStr += ".c";
#else
    tmpStr += "XXXXXX";
    std::vector<char> tmpBuf(tmpStr.begin(), tmpStr.end());
    tmpBuf.push_back('\0');
    int fd = mkstemp(tmpBuf.data());
    if (fd == -1) return false;
    close(fd);
    tmpStr = tmpBuf.data();
    tmpStr += ".c";
    std::rename(tmpBuf.data(), tmpStr.c_str());
#endif

    FILE* f = fopen(tmpStr.c_str(), "w");
    if (!f) return false;
    fwrite(input.data(), 1, input.size(), f);
    fclose(f);

    std::string cmd = "clang-format --style=\"{BasedOnStyle: LLVM, IndentWidth: 4, ColumnLimit: 100}\" \"";
    cmd += tmpStr + "\"";

    FILE* pipe = popen(cmd.c_str(), "r");
    if (!pipe) {
        fs::remove(tmpStr);
        return false;
    }

    char buf[4096];
    output.clear();
    while (fgets(buf, sizeof(buf), pipe))
        output += buf;

    int status = pclose(pipe);
    fs::remove(tmpStr);

    return status == 0 && !output.empty();
}

bool CCodeEditor::FormatCCode(const std::string& input, std::string& output) {
    CCodeEditor tmp;
    return tmp.runClangFormat(input, output);
}

bool CCodeEditor::render(const std::string& label, std::string& code, bool readOnly) {
    if (!m_checkedFormat)
        checkClangFormat();

    bool changed = false;

    size_t needed = code.size() + 512;
    if (m_buffer.size() < needed)
        m_buffer.resize(needed);

    memcpy(m_buffer.data(), code.data(), code.size());
    m_buffer[code.size()] = '\0';

    ImGui::PushID(label.c_str());

    // Calculate line numbers
    int lineCount = 1;
    for (size_t i = 0; i < code.size(); i++) {
        if (code[i] == '\n') lineCount++;
    }
    int lineDigits = 1;
    for (int n = lineCount; n >= 10; n /= 10) lineDigits++;

    ImGuiInputTextFlags flags = ImGuiInputTextFlags_AllowTabInput;
    if (readOnly)
        flags |= ImGuiInputTextFlags_ReadOnly;

    // Side-by-side layout: line numbers + editor
    float lineNumWidth = ImGui::GetTextLineHeight() * (lineDigits + 1);
    float totalHeight = std::max(80.0f, m_editorHeight);

    // Line numbers (left)
    ImGui::BeginChild("##lines", ImVec2(lineNumWidth, totalHeight), false);
    ImGui::SetScrollY(m_lastScrollY);
    ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(0.5f, 0.5f, 0.5f, 1));
    for (int i = 1; i <= lineCount; i++) {
        ImGui::Text("%*d", lineDigits, i);
    }
    ImGui::PopStyleColor();
    ImGui::EndChild();

    ImGui::SameLine();

    // Editor (right)
    ImGui::BeginChild("##editor", ImVec2(-FLT_MIN, totalHeight), false);
    if (ImGui::InputTextMultiline("##code", m_buffer.data(), m_buffer.size(),
                                  ImVec2(-FLT_MIN, -FLT_MIN), flags)) {
        code = std::string(m_buffer.data());
        changed = true;
    }
    m_lastScrollY = ImGui::GetScrollY();
    ImGui::EndChild();

    // Resize handle
    ImVec2 itemMin = ImGui::GetItemRectMin();
    ImGui::SetCursorScreenPos(ImVec2(itemMin.x, itemMin.y + totalHeight));
    ImGui::InvisibleButton("##resize", ImVec2(-1, 6));
    if (ImGui::IsItemActive() && ImGui::IsMouseDragging(0, 0)) {
        m_editorHeight += ImGui::GetIO().MouseDelta.y;
        m_editorHeight = std::max(60.0f, m_editorHeight);
    }
    if (ImGui::IsItemHovered())
        ImGui::SetMouseCursor(ImGuiMouseCursor_ResizeNS);

    // Footer: line count + Prettify
    ImGui::TextDisabled("%d line(s)", lineCount);

    if (!readOnly && m_clangFormatFound) {
        ImGui::SameLine();
        if (ImGui::Button("Prettify")) {
            std::string formatted;
            if (runClangFormat(code, formatted)) {
                code = formatted;
                changed = true;
            } else {
                ImGui::OpenPopup("FormatError");
            }
        }
        ImGui::SameLine();
        ImGui::TextDisabled("(clang-format)");
    } else if (!readOnly && m_checkedFormat && !m_clangFormatFound) {
        ImGui::SameLine();
        ImGui::TextColored(ImColor(180, 180, 60), "clang-format not found");
        if (ImGui::IsItemHovered())
            ImGui::SetTooltip("Install clang-format to enable C code prettification");
    }

    if (ImGui::BeginPopup("FormatError")) {
        ImGui::Text("clang-format failed. Check syntax.");
        ImGui::EndPopup();
    }

    ImGui::PopID();
    return changed;
}
