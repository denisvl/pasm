use std::collections::BTreeSet;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

const ENV_VARS: &[&str] = &[
    "PASM_EMU_DIR",
    "PASM_EMU_BUILD_DIR",
    "PASM_EMU_MANIFEST",
    "PASM_EMU_EXTRA_LIBS",
    "PASM_EMU_EXTRA_LIB_DIRS",
    "VCPKG_ROOT",
    "VCPKG_TARGET_TRIPLET",
    "VCPKG_DEFAULT_TRIPLET",
];

fn extract_json_string(text: &str, key: &str) -> Option<String> {
    let needle = format!("\"{key}\"");
    let start = text.find(&needle)?;
    let rest = &text[start + needle.len()..];
    let colon = rest.find(':')?;
    let rest = &rest[colon + 1..];
    let first_quote = rest.find('"')?;
    let rest = &rest[first_quote + 1..];

    let mut value = String::new();
    let mut escaped = false;

    for ch in rest.chars() {
        if escaped {
            value.push(match ch {
                '"' => '"',
                '\\' => '\\',
                '/' => '/',
                'b' => '\u{0008}',
                'f' => '\u{000c}',
                'n' => '\n',
                'r' => '\r',
                't' => '\t',
                other => other,
            });
            escaped = false;
            continue;
        }

        match ch {
            '\\' => escaped = true,
            '"' => return Some(value),
            other => value.push(other),
        }
    }

    None
}

/// A single subsystem entry from `debugger_link.json`.
struct SubsystemEntry {
    cmake_subdir: String,
    system_target: String,
    cpu_core_target: String,
}

/// Extract the `subsystems` array from the manifest, returning the fields
/// needed to locate and link each subsystem's static libraries.
fn extract_subsystems(text: &str) -> Vec<SubsystemEntry> {
    let needle = "\"subsystems\"";
    let Some(start) = text.find(needle) else {
        return Vec::new();
    };

    let rest = &text[start + needle.len()..];
    let Some(colon) = rest.find(':') else {
        return Vec::new();
    };
    let rest = &rest[colon + 1..];
    let Some(open) = rest.find('[') else {
        return Vec::new();
    };

    let mut out = Vec::new();
    let mut depth = 0i32;
    let mut object_start = None;

    for (i, ch) in rest[open..].char_indices() {
        match ch {
            '{' => {
                if depth == 0 {
                    object_start = Some(i);
                }
                depth += 1;
            }
            '}' => {
                depth -= 1;
                if depth == 0 {
                    if let Some(start_idx) = object_start {
                        let object = &rest[open + start_idx..=open + i];
                        let cmake_subdir =
                            extract_json_string(object, "cmake_subdir").unwrap_or_default();
                        let system_target =
                            extract_json_string(object, "system_target").unwrap_or_default();
                        let cpu_core_target =
                            extract_json_string(object, "cpu_core_target").unwrap_or_default();

                        if !system_target.is_empty() {
                            out.push(SubsystemEntry {
                                cmake_subdir,
                                system_target,
                                cpu_core_target,
                            });
                        }
                    }
                    object_start = None;
                }
            }
            ']' if depth == 0 => break,
            _ => {}
        }
    }

    out
}

/// Construct the platform-appropriate static library file name from a CMake
/// target name (e.g. `c64_1541_subsystem_mos6502_cpu_core` →
/// `c64_1541_subsystem_mos6502_cpu_core.lib` on MSVC or
/// `libc64_1541_subsystem_mos6502_cpu_core.a` on Unix).
fn target_library_filename(target: &str) -> String {
    #[cfg(target_env = "msvc")]
    {
        format!("{target}.lib")
    }

    #[cfg(not(target_env = "msvc"))]
    {
        format!("lib{target}.a")
    }
}

