#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#include <filesystem>
#include <iostream>
#include <fstream>
#include <functional>

#include "schema_registry.h"
#include "schema_parser.h"
#include "yaml_loader.h"

namespace fs = std::filesystem;

struct TestResult {
    std::string name;
    bool passed;
    std::string detail;
};

static int s_testsRun = 0;
static int s_testsPassed = 0;
static std::vector<std::string> s_failures;

static void CHECK(const std::string& name, bool cond, const std::string& detail = "") {
    s_testsRun++;
    if (cond) {
        s_testsPassed++;
        std::cout << "  PASS  " << name << std::endl;
    } else {
        std::cout << "  FAIL  " << name;
        if (!detail.empty()) std::cout << " — " << detail;
        std::cout << std::endl;
        s_failures.push_back(name);
    }
}

int main() {
    std::string cwd = fs::current_path().string();
    std::string schemasDir = cwd + "/schemas";
    std::string examplesDir = cwd + "/examples";

    // --- Test 1: Schema Registry finds all 10 schemas ---
    {
        std::cout << "\n=== Schema Registry ===\n";
        SchemaRegistry reg;
        bool init = reg.initialize(schemasDir, examplesDir);
        CHECK("registry initializes", init, schemasDir + " not found");
        if (!init) return 1;

        CHECK("schemas loaded", reg.schemas().size() == 10,
              "got " + std::to_string(reg.schemas().size()) + " expected 10");
    }

    // --- Test 2: All YAML files matched ---
    {
        std::cout << "\n=== Schema Matching ===\n";
        SchemaRegistry reg;
        reg.initialize(schemasDir, examplesDir);
        auto& unmatched = reg.unmatchedFiles();
        CHECK("all YAML files matched", unmatched.empty(),
              std::to_string(unmatched.size()) + " unmatched");
        if (!unmatched.empty()) {
            for (auto& f : unmatched)
                std::cout << "    UNMATCHED: " << f << std::endl;
        }
    }

    // --- Test 3: Schema parsing ---
    {
        std::cout << "\n=== Schema Parsing ===\n";
        SchemaRegistry reg;
        reg.initialize(schemasDir, examplesDir);
        SchemaParser parser;

        for (auto& info : reg.schemas()) {
            if (info.schemaPath.empty()) continue;

            SchemaField field = parser.parseFile(info.schemaPath);
            CHECK("parse " + info.name, !field.properties.empty(),
                  info.schemaPath);

            // Check C code detection
            int ccodeCount = 0;
            std::function<void(const SchemaField&)> countCCode = [&](const SchemaField& f) {
                if (f.isCCodeField) ccodeCount++;
                for (auto& p : f.properties) countCCode(p);
                if (f.items) countCCode(*f.items);
                for (auto& v : f.oneOfVariants)
                    for (auto& p : v) countCCode(p);
            };
            countCCode(field);
            std::cout << "    " << info.name << ": " << field.properties.size()
                      << " properties, " << ccodeCount << " C code fields\n";
        }
    }

    // --- Test 4: YAML round-trip ---
    {
        std::cout << "\n=== YAML Roundtrip ===\n";

        SchemaRegistry reg;
        reg.initialize(schemasDir, examplesDir);

        std::string tmpDir = "/tmp/opencode/roundtrip/";
        fs::create_directories(tmpDir);

        std::vector<std::string> yamlFiles;
        for (auto& entry : fs::recursive_directory_iterator(examplesDir)) {
            if (entry.path().extension() == ".yaml")
                yamlFiles.push_back(entry.path().string());
        }

        int loaded = 0, saved = 0;
        for (auto& path : yamlFiles) {
            YamlDocument doc;
            if (!doc.load(path)) {
                CHECK("load " + fs::path(path).filename().string(),
                      false, doc.lastError());
                continue;
            }
            loaded++;

            std::string tmpPath = tmpDir + fs::path(path).filename().string();
            if (!doc.saveAs(tmpPath)) {
                CHECK("save " + fs::path(path).filename().string(),
                      false, doc.lastError());
                continue;
            }

            // Re-load the saved file to verify it's valid YAML
            YamlDocument verify;
            if (!verify.load(tmpPath)) {
                CHECK("verify " + fs::path(path).filename().string(),
                      false, verify.lastError());
                continue;
            }
            saved++;
        }

        fs::remove_all(tmpDir);

        CHECK("YAML files loaded", loaded > 0,
              "found " + std::to_string(yamlFiles.size()) + " .yaml files");
        CHECK("all YAML roundtrip OK", loaded == saved,
              std::to_string(loaded) + " loaded, " + std::to_string(saved) + " roundtripped");
        std::cout << "    " << yamlFiles.size() << " files found, "
                  << loaded << " loaded, " << saved << " verified OK\n";
    }

    // --- Test 5: Schema info consistency ---
    {
        std::cout << "\n=== Schema Info ===\n";
        SchemaRegistry reg;
        reg.initialize(schemasDir, examplesDir);

        for (auto& info : reg.schemas()) {
            CHECK("schema " + info.name + " has display name",
                  !info.displayName.empty());
            CHECK("schema " + info.name + " has schema path",
                  !info.schemaPath.empty());
        }
    }

    // --- Summary ---
    std::cout << "\n=== Results ===\n"
              << s_testsPassed << "/" << s_testsRun << " tests passed\n";

    if (!s_failures.empty()) {
        std::cout << "\nFailures:\n";
        for (auto& f : s_failures)
            std::cout << "  FAIL  " << f << "\n";
    }

    return s_failures.empty() ? 0 : 1;
}
