mod actions;
mod app;
mod backend;
mod state;
mod ui;

use std::io;
use std::time::{Duration, Instant};

use actions::map_key_event;
use app::{App, RunSpeedMode};
use backend::mock::MockDebuggerBackend;
use backend::DebuggerBackend;
use crossterm::event::{self, Event, KeyEventKind};
use crossterm::execute;
use crossterm::terminal::{
    disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen,
};
use ratatui::backend::CrosstermBackend;
use ratatui::Terminal;
use state::DebuggerMode;

fn parse_arg(flag: &str) -> Option<String> {
    let args: Vec<String> = std::env::args().collect();
    args.windows(2).find(|w| w[0] == flag).map(|w| w[1].clone())
}

fn has_flag(flag: &str) -> bool {
    std::env::args().any(|arg| arg == flag)
}

#[allow(dead_code)]
fn parse_u64_arg(flag: &str) -> Option<u64> {
    let raw = parse_arg(flag)?;
    if let Some(hex) = raw.strip_prefix("0x").or_else(|| raw.strip_prefix("0X")) {
        u64::from_str_radix(hex, 16).ok()
    } else {
        raw.parse::<u64>().ok()
    }
}

fn build_backend() -> Result<Box<dyn DebuggerBackend>, String> {
    let backend_name = parse_arg("--backend").unwrap_or_else(|| "mock".to_string());
    if backend_name == "mock" {
        return Ok(Box::new(MockDebuggerBackend::new()));
    }

    if backend_name == "linked" {
        #[cfg(feature = "linked-emulator")]
        {
            let memory_size = parse_u64_arg("--memory-size")
                .and_then(|v| usize::try_from(v).ok())
                .unwrap_or(65536);
            let system_dir = parse_arg("--system-dir");
            let cart_rom = parse_arg("--cart-rom");
            let start_pc = parse_u64_arg("--start-pc");
            let backend = backend::linked_emulator::LinkedEmulatorBackend::new(
                memory_size,
                system_dir.as_deref(),
                cart_rom.as_deref(),
                start_pc,
            )?;
            return Ok(Box::new(backend));
        }
        #[cfg(not(feature = "linked-emulator"))]
        {
            return Err(
                "linked backend requires cargo feature 'linked-emulator' and generated emulator linkage"
                    .to_string(),
            );
        }
    }

    Err(format!(
        "unsupported backend '{backend_name}'. Use --backend mock|linked"
    ))
}

fn parse_speed_mode() -> Result<RunSpeedMode, String> {
    let speed_arg = parse_arg("--speed").or_else(|| parse_arg("--run-speed"));
    match speed_arg.as_deref() {
        None | Some("realtime") => Ok(RunSpeedMode::Realtime),
        Some("max") | Some("fast") => Ok(RunSpeedMode::Max),
        Some(other) => Err(format!(
            "invalid speed value '{other}'. Use --speed realtime|max (or --run-speed)"
        )),
    }
}

fn run_ui(mut app: App, use_alt_screen: bool) -> Result<(), String> {
    enable_raw_mode().map_err(|e| e.to_string())?;
    let mut stdout = io::stdout();
    if use_alt_screen {
        execute!(stdout, EnterAlternateScreen).map_err(|e| e.to_string())?;
    }
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend).map_err(|e| e.to_string())?;

    let mut last_tick = Instant::now();
    let mut needs_draw = true;

    loop {
        if needs_draw {
            terminal
                .draw(|frame| ui::draw(frame, &app))
                .map_err(|e| e.to_string())?;
            needs_draw = false;
        }

        if app.should_quit {
            break;
        }

        let tick_rate = if app.snapshot.core.mode == DebuggerMode::Running {
            Duration::from_millis(16)
        } else {
            // Keep paused refreshes sparse so terminal selection/copy is usable.
            Duration::from_millis(1500)
        };
        let timeout = tick_rate.saturating_sub(last_tick.elapsed());
        if event::poll(timeout).map_err(|e| e.to_string())? {
            if let Event::Key(key) = event::read().map_err(|e| e.to_string())? {
                if matches!(key.kind, KeyEventKind::Press | KeyEventKind::Repeat) {
                    if app.handle_key_event(key)? {
                        needs_draw = true;
                        continue;
                    }
                    let action = map_key_event(key);
                    app.handle_action(action)?;
                    needs_draw = true;
                }
            }
        }

        let now = Instant::now();
        let elapsed = now.saturating_duration_since(last_tick);
        if elapsed >= tick_rate {
            app.on_tick_with_elapsed(elapsed)?;
            // Anchor the next tick to the timestamp captured before running
            // the emulation slice so runtime cost is included in pacing.
            last_tick = now;
            needs_draw = true;
        }
    }

    disable_raw_mode().map_err(|e| e.to_string())?;
    if use_alt_screen {
        execute!(terminal.backend_mut(), LeaveAlternateScreen).map_err(|e| e.to_string())?;
    }
    terminal.show_cursor().map_err(|e| e.to_string())?;
    Ok(())
}

fn main() {
    let backend = match build_backend() {
        Ok(v) => v,
        Err(err) => {
            eprintln!("backend initialization failed: {err}");
            std::process::exit(1);
        }
    };

    let app = match App::new(backend) {
        Ok(v) => v,
        Err(err) => {
            eprintln!("failed to build app state: {err}");
            std::process::exit(1);
        }
    };
    let mut app = app;
    if let Some(v) = parse_u64_arg("--run-steps-per-tick") {
        if let Ok(steps) = usize::try_from(v) {
            if steps > 0 {
                app.run_steps_per_tick = steps;
            }
        }
    }
    app.run_speed_mode = match parse_speed_mode() {
        Ok(mode) => mode,
        Err(err) => {
            eprintln!("{err}");
            std::process::exit(1);
        }
    };
    let no_alt_screen_flag = has_flag("--no-alt-screen");
    let alt_screen_flag = has_flag("--alt-screen");
    let no_alt_screen_env = std::env::var("PASM_TUI_NO_ALT_SCREEN")
        .map(|v| {
            let t = v.trim();
            !t.is_empty() && t != "0"
        })
        .unwrap_or(false);
    let alt_screen_env = std::env::var("PASM_TUI_ALT_SCREEN")
        .map(|v| {
            let t = v.trim();
            !t.is_empty() && t != "0"
        })
        .unwrap_or(false);
    // Default to alt-screen so quitting restores the original terminal contents.
    let use_alt_screen = if no_alt_screen_flag || no_alt_screen_env {
        false
    } else if alt_screen_flag || alt_screen_env {
        true
    } else {
        true
    };

    if let Err(err) = run_ui(app, use_alt_screen) {
        let _ = disable_raw_mode();
        if use_alt_screen {
            let _ = execute!(io::stdout(), LeaveAlternateScreen);
        }
        eprintln!("tui runtime error: {err}");
        std::process::exit(1);
    }
}
