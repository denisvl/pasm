use std::collections::HashSet;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

fn extract_json_string(text: &str, key: &str) -> Option<String> {
    let needle = format!("\"{key}\"");
    let start = text.find(&needle)?;
    let rest = &text[start + needle.len()..];
    let colon = rest.find(':')?;
    let rest = &rest[colon + 1..];
    let first_quote = rest.find('"')?;
    let rest = &rest[first_quote + 1..];
    let end_quote = rest.find('"')?;
    Some(rest[..end_quote].to_string())
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
    let mut chars = rest[open + 1..].chars();
    let mut out = Vec::new();
    let mut current = String::new();
    let mut in_string = false;
    let mut escaped = false;
    for ch in chars.by_ref() {
        if in_string {
            if escaped {
                current.push(ch);
                escaped = false;
                continue;
            }
            match ch {
                '\\' => escaped = true,
                '"' => {
                    in_string = false;
                    out.push(current.clone());
                    current.clear();
                }
                _ => current.push(ch),
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

fn detect_library_entry(
    search_dir: &Path,
    lib_basename: Option<&str>,
) -> Option<(String, String, PathBuf)> {
    let mut entries: Vec<PathBuf> = fs::read_dir(search_dir)
        .ok()?
        .filter_map(|e| e.ok().map(|v| v.path()))
        .collect();
    entries.sort();

    if let Some(base) = lib_basename {
        #[cfg(target_env = "msvc")]
        let candidates = [(format!("{base}.lib"), base.to_string())];

        #[cfg(not(target_env = "msvc"))]
        let candidates = [
            (format!("lib{base}.a"), format!("static={base}")),
            (format!("lib{base}.so"), format!("dylib={base}")),
            (format!("lib{base}.dylib"), format!("dylib={base}")),
            (format!("{base}.lib"), base.to_string()),
        ];

        for (filename, link_spec) in candidates {
            let full_path = search_dir.join(&filename);
            if full_path.exists() {
                return Some((search_dir.display().to_string(), link_spec, full_path));
            }
        }
    }

    for path in entries {
        let Some(file_name) = path.file_name().and_then(|v| v.to_str()) else {
            continue;
        };

        #[cfg(target_env = "msvc")]
        {
            // Avoid selecting MinGW/GCC archives when linking with MSVC.
            if file_name.ends_with(".a")
                || file_name.ends_with(".so")
                || file_name.ends_with(".dylib")
            {
                continue;
            }
        }

        if file_name.starts_with("lib") && file_name.ends_with("_emu.a") {
            let base = file_name
                .trim_start_matches("lib")
                .trim_end_matches(".a")
                .to_string();
            return Some((
                search_dir.display().to_string(),
                format!("static={base}"),
                path,
            ));
        }
        if file_name.starts_with("lib") && file_name.ends_with("_emu.so") {
            let base = file_name
                .trim_start_matches("lib")
                .trim_end_matches(".so")
                .to_string();
            return Some((
                search_dir.display().to_string(),
                format!("dylib={base}"),
                path,
            ));
        }
        if file_name.starts_with("lib") && file_name.ends_with("_emu.dylib") {
            let base = file_name
                .trim_start_matches("lib")
                .trim_end_matches(".dylib")
                .to_string();
            return Some((
                search_dir.display().to_string(),
                format!("dylib={base}"),
                path,
            ));
        }
        if file_name.ends_with("_emu.lib") {
            let base = file_name.trim_end_matches(".lib").to_string();
            return Some((search_dir.display().to_string(), base, path));
        }
    }
    None
}

fn add_if_exists_unique(vec: &mut Vec<PathBuf>, path: PathBuf) {
    if path.exists() && !vec.iter().any(|v| v == &path) {
        vec.push(path);
    }
}

fn add_build_dirs(vec: &mut Vec<PathBuf>, base: &Path) {
    add_if_exists_unique(vec, base.join("Release"));
    add_if_exists_unique(vec, base.join("RelWithDebInfo"));
    add_if_exists_unique(vec, base.join("MinSizeRel"));
    add_if_exists_unique(vec, base.join("Debug"));
    add_if_exists_unique(vec, base.to_path_buf());
}

fn discover_generated_dirs() -> Vec<PathBuf> {
    let mut dirs = Vec::new();
    let Some(manifest_dir) = env::var_os("CARGO_MANIFEST_DIR") else {
        return dirs;
    };
    let manifest_dir = PathBuf::from(manifest_dir);
    let Some(workspace_root) = manifest_dir.parent().and_then(|p| p.parent()) else {
        return dirs;
    };
    let generated_root = workspace_root.join("generated");
    let Ok(entries) = fs::read_dir(generated_root) else {
        return dirs;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            let build = path.join("build");
            add_build_dirs(&mut dirs, &build);
            add_if_exists_unique(&mut dirs, path);
        }
    }
    dirs
}

fn workspace_root_from_manifest_dir() -> Option<PathBuf> {
    let manifest_dir = env::var_os("CARGO_MANIFEST_DIR").map(PathBuf::from)?;
    manifest_dir
        .parent()
        .and_then(|p| p.parent())
        .map(PathBuf::from)
}

fn resolve_input_path(raw: &str) -> PathBuf {
    let p = PathBuf::from(raw);
    if p.is_absolute() {
        return p;
    }
    if let Some(root) = workspace_root_from_manifest_dir() {
        return root.join(p);
    }
    p
}

fn add_if_exists_unique_str(vec: &mut Vec<String>, path: PathBuf) {
    if !path.exists() {
        return;
    }
    let value = path.to_string_lossy().to_string();
    if !vec.iter().any(|v| v == &value) {
        vec.push(value);
    }
}

fn discover_vcpkg_lib_dirs() -> Vec<String> {
    let mut out = Vec::new();
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

    let mut roots: Vec<PathBuf> = Vec::new();
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
        add_if_exists_unique_str(&mut out, installed.join("lib"));
        add_if_exists_unique_str(&mut out, installed.join("debug").join("lib"));
    }

    out
}

fn main() {
    println!("cargo:rerun-if-env-changed=PASM_EMU_DIR");
    println!("cargo:rerun-if-env-changed=PASM_EMU_BUILD_DIR");
    println!("cargo:rerun-if-env-changed=PASM_EMU_LIB_BASENAME");
    println!("cargo:rerun-if-env-changed=PASM_EMU_MANIFEST");
    println!("cargo:rerun-if-env-changed=PASM_EMU_EXTRA_LIBS");
    println!("cargo:rerun-if-env-changed=PASM_EMU_EXTRA_LIB_DIRS");
    println!("cargo:rerun-if-env-changed=VCPKG_ROOT");
    println!("cargo:rerun-if-env-changed=VCPKG_TARGET_TRIPLET");
    println!("cargo:rerun-if-env-changed=VCPKG_DEFAULT_TRIPLET");

    if env::var_os("CARGO_FEATURE_LINKED_EMULATOR").is_none() {
        return;
    }

    let emu_dir_str = env::var("PASM_EMU_DIR").ok();
    let build_dir_str = env::var("PASM_EMU_BUILD_DIR").ok();
    let emu_dir = emu_dir_str.as_ref().map(|v| resolve_input_path(v));
    let build_dir = build_dir_str.as_ref().map(|v| resolve_input_path(v));
    let manifest_path = env::var("PASM_EMU_MANIFEST")
        .ok()
        .map(|v| resolve_input_path(&v))
        .or_else(|| emu_dir.as_ref().map(|p| p.join("debugger_link.json")));
    if let Some(path) = &manifest_path {
        println!("cargo:rerun-if-changed={}", path.display());
    }
    let mut lib_basename = env::var("PASM_EMU_LIB_BASENAME").ok();
    let mut manifest_text: Option<String> = None;

    if lib_basename.is_none() {
        if let Some(path) = &manifest_path {
            if let Ok(text) = fs::read_to_string(path) {
                manifest_text = Some(text.clone());
                lib_basename = extract_json_string(&text, "library_basename");
            }
        }
    }
    if manifest_text.is_none() {
        if let Some(path) = &manifest_path {
            manifest_text = fs::read_to_string(path).ok();
        }
    }

    let mut search_dirs: Vec<PathBuf> = Vec::new();
    let has_explicit_dirs = emu_dir.is_some() || build_dir.is_some();
    if let Some(dir) = emu_dir {
        add_build_dirs(&mut search_dirs, &dir.join("build"));
        add_if_exists_unique(&mut search_dirs, dir);
    }
    if let Some(dir) = build_dir {
        add_build_dirs(&mut search_dirs, &dir);
    }
    if !has_explicit_dirs {
        for dir in discover_generated_dirs() {
            add_if_exists_unique(&mut search_dirs, dir);
        }
    }
    if search_dirs.is_empty() {
        panic!("unable to locate generated emulator artifacts.\nSet PASM_EMU_DIR to your generated output directory (contains debugger_link.json), build it with CMake, then retry.");
    }

    for dir in &search_dirs {
        if let Some((search_path, link_spec, lib_path)) =
            detect_library_entry(dir, lib_basename.as_deref())
        {
            println!("cargo:rustc-link-search=native={search_path}");
            println!("cargo:rustc-link-lib={link_spec}");
            println!("cargo:rerun-if-changed={}", lib_path.display());

            let mut extra_link_paths: HashSet<String> = HashSet::new();
            let mut extra_link_libs: HashSet<String> = HashSet::new();
            let mut extra_link_files: HashSet<String> = HashSet::new();

            let effective_manifest_text = if manifest_text.is_some() {
                manifest_text.clone()
            } else {
                let search_path_buf = PathBuf::from(&search_path);
                let candidate = if search_path_buf.ends_with("build") {
                    search_path_buf
                        .parent()
                        .map(|p| p.join("debugger_link.json"))
                } else {
                    Some(search_path_buf.join("debugger_link.json"))
                };
                candidate.and_then(|p| fs::read_to_string(p).ok())
            };

            if let Some(text) = &effective_manifest_text {
                for p in extract_json_array_strings(text, "library_paths") {
                    if !p.is_empty() {
                        let resolved = resolve_input_path(&p);
                        extra_link_paths.insert(resolved.to_string_lossy().to_string());
                    }
                }
                for l in extract_json_array_strings(text, "library_names") {
                    if !l.is_empty() {
                        extra_link_libs.insert(l);
                    }
                }
                for f in extract_json_array_strings(text, "library_files") {
                    if !f.is_empty() {
                        extra_link_files.insert(f);
                    }
                }
            }

            if let Ok(extra_libs) = env::var("PASM_EMU_EXTRA_LIBS") {
                for lib in extra_libs
                    .split(',')
                    .map(|s| s.trim())
                    .filter(|s| !s.is_empty())
                {
                    extra_link_libs.insert(lib.to_string());
                }
            }
            if let Ok(extra_lib_dirs) = env::var("PASM_EMU_EXTRA_LIB_DIRS") {
                for dir in extra_lib_dirs
                    .split(',')
                    .map(|s| s.trim())
                    .filter(|s| !s.is_empty())
                {
                    extra_link_paths.insert(dir.to_string());
                }
            }
            for dir in discover_vcpkg_lib_dirs() {
                extra_link_paths.insert(dir);
            }

            for dir in extra_link_paths {
                println!("cargo:rustc-link-search=native={dir}");
            }
            for lib in extra_link_libs {
                println!("cargo:rustc-link-lib={lib}");
            }
            for file in extra_link_files {
                println!("cargo:rerun-if-changed={file}");
                println!("cargo:rustc-link-arg={file}");
            }
            return;
        }
    }

    let placeholder_hint = if emu_dir_str
        .as_deref()
        .map(|v| v.contains("/path/to/generated/emulator"))
        .unwrap_or(false)
        || build_dir_str
            .as_deref()
            .map(|v| v.contains("/path/to/generated/emulator"))
            .unwrap_or(false)
    {
        "\nDetected placeholder path '/path/to/generated/emulator'. Replace it with a real generated output path."
    } else {
        ""
    };

    #[cfg(target_env = "msvc")]
    let msvc_archive_hint = {
        let mut found_gnu_archive = false;
        for dir in &search_dirs {
            if let Ok(entries) = fs::read_dir(dir) {
                for entry in entries.flatten() {
                    if let Some(name) = entry.file_name().to_str() {
                        if name.starts_with("lib") && name.ends_with("_emu.a") {
                            found_gnu_archive = true;
                            break;
                        }
                    }
                }
            }
            if found_gnu_archive {
                break;
            }
        }
        if found_gnu_archive {
            "\nDetected GCC/MinGW archive (*.a) in selected emulator build directory. With rustc-msvc/link.exe you must build the emulator with MSVC so a *.lib import/static library is produced (for example, use the .bat launcher or CMake Visual Studio generator)."
        } else {
            ""
        }
    };

    #[cfg(not(target_env = "msvc"))]
    let msvc_archive_hint = "";

    panic!(
        "unable to locate generated emulator library.\nChecked directories: {:?}\nExpected basename: {:?}{}{}\nHint:\n  1) uv run python -m src.main generate --processor <processor.yaml> --system <system.yaml> --output <out>\n  2) cmake -S <out> -B <out>/build && cmake --build <out>/build\n  3) PASM_EMU_DIR=<out> cargo run --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- --backend linked",
        search_dirs, lib_basename, placeholder_hint, msvc_archive_hint
    );
}