fn extract_json_array_strings(text: &str, key: &str) -> Vec<String> {
    let needle = format!("\"{key}\"");
    let Some(start) = text.find(&needle) else {
        return Vec::new();
    };

    let rest = &text[start + needle.len()..];
    let Some(colon) = rest.find(':') else {
        return Vec::new();
    };

    let rest = &rest[colon + 1..];
    let Some(open) = rest.find('[') else {
        return Vec::new();
    };

    let mut out = Vec::new();
    let mut current = String::new();
    let mut in_string = false;
    let mut escaped = false;

    for ch in rest[open + 1..].chars() {
        if in_string {
            if escaped {
                current.push(match ch {
                    '"' => '"',
                    '\\' => '\\',
                    '/' => '/',
                    'b' => '\u{0008}',
                    'f' => '\u{000c}',
                    'n' => '\n',
                    'r' => '\r',
                    't' => '\t',
                    other => other,
                });
                escaped = false;
                continue;
            }

            match ch {
                '\\' => escaped = true,
                '"' => {
                    in_string = false;
                    out.push(std::mem::take(&mut current));
                }
                other => current.push(other),
            }

            continue;
        }

        match ch {
            '"' => in_string = true,
            ']' => break,
            _ => {}
        }
    }

    out
}

fn extract_json_array_objects(text: &str, key: &str) -> Vec<String> {
    let needle = format!("\"{key}\"");
    let Some(start) = text.find(&needle) else {
        return Vec::new();
    };

    let rest = &text[start + needle.len()..];
    let Some(colon) = rest.find(':') else {
        return Vec::new();
    };

    let rest = &rest[colon + 1..];
    let Some(open) = rest.find('[') else {
        return Vec::new();
    };

    let mut out = Vec::new();
    let mut current = String::new();
    let mut in_string = false;
    let mut escaped = false;
    let mut depth = 0usize;

    for ch in rest[open + 1..].chars() {
        if in_string {
            if depth > 0 {
                current.push(ch);
            }
            if escaped {
                escaped = false;
                continue;
            }
            match ch {
                '\\' => escaped = true,
                '"' => in_string = false,
                _ => {}
            }
            continue;
        }

        match ch {
            '"' => {
                if depth > 0 {
                    current.push(ch);
                }
                in_string = true;
            }
            '{' => {
                depth += 1;
                current.push(ch);
            }
            '}' => {
                if depth > 0 {
                    current.push(ch);
                    depth -= 1;
                    if depth == 0 {
                        out.push(std::mem::take(&mut current));
                    }
                }
            }
            ']' if depth == 0 => break,
            _ => {
                if depth > 0 {
                    current.push(ch);
                }
            }
        }
    }

    out
}

fn workspace_root_from_manifest_dir() -> Option<PathBuf> {
    let manifest_dir = env::var_os("CARGO_MANIFEST_DIR").map(PathBuf::from)?;
    manifest_dir
        .parent()
        .and_then(Path::parent)
        .map(Path::to_path_buf)
}

fn resolve_input_path(raw: &str) -> PathBuf {
    let path = PathBuf::from(raw);

    if path.is_absolute() {
        path
    } else if let Some(root) = workspace_root_from_manifest_dir() {
        root.join(path)
    } else {
        path
    }
}

fn normalize_existing_path(path: PathBuf) -> PathBuf {
    fs::canonicalize(&path).unwrap_or(path)
}

fn push_unique_existing(dirs: &mut Vec<PathBuf>, path: PathBuf) {
    if !path.exists() {
        return;
    }

    let path = normalize_existing_path(path);
    if !dirs.iter().any(|existing| existing == &path) {
        dirs.push(path);
    }
}

fn add_build_dirs(dirs: &mut Vec<PathBuf>, base: &Path) {
    /*
     * Prefer the configuration-specific directory first on multi-config
     * generators such as Visual Studio.
     */
    push_unique_existing(dirs, base.join("Release"));
    push_unique_existing(dirs, base.join("RelWithDebInfo"));
    push_unique_existing(dirs, base.join("MinSizeRel"));
    push_unique_existing(dirs, base.join("Debug"));
    push_unique_existing(dirs, base.to_path_buf());
}

fn selected_manifest_path(emu_dir: Option<&Path>) -> PathBuf {
    if let Ok(raw) = env::var("PASM_EMU_MANIFEST") {
        return resolve_input_path(&raw);
    }

    if let Some(dir) = emu_dir {
        return dir.join("debugger_link.json");
    }

    panic!(
        "PASM_EMU_MANIFEST or PASM_EMU_DIR must be set for a linked-emulator build.\n\
         Refusing to scan other generated systems because that could link the wrong emulator."
    );
}

