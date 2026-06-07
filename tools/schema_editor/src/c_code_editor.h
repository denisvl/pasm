#pragma once

#include <string>
#include <vector>

class CCodeEditor {
public:
    CCodeEditor();
    ~CCodeEditor();

    bool render(const std::string& label, std::string& code, bool readOnly = false);
    bool isClangFormatAvailable() const { return m_clangFormatFound; }
    static bool FormatCCode(const std::string& input, std::string& output);

private:
    bool checkClangFormat();
    bool runClangFormat(const std::string& input, std::string& output);

    bool m_clangFormatFound = false;
    bool m_checkedFormat = false;
    float m_editorHeight = 200.0f;
    float m_lastScrollY = 0.0f;
    std::vector<char> m_buffer;
};
