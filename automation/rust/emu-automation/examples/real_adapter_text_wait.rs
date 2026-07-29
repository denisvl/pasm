use std::env;

use emu_automation::Library;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args().skip(1);
    let library = args.next().ok_or("usage: real_adapter_text_wait <library> [create_symbol] [text]")?;
    let create_symbol = args.next().unwrap_or_else(|| "emu_automation_create".to_string());
    let expected_text = args.next().unwrap_or_else(|| "READY".to_string());

    let library = Library::open(library)?;
    let machine = library.create_machine(&create_symbol)?;

    let descriptor = machine.describe()?;
    println!("machine: {:?}", descriptor);
    println!("capabilities: {:?}", machine.capabilities()?);

    let text_views = machine.screen().text_views()?;
    let region_id = text_views.first().map(|view| view.region_id.as_str());
    let snapshot = machine
        .screen()
        .wait_for_text(&expected_text, region_id, 180, 1)?;
    println!("{}", snapshot.plain);
    Ok(())
}
