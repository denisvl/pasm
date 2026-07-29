use std::env;
use std::path::{Path, PathBuf};
use std::process::Command;


fn main() {
    let manifest_dir = PathBuf::from(env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR"));
    let repo_root = manifest_dir
        .ancestors()
        .nth(3)
        .expect("repo root")
        .to_path_buf();
    let out_dir = PathBuf::from(env::var("OUT_DIR").expect("OUT_DIR"));
    let include_dir = repo_root.join("automation/include");
    let core_source = repo_root.join("automation/core/emu_automation.c");
    let support_source = manifest_dir.join("tests/support/mock_automation.c");
    let core_object = out_dir.join("emu_automation.o");
    let support_object = out_dir.join("mock_automation.o");
    let archive = out_dir.join("libemu_automation_test_support.a");

    println!("cargo:rerun-if-changed={}", core_source.display());
    println!("cargo:rerun-if-changed={}", support_source.display());
    println!("cargo:rerun-if-changed={}", include_dir.join("emu_automation.h").display());
    println!(
        "cargo:rerun-if-changed={}",
        include_dir.join("emu_automation_adapter.h").display()
    );

    compile_object(&core_source, &core_object, &include_dir);
    compile_object(&support_source, &support_object, &include_dir);
    archive_objects(&archive, &[&core_object, &support_object]);

    println!("cargo:rustc-link-search=native={}", out_dir.display());
    println!("cargo:rustc-link-lib=static=emu_automation_test_support");
}

fn compile_object(source: &Path, object: &Path, include_dir: &Path) {
    let status = Command::new("cc")
        .arg("-std=c11")
        .arg("-Wall")
        .arg("-Wextra")
        .arg("-I")
        .arg(include_dir)
        .arg("-c")
        .arg(source)
        .arg("-o")
        .arg(object)
        .status()
        .expect("failed to invoke cc");
    assert!(status.success(), "cc failed for {}", source.display());
}

fn archive_objects(archive: &Path, objects: &[&Path]) {
    let status = Command::new("ar")
        .arg("crs")
        .arg(archive)
        .args(objects)
        .status()
        .expect("failed to invoke ar");
    assert!(status.success(), "ar failed for {}", archive.display());
}