fn selected_search_dirs(emu_dir: Option<&Path>, build_dir: Option<&Path>) -> Vec<PathBuf> {
    let mut dirs = Vec::new();

    /*
     * PASM_EMU_BUILD_DIR is the most authoritative value. In the batch script
     * it normally points directly to build\\Release on Visual Studio builds.
     */
    if let Some(dir) = build_dir {
        add_build_dirs(&mut dirs, dir);
    }

    if let Some(dir) = emu_dir {
        add_build_dirs(&mut dirs, &dir.join("build"));
        push_unique_existing(&mut dirs, dir.to_path_buf());
    }

    if dirs.is_empty() {
        panic!(
            "No generated emulator build directories exist.\n\
             PASM_EMU_DIR={:?}\n\
             PASM_EMU_BUILD_DIR={:?}\n\
             Build the selected emulator with CMake before invoking Cargo.",
            emu_dir,
            build_dir
        );
    }

    dirs
}

fn static_library_name(file_name: &str) -> Option<String> {
    #[cfg(target_env = "msvc")]
    {
        file_name
            .strip_suffix(".lib")
            .map(|base| base.to_string())
    }

    #[cfg(not(target_env = "msvc"))]
    {
        file_name
            .strip_prefix("lib")
            .and_then(|name| name.strip_suffix(".a"))
            .map(|base| base.to_string())
    }
}

fn find_library(search_dirs: &[PathBuf], file_name: &str) -> Option<PathBuf> {
    search_dirs
        .iter()
        .map(|dir| dir.join(file_name))
        .find(|path| path.is_file())
        .map(normalize_existing_path)
}

