#pragma once

#include <string>
#include <memory>
#include <vector>
#include <algorithm>
#include <filesystem>
#include <yaml-cpp/yaml.h>
#include "yaml_loader.h"

struct SchemaField;
class SchemaRegistry;
class FileBrowser;
class SchemaParser;
class YamlDocument;
class FormRenderer;

struct Document {
    std::unique_ptr<YamlDocument> yamlDoc;
    std::unique_ptr<SchemaField> schema;
    std::string schemaName;
    std::string schemaTitle;
    std::string schemaPath;
    std::string rawText;
    std::string rawParseError;
    bool readOnly = false;
    bool rawMode = false;
    bool fileChangedWarn = false;
    std::filesystem::file_time_type modTime = {};
    std::vector<YAML::Node> undoStack;
    std::vector<YAML::Node> redoStack;
    // Find/Replace state (per-document)
    bool findBarOpen = false;
    char findText[256] = "";
    char replaceText[256] = "";
    std::vector<size_t> findMatches;
    int findCurrentIdx = -1;

    bool isOpen() const { return yamlDoc && yamlDoc->isOpen(); }
    const std::string& path() const { return yamlDoc ? yamlDoc->path() : emptyStr; }

    static inline const std::string emptyStr;
};

struct FindResult {
    std::string path;
    int line;
    std::string text;
};

class App {
public:
    App();
    ~App();

    bool initialize();
    void render();
    bool wantsToQuit() const { return m_wantsToQuit; }
    void requestQuit();
    void openFile(const std::string& path);

private:
    void renderMenuBar();
    void renderStatusBar();
    void renderConfirmDialog();
    void renderSaveAsDialog();
    void renderNewFileDialog();
    void renderFindInFiles();
    void renderEditorPanel();
    void renderTabBar();
    void renderRawEditor(Document& doc);
    void handleShortcuts();
    void toggleTheme();

    void saveFile();
    void closeFile();
    void closeDocument(int idx);
    void doEraseDoc(int idx);
    void saveAs(const std::string& path);
    void setStatus(const std::string& msg);

    void syncRawFromData(Document& doc);
    bool checkFileChanged(Document& doc);
    void formatAllCCode(const SchemaField& field, YAML::Node data, int& count);
    void pushUndo();
    void undo();
    void redo();

    void buildFindMatches(Document& doc);
    void replaceFindMatch(Document& doc);
    void replaceFindAll(Document& doc);
    void doFindInFiles();

    std::string findProjectRoot() const;
    void loadConfig();
    void saveConfig();

    Document* activeDoc();
    Document* activeDocOrNull();

    using FileTime = std::filesystem::file_time_type;

    enum class ConfirmAction { None, CloseFile, Quit };
    ConfirmAction m_pendingAction = ConfirmAction::None;
    std::string m_pendingFile;
    int m_pendingDocIdx = -1;

    bool m_wantsToQuit = false;
    bool m_showDemoWindow = false;
    bool m_showAbout = false;
    bool m_showUnmatched = false;
    bool m_showSaveAs = false;
    bool m_showNewFile = false;
    bool m_showSchemaInspector = false;
    bool m_showFindInFiles = false;
    bool m_darkTheme = true;
    std::string m_statusMessage;

    // Find in files state
    char m_ffQuery[256] = "";
    std::vector<FindResult> m_ffResults;
    bool m_ffCaseSensitive = false;

    std::unique_ptr<SchemaRegistry> m_schemaRegistry;
    std::unique_ptr<FileBrowser> m_fileBrowser;
    std::unique_ptr<SchemaParser> m_schemaParser;
    std::unique_ptr<FormRenderer> m_formRenderer;

    std::vector<Document> m_documents;
    int m_activeDoc = -1;

    std::string m_projectRoot;
    std::string m_schemasDir;
    std::string m_examplesDir;
    char m_saveAsPath[1024] = "";
    char m_newFilePath[1024] = "";

    std::vector<std::string> m_recentFiles;
    float m_filePanelWidth = 280.0f;
};
