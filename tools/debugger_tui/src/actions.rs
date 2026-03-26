use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Action {
    Quit,
    Refresh,
    Reset,
    RunPause,
    StepInto,
    StepOver,
    StepOut,
    ToggleInstructionInfo,
    ToggleHistory,
    ToggleOverlay,
    ToggleBreakpoint,
    SelectNextPane,
    SelectPrevPane,
    ScrollDown,
    ScrollUp,
    PageDown,
    PageUp,
    JumpToAddress,
    RunToCursor,
    Noop,
}

pub fn map_key_event(ev: KeyEvent) -> Action {
    if let KeyCode::Char(ch) = ev.code {
        let lower = ch.to_ascii_lowercase();
        if ev.modifiers.contains(KeyModifiers::CONTROL) && lower == 'c' {
            return Action::Quit;
        }
        return match lower {
            'q' => Action::Quit,
            'r' => Action::Refresh,
            'x' => Action::Reset,
            'i' => Action::ToggleInstructionInfo,
            'h' => Action::ToggleHistory,
            'o' => Action::ToggleOverlay,
            'b' => Action::ToggleBreakpoint,
            'g' => Action::JumpToAddress,
            _ => Action::Noop,
        };
    }

    match ev.code {
        KeyCode::F(9) => Action::RunPause,
        KeyCode::F(4) => Action::RunToCursor,
        KeyCode::Tab => Action::SelectNextPane,
        KeyCode::BackTab => Action::SelectPrevPane,
        KeyCode::Down => Action::ScrollDown,
        KeyCode::Up => Action::ScrollUp,
        KeyCode::PageDown => Action::PageDown,
        KeyCode::PageUp => Action::PageUp,
        KeyCode::F(6) => Action::StepOut,
        KeyCode::F(7) => Action::StepInto,
        KeyCode::F(8) => Action::StepOver,
        KeyCode::F(5) => Action::Reset,
        _ => Action::Noop,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};

    #[test]
    fn maps_function_keys() {
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::F(5), KeyModifiers::NONE)),
            Action::Reset
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::F(7), KeyModifiers::NONE)),
            Action::StepInto
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::F(8), KeyModifiers::NONE)),
            Action::StepOver
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::F(6), KeyModifiers::NONE)),
            Action::StepOut
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::F(9), KeyModifiers::NONE)),
            Action::RunPause
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::F(4), KeyModifiers::NONE)),
            Action::RunToCursor
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::PageUp, KeyModifiers::NONE)),
            Action::PageUp
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::PageDown, KeyModifiers::NONE)),
            Action::PageDown
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::Char('g'), KeyModifiers::NONE)),
            Action::JumpToAddress
        );
    }

    #[test]
    fn maps_fallback_step_keys() {
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::Char('Q'), KeyModifiers::SHIFT)),
            Action::Quit
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::Char('x'), KeyModifiers::NONE)),
            Action::Reset
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::Char('X'), KeyModifiers::SHIFT)),
            Action::Reset
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::Char('s'), KeyModifiers::NONE)),
            Action::Noop
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::Char('n'), KeyModifiers::NONE)),
            Action::Noop
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::Char('o'), KeyModifiers::NONE)),
            Action::ToggleOverlay
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::Char('O'), KeyModifiers::SHIFT)),
            Action::ToggleOverlay
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::Char('i'), KeyModifiers::NONE)),
            Action::ToggleInstructionInfo
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::Char('h'), KeyModifiers::NONE)),
            Action::ToggleHistory
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::Char(' '), KeyModifiers::NONE)),
            Action::Noop
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::Char('I'), KeyModifiers::SHIFT)),
            Action::ToggleInstructionInfo
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::Char('H'), KeyModifiers::SHIFT)),
            Action::ToggleHistory
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::Char('B'), KeyModifiers::SHIFT)),
            Action::ToggleBreakpoint
        );
        assert_eq!(
            map_key_event(KeyEvent::new(KeyCode::Char('G'), KeyModifiers::SHIFT)),
            Action::JumpToAddress
        );
    }
}