fn emit_required_split_libraries(search_dirs: &[PathBuf], manifest_text: &str) {
    let system_file = extract_json_string(manifest_text, "system_static")
        .unwrap_or_else(|| panic!("debugger_link.json is missing split_artifacts.system_static"));

    let cpu_file = extract_json_string(manifest_text, "cpu_core_static")
        .unwrap_or_else(|| panic!("debugger_link.json is missing split_artifacts.cpu_core_static"));

    let system_path = find_library(search_dirs, &system_file).unwrap_or_else(|| {
        panic!(
            "Unable to find selected system library `{system_file}`.\nSearch directories:\n{}",
            format_search_dirs(search_dirs)
        )
    });

    let cpu_path = find_library(search_dirs, &cpu_file).unwrap_or_else(|| {
        panic!(
            "Unable to find selected CPU library `{cpu_file}`.\nSearch directories:\n{}",
            format_search_dirs(search_dirs)
        )
    });

    let system_dir = system_path
        .parent()
        .expect("system library path has no parent");
    let cpu_dir = cpu_path.parent().expect("CPU library path has no parent");

    /*
     * Emit both directories, because split artifacts could theoretically live
     * in different directories.
     */
    println!("cargo:rustc-link-search=native={}", system_dir.display());
    if cpu_dir != system_dir {
        println!("cargo:rustc-link-search=native={}", cpu_dir.display());
    }

    let system_name = static_library_name(&system_file)
        .unwrap_or_else(|| panic!("Unsupported static library filename: {system_file}"));
    let cpu_name = static_library_name(&cpu_file)
        .unwrap_or_else(|| panic!("Unsupported static library filename: {cpu_file}"));

    /*
     * The system library depends on the CPU core, so preserve this order.
     * `static=` also prevents Cargo from interpreting an import library as a
     * dynamically linked dependency where platforms support both forms.
     */
    println!("cargo:rustc-link-lib=static={system_name}");
    println!("cargo:rustc-link-lib=static={cpu_name}");

    println!("cargo:rerun-if-changed={}", system_path.display());
    println!("cargo:rerun-if-changed={}", cpu_path.display());

    println!(
        "cargo:warning=PASM linked emulator system library: {}",
        system_path.display()
    );
    println!(
        "cargo:warning=PASM linked emulator CPU library: {}",
        cpu_path.display()
    );

    /*
     * Link subsystem libraries (e.g. the C64's 1541 floppy drive subsystem
     * with its own MOS6502 CPU). The main system library references symbols
     * from these subsystem libraries, so they must be linked as well.
     */
    let subsystems = extract_subsystems(manifest_text);
    for sub in &subsystems {
        let sub_system_file = target_library_filename(&sub.system_target);
        let sub_cpu_file = target_library_filename(&sub.cpu_core_target);

        /*
         * Subsystem libraries live under a subdirectory of the build tree
         * (e.g. build/subsystems/c64_1541_subsystem/Release on Visual
         * Studio). Build a set of search directories that includes the
         * subsystem's build subdirectory.
         */
        let mut sub_search_dirs = Vec::new();
        if !sub.cmake_subdir.is_empty() {
            for dir in search_dirs {
                /*
                 * search_dirs entries are typically build/Release or build.
                 * Strip the trailing Release/Debug config to get the build
                 * root, then append the cmake_subdir and re-add configs.
                 */
                let parent = dir.parent().unwrap_or(dir);
                add_build_dirs(&mut sub_search_dirs, &parent.join(&sub.cmake_subdir));
            }
        }
        /*
         * Fall back to the top-level search dirs as well.
         */
        for dir in search_dirs {
            push_unique_existing(&mut sub_search_dirs, dir.to_path_buf());
        }

        let sub_system_path = find_library(&sub_search_dirs, &sub_system_file)
            .unwrap_or_else(|| {
                panic!(
                    "Unable to find subsystem system library `{sub_system_file}` for subsystem `{}`.\nSearch directories:\n{}",
                    sub.system_target,
                    format_search_dirs(&sub_search_dirs)
                )
            });

        let sub_cpu_path = find_library(&sub_search_dirs, &sub_cpu_file)
            .unwrap_or_else(|| {
                panic!(
                    "Unable to find subsystem CPU core library `{sub_cpu_file}` for subsystem `{}`.\nSearch directories:\n{}",
                    sub.cpu_core_target,
                    format_search_dirs(&sub_search_dirs)
                )
            });

        let sub_system_dir = sub_system_path
            .parent()
            .expect("subsystem system library path has no parent");
        let sub_cpu_dir = sub_cpu_path
            .parent()
            .expect("subsystem CPU library path has no parent");

        println!("cargo:rustc-link-search=native={}", sub_system_dir.display());
        if sub_cpu_dir != sub_system_dir {
            println!("cargo:rustc-link-search=native={}", sub_cpu_dir.display());
        }

        let sub_system_name = static_library_name(&sub_system_file)
            .unwrap_or_else(|| panic!("Unsupported subsystem static library filename: {sub_system_file}"));
        let sub_cpu_name = static_library_name(&sub_cpu_file)
            .unwrap_or_else(|| panic!("Unsupported subsystem static library filename: {sub_cpu_file}"));

        /*
         * Link subsystem system before its CPU core (same dependency order
         * as the main system).
         */
        println!("cargo:rustc-link-lib=static={sub_system_name}");
        println!("cargo:rustc-link-lib=static={sub_cpu_name}");

        println!("cargo:rerun-if-changed={}", sub_system_path.display());
        println!("cargo:rerun-if-changed={}", sub_cpu_path.display());

        println!(
            "cargo:warning=PASM linked subsystem system library: {}",
            sub_system_path.display()
        );
        println!(
            "cargo:warning=PASM linked subsystem CPU library: {}",
            sub_cpu_path.display()
        );
    }
}

fn add_subsystem_search_dirs(
    dirs: &mut Vec<PathBuf>,
    manifest_text: &str,
    emu_dir: Option<&Path>,
    build_dir: Option<&Path>,
) {
    for object in extract_json_array_objects(manifest_text, "subsystems") {
        let Some(cmake_subdir) = extract_json_string(&object, "cmake_subdir") else {
            continue;
        };
        let cmake_subdir = cmake_subdir.trim();
        if cmake_subdir.is_empty() {
            continue;
        }
        if let Some(dir) = build_dir {
            add_build_dirs(dirs, &dir.join(cmake_subdir));
        }
        if let Some(dir) = emu_dir {
            add_build_dirs(dirs, &dir.join("build").join(cmake_subdir));
        }
    }
}

fn emit_subsystem_split_libraries(search_dirs: &[PathBuf], manifest_text: &str) {
    for object in extract_json_array_objects(manifest_text, "subsystems") {
        let id = extract_json_string(&object, "id").unwrap_or_else(|| "<unknown>".to_string());
        let Some(system_file) = extract_json_string(&object, "system_static") else {
            continue;
        };
        let Some(cpu_file) = extract_json_string(&object, "cpu_core_static") else {
            continue;
        };

        let system_path = find_library(search_dirs, &system_file).unwrap_or_else(|| {
            panic!(
                "Unable to find subsystem `{id}` system library `{system_file}`.\nSearch directories:\n{}",
                format_search_dirs(search_dirs)
            )
        });

        let cpu_path = find_library(search_dirs, &cpu_file).unwrap_or_else(|| {
            panic!(
                "Unable to find subsystem `{id}` CPU library `{cpu_file}`.\nSearch directories:\n{}",
                format_search_dirs(search_dirs)
            )
        });

        let system_dir = system_path
            .parent()
            .expect("subsystem system library path has no parent");
        let cpu_dir = cpu_path
            .parent()
            .expect("subsystem CPU library path has no parent");

        println!("cargo:rustc-link-search=native={}", system_dir.display());
        if cpu_dir != system_dir {
            println!("cargo:rustc-link-search=native={}", cpu_dir.display());
        }

        let system_name = static_library_name(&system_file).unwrap_or_else(|| {
            panic!("Unsupported subsystem static library filename: {system_file}")
        });
        let cpu_name = static_library_name(&cpu_file).unwrap_or_else(|| {
            panic!("Unsupported subsystem static library filename: {cpu_file}")
        });

        println!("cargo:rustc-link-lib=static={system_name}");
        println!("cargo:rustc-link-lib=static={cpu_name}");
        println!("cargo:rerun-if-changed={}", system_path.display());
        println!("cargo:rerun-if-changed={}", cpu_path.display());
        println!(
            "cargo:warning=PASM linked subsystem `{id}` system library: {}",
            system_path.display()
        );
        println!(
            "cargo:warning=PASM linked subsystem `{id}` CPU library: {}",
            cpu_path.display()
        );
    }
}

fn format_search_dirs(search_dirs: &[PathBuf]) -> String {
    search_dirs
        .iter()
        .map(|path| format!("  {}", path.display()))
        .collect::<Vec<_>>()
        .join("\n")
}

fn add_existing_string_path(set: &mut BTreeSet<String>, path: PathBuf) {
    if path.exists() {
        let normalized = normalize_existing_path(path);
        set.insert(normalized.to_string_lossy().into_owned());
    }
}

fn discover_vcpkg_lib_dirs() -> BTreeSet<String> {
    let mut out = BTreeSet::new();

    let default_triplet = if cfg!(target_os = "windows") {
        "x64-windows"
    } else if cfg!(target_os = "macos") {
        "x64-osx"
    } else {
        "x64-linux"
    };

    let triplet = env::var("VCPKG_TARGET_TRIPLET")
        .ok()
        .or_else(|| env::var("VCPKG_DEFAULT_TRIPLET").ok())
        .unwrap_or_else(|| default_triplet.to_string());

    let mut roots = Vec::<PathBuf>::new();

    if let Ok(root) = env::var("VCPKG_ROOT") {
        roots.push(PathBuf::from(root));
    }

    if cfg!(target_os = "windows") {
        roots.push(PathBuf::from(r"D:\Development\vcpkg"));
        roots.push(PathBuf::from(r"C:\vcpkg"));
    } else {
        roots.push(PathBuf::from("/usr/local/vcpkg"));
        roots.push(PathBuf::from("/opt/vcpkg"));

        if let Some(home) = env::var_os("HOME") {
            roots.push(PathBuf::from(home).join("vcpkg"));
        }
    }

    for root in roots {
        let installed = root.join("installed").join(&triplet);
        add_existing_string_path(&mut out, installed.join("lib"));
        add_existing_string_path(&mut out, installed.join("debug").join("lib"));
    }

    out
}

fn emit_manifest_extra_links(manifest_text: &str) {
    let mut link_paths = BTreeSet::<String>::new();
    let mut link_libs = BTreeSet::<String>::new();
    let mut link_files = BTreeSet::<String>::new();

    for raw in extract_json_array_strings(manifest_text, "library_paths") {
        if raw.trim().is_empty() {
            continue;
        }

        let resolved = resolve_input_path(raw.trim());
        link_paths.insert(normalize_existing_path(resolved).to_string_lossy().into_owned());
    }

    for lib in extract_json_array_strings(manifest_text, "library_names") {
        let lib = lib.trim();
        if !lib.is_empty() {
            link_libs.insert(lib.to_string());
        }
    }

    for raw in extract_json_array_strings(manifest_text, "library_files") {
        let raw = raw.trim();
        if raw.is_empty() {
            continue;
        }

        let resolved = resolve_input_path(raw);
        link_files.insert(normalize_existing_path(resolved).to_string_lossy().into_owned());
    }

    if let Ok(extra_libs) = env::var("PASM_EMU_EXTRA_LIBS") {
        for lib in extra_libs.split(',').map(str::trim).filter(|s| !s.is_empty()) {
            link_libs.insert(lib.to_string());
        }
    }

    if let Ok(extra_dirs) = env::var("PASM_EMU_EXTRA_LIB_DIRS") {
        for raw in extra_dirs
            .split(',')
            .map(str::trim)
            .filter(|s| !s.is_empty())
        {
            let resolved = resolve_input_path(raw);
            link_paths.insert(normalize_existing_path(resolved).to_string_lossy().into_owned());
        }
    }

    link_paths.extend(discover_vcpkg_lib_dirs());

    for dir in link_paths {
        println!("cargo:rustc-link-search=native={dir}");
    }

    for lib in link_libs {
        /*
         * Extra library names may intentionally include Cargo modifiers such
         * as `static=foo`, so preserve the manifest/environment value exactly.
         */
        println!("cargo:rustc-link-lib={lib}");
    }

    for file in link_files {
        println!("cargo:rerun-if-changed={file}");
        println!("cargo:rustc-link-arg={file}");
    }
}

fn main() {
    for variable in ENV_VARS {
        println!("cargo:rerun-if-env-changed={variable}");
    }

    /*
     * Check-cfg avoids newer Rust warnings when the Rust source uses custom
     * cfg names emitted by this build script in the future.
     */
    println!("cargo:rustc-check-cfg=cfg(pasm_linked_emulator)");

    if env::var_os("CARGO_FEATURE_LINKED_EMULATOR").is_none() {
        return;
    }

    println!("cargo:rustc-cfg=pasm_linked_emulator");

    let emu_dir = env::var("PASM_EMU_DIR")
        .ok()
        .map(|value| normalize_existing_path(resolve_input_path(&value)));

    let build_dir = env::var("PASM_EMU_BUILD_DIR")
        .ok()
        .map(|value| normalize_existing_path(resolve_input_path(&value)));

    let manifest_path = selected_manifest_path(emu_dir.as_deref());
    let manifest_path = normalize_existing_path(manifest_path);

    if !manifest_path.is_file() {
        panic!(
            "Selected PASM debugger manifest does not exist: {}\n\
             PASM_EMU_DIR={:?}\n\
             PASM_EMU_BUILD_DIR={:?}",
            manifest_path.display(),
            emu_dir,
            build_dir
        );
    }

    println!("cargo:rerun-if-changed={}", manifest_path.display());
    println!(
        "cargo:warning=PASM linked emulator manifest: {}",
        manifest_path.display()
    );

    let manifest_text = fs::read_to_string(&manifest_path).unwrap_or_else(|error| {
        panic!(
            "Unable to read selected debugger manifest {}: {error}",
            manifest_path.display()
        )
    });

    let system_name = extract_json_string(&manifest_text, "system_name")
        .unwrap_or_else(|| "<unknown>".to_string());
    let processor_name = extract_json_string(&manifest_text, "processor_name")
        .unwrap_or_else(|| "<unknown>".to_string());

    println!(
        "cargo:warning=PASM selected system: {system_name} ({processor_name})"
    );

    let mut search_dirs = selected_search_dirs(emu_dir.as_deref(), build_dir.as_deref());
    add_subsystem_search_dirs(
        &mut search_dirs,
        &manifest_text,
        emu_dir.as_deref(),
        build_dir.as_deref(),
    );

    println!(
        "cargo:warning=PASM emulator library search directories:\n{}",
        format_search_dirs(&search_dirs)
    );

    /*
     * Crucially, only the explicitly selected manifest is used. There is no
     * fallback that scans sibling generated systems. If the selected MSX build
     * is incomplete, the build fails instead of silently linking Apple II.
     */
    emit_required_split_libraries(&search_dirs, &manifest_text);
    emit_subsystem_split_libraries(&search_dirs, &manifest_text);
    emit_manifest_extra_links(&manifest_text);
}
