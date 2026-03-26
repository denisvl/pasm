use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::style::{Color, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Clear, List, ListItem, Paragraph};
use ratatui::Frame;

use crate::app::{App, JumpTarget, Pane};
use crate::state::DebuggerMode;

const BG_PANEL: Color = Color::Rgb(22, 28, 38);
const BG_FOCUS: Color = Color::Rgb(30, 40, 56);
const BG_STATUS: Color = Color::Rgb(20, 44, 54);
const BG_SHORTCUTS: Color = Color::Rgb(35, 25, 45);
const FG_TEXT: Color = Color::Rgb(218, 225, 236);
const FG_DIM: Color = Color::Rgb(150, 165, 185);
const FG_ACCENT: Color = Color::Rgb(255, 214, 112);
const FG_CHANGED: Color = Color::Rgb(255, 170, 120);
const FG_CURRENT: Color = Color::Rgb(130, 236, 175);
const BG_BREAKPOINT: Color = Color::Rgb(140, 35, 35);
const FG_ADDR: Color = Color::Rgb(156, 176, 202);
const FG_BYTES: Color = Color::Rgb(178, 192, 210);
const FG_MNEMONIC: Color = Color::Rgb(224, 232, 242);
const FG_META: Color = Color::Rgb(132, 150, 170);

fn centered_rect(percent_x: u16, percent_y: u16, area: Rect) -> Rect {
    let popup_layout = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage((100 - percent_y) / 2),
            Constraint::Percentage(percent_y),
            Constraint::Percentage((100 - percent_y) / 2),
        ])
        .split(area);

    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage((100 - percent_x) / 2),
            Constraint::Percentage(percent_x),
            Constraint::Percentage((100 - percent_x) / 2),
        ])
        .split(popup_layout[1])[1]
}

fn split_weighted(area: Rect, weights: &[u16], horizontal: bool, min_each: u16) -> Vec<Rect> {
    if weights.is_empty() {
        return Vec::new();
    }

    let total_space = if horizontal { area.width } else { area.height };
    let count = weights.len() as u16;
    let mut sizes = vec![0u16; weights.len()];

    if total_space == 0 {
        return sizes
            .into_iter()
            .map(|_| Rect {
                x: area.x,
                y: area.y,
                width: 0,
                height: 0,
            })
            .collect();
    }

    let min_base = if total_space >= min_each.saturating_mul(count) {
        min_each
    } else if total_space >= count {
        1
    } else {
        0
    };

    sizes.fill(min_base);
    let used = min_base.saturating_mul(count);
    let extra_total = total_space.saturating_sub(used);
    let weight_sum = weights.iter().fold(0u32, |acc, v| acc + (*v as u32)).max(1);

    let mut assigned = 0u16;
    for (idx, weight) in weights.iter().enumerate() {
        let share = ((extra_total as u32 * *weight as u32) / weight_sum) as u16;
        sizes[idx] = sizes[idx].saturating_add(share);
        assigned = assigned.saturating_add(share);
    }

    let mut remainder = extra_total.saturating_sub(assigned);
    let mut i = 0usize;
    while remainder > 0 {
        let idx = i % sizes.len();
        sizes[idx] = sizes[idx].saturating_add(1);
        remainder -= 1;
        i += 1;
    }

    let mut cursor_x = area.x;
    let mut cursor_y = area.y;
    sizes
        .into_iter()
        .map(|size| {
            let rect = if horizontal {
                let r = Rect {
                    x: cursor_x,
                    y: area.y,
                    width: size,
                    height: area.height,
                };
                cursor_x = cursor_x.saturating_add(size);
                r
            } else {
                let r = Rect {
                    x: area.x,
                    y: cursor_y,
                    width: area.width,
                    height: size,
                };
                cursor_y = cursor_y.saturating_add(size);
                r
            };
            rect
        })
        .collect()
}

fn pane_style(app: &App, pane: Pane) -> Style {
    if app.focused_pane == pane {
        Style::default().fg(FG_ACCENT).bg(BG_FOCUS)
    } else {
        Style::default().fg(FG_DIM).bg(BG_PANEL)
    }
}

fn panel_block(app: &App, pane: Pane, title: &'static str) -> Block<'static> {
    Block::default()
        .borders(Borders::ALL)
        .title(title)
        .border_style(pane_style(app, pane))
        .style(Style::default().fg(FG_TEXT).bg(BG_PANEL))
}

fn instruction_text_for_row(app: &App, instruction: &str) -> String {
    if app.show_instruction_info {
        return instruction.to_string();
    }
    if let Some((head, _)) = instruction.split_once(" OP=") {
        return head.trim_end().to_string();
    }
    instruction.to_string()
}

fn split_instruction_for_row(app: &App, instruction: &str) -> (String, Option<String>) {
    if let Some((head, tail)) = instruction.split_once(" OP=") {
        let mnemonic = head.trim_end().to_string();
        if app.show_instruction_info {
            return (mnemonic, Some(format!("OP={tail}")));
        }
        return (mnemonic, None);
    }
    (instruction_text_for_row(app, instruction), None)
}

fn build_shortcut_lines(max_inner_width: u16) -> Vec<Line<'static>> {
    let entries = [
        ("F4", "RunTo"),
        ("F7", "Into"),
        ("F8", "Over"),
        ("F6", "Out"),
        ("F5", "Reset"),
        ("F9", "RunPause"),
        ("H", "History"),
        ("I", "InstrInfo"),
        ("O", "Overlay"),
        ("B", "Breakpoint"),
        ("TAB", "Pane"),
        ("ARROWS", "Navigate"),
        ("PGUP/PGDN", "Page"),
        ("G", "Jump"),
        ("Q", "Quit"),
    ];

    let width = usize::from(max_inner_width.max(12));
    let mut lines: Vec<Vec<Span<'static>>> = vec![Vec::new(), Vec::new()];
    let mut used = [0usize, 0usize];
    let mut line_idx = 0usize;

    for (key, label) in entries {
        let token_len = key.len() + 1 + label.len() + 2;
        if line_idx == 0 && used[0] > 0 && used[0] + token_len > width {
            line_idx = 1;
        }
        if line_idx == 1 && used[1] > 0 && used[1] + token_len > width {
            let ellipsis = " ...";
            if used[1] + ellipsis.len() <= width {
                lines[1].push(Span::raw(ellipsis));
            }
            break;
        }
        lines[line_idx].push(Span::styled(key, Style::default().fg(FG_ACCENT)));
        lines[line_idx].push(Span::raw(format!(" {label}  ")));
        used[line_idx] += token_len;
    }

    let mut out = lines
        .into_iter()
        .take(2)
        .map(Line::from)
        .collect::<Vec<_>>();
    while out.len() < 2 {
        out.push(Line::from(Vec::<Span<'static>>::new()));
    }
    out
}

pub fn draw(frame: &mut Frame, app: &App) {
    let root = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(4), // Status block: exactly 2 inner lines.
            Constraint::Min(1),    // Main content uses the remaining space.
            Constraint::Length(4), // Shortcuts block: exactly 2 inner lines.
        ])
        .split(frame.area());

    let mut status_lines = Vec::new();
    status_lines.push(Line::from(vec![
        Span::styled(
            format!("{}  ", app.snapshot.core.target_name),
            Style::default().fg(FG_CURRENT),
        ),
        Span::styled(
            format!("mode={:?}  ", app.snapshot.core.mode),
            Style::default().fg(FG_ACCENT),
        ),
        Span::raw(format!("pc=0x{:04X}  ", app.snapshot.core.pc as u16)),
        Span::raw(format!("sp=0x{:04X}  ", app.snapshot.core.sp as u16)),
        Span::raw(format!("cycles={}  ", app.snapshot.core.total_cycles)),
        Span::raw(format!("tstate={}  ", app.snapshot.core.tstate_global)),
        Span::raw(format!("frame={}", app.snapshot.core.frame_index)),
    ]));
    let status_text = if app.snapshot.core.status_line.is_empty() {
        "-"
    } else {
        app.snapshot.core.status_line.as_str()
    };
    let msg = app.last_message.as_deref().unwrap_or("No messages");
    status_lines.push(Line::from(vec![
        Span::styled("status: ", Style::default().fg(FG_DIM)),
        Span::raw(status_text),
        Span::styled("  msg: ", Style::default().fg(FG_DIM)),
        Span::raw(msg),
    ]));

    let status = Paragraph::new(status_lines).block(
        Block::default()
            .borders(Borders::ALL)
            .title("Status")
            .style(Style::default().fg(FG_TEXT).bg(BG_STATUS))
            .border_style(Style::default().fg(FG_ACCENT).bg(BG_STATUS)),
    );
    frame.render_widget(status, root[0]);

    let main = split_weighted(root[1], &[62, 38], true, 1);
    let left = split_weighted(main[0], &[72, 28], false, 1);
    let right = split_weighted(main[1], &[44, 11, 11, 22, 12], false, 1);

    let disasm_and_history = if app.show_history {
        split_weighted(left[0], &[64, 36], true, 1)
    } else {
        vec![left[0]]
    };
    let disasm_area = disasm_and_history[0];
    let history_area = if app.show_history {
        disasm_and_history.get(1).copied()
    } else {
        None
    };

    let disasm_visible_rows = disasm_area.height.saturating_sub(2) as usize;
    let disasm_total = app.disasm_rows.len();
    let disasm_window_start = if disasm_visible_rows == 0 || disasm_total <= disasm_visible_rows {
        0
    } else {
        let half = disasm_visible_rows / 2;
        let base = app.disasm_selected_index.saturating_sub(half);
        base.min(disasm_total.saturating_sub(disasm_visible_rows))
    };

    let disasm_items: Vec<ListItem> = app
        .disasm_rows
        .iter()
        .enumerate()
        .skip(disasm_window_start)
        .take(disasm_visible_rows.max(1))
        .map(|(idx, row)| {
            let show_current_ip =
                row.is_current_ip && app.snapshot.core.mode != DebuggerMode::Running;
            let sel = if idx == app.disasm_selected_index {
                ">"
            } else {
                " "
            };
            let marker = if show_current_ip { "@" } else { " " };
            let ch = if row.changed { "!" } else { " " };
            let mut style = Style::default().fg(FG_TEXT).bg(BG_PANEL);
            if show_current_ip {
                style = Style::default()
                    .fg(Color::Black)
                    .bg(FG_CURRENT)
                    .add_modifier(ratatui::style::Modifier::BOLD);
            } else if row.has_breakpoint {
                style = Style::default()
                    .fg(Color::White)
                    .bg(BG_BREAKPOINT)
                    .add_modifier(ratatui::style::Modifier::BOLD);
            } else if row.changed {
                style = style.fg(FG_CHANGED);
            }

            if show_current_ip || row.has_breakpoint {
                return ListItem::new(Line::styled(
                    format!(
                        "{}{}{} {:04X}: {:<11} {}",
                        sel,
                        marker,
                        ch,
                        row.address as u16,
                        row.bytes,
                        instruction_text_for_row(app, &row.instruction)
                    ),
                    style,
                ));
            }

            let row_bg =
                if idx == app.disasm_selected_index && app.focused_pane == Pane::Disassembly {
                    BG_FOCUS
                } else {
                    BG_PANEL
                };
            let (mnemonic, meta) = split_instruction_for_row(app, &row.instruction);
            let prefix_style = if row.changed {
                Style::default().fg(FG_CHANGED).bg(row_bg)
            } else {
                Style::default().fg(FG_DIM).bg(row_bg)
            };
            let addr_style = Style::default().fg(FG_ADDR).bg(row_bg);
            let bytes_style = Style::default().fg(FG_BYTES).bg(row_bg);
            let mnemonic_style = if row.changed {
                Style::default().fg(FG_CHANGED).bg(row_bg)
            } else {
                Style::default().fg(FG_MNEMONIC).bg(row_bg)
            };
            let meta_style = Style::default().fg(FG_META).bg(row_bg);

            let mut spans = vec![
                Span::styled(format!("{sel}{marker}{ch} "), prefix_style),
                Span::styled(format!("{:04X}: ", row.address as u16), addr_style),
                Span::styled(format!("{:<11} ", row.bytes), bytes_style),
                Span::styled(mnemonic, mnemonic_style),
            ];
            if let Some(meta_text) = meta {
                spans.push(Span::styled(format!(" {meta_text}"), meta_style));
            }
            ListItem::new(Line::from(spans))
        })
        .collect();
    let disasm = List::new(disasm_items)
        .block(panel_block(app, Pane::Disassembly, "Disassembly"))
        .highlight_style(Style::default().fg(Color::Cyan));
    frame.render_widget(disasm, disasm_area);

    if let Some(area) = history_area {
        if app.snapshot.core.mode == DebuggerMode::Running {
            frame.render_widget(
                Paragraph::new(vec![
                    Line::from(Span::styled(
                        "History display is frozen while running.",
                        Style::default().fg(FG_DIM),
                    )),
                    Line::from(Span::styled(
                        "Pause execution to inspect the trace.",
                        Style::default().fg(FG_DIM),
                    )),
                ])
                .block(panel_block(app, Pane::History, "History")),
                area,
            );
        } else {
            let history_visible_rows = area.height.saturating_sub(2) as usize;
            let mut history_items: Vec<ListItem> = app
                .execution_history
                .iter()
                .rev()
                .skip(app.history_scroll)
                .take(history_visible_rows.max(1))
                .map(|row| {
                    let row_bg = if app.focused_pane == Pane::History {
                        BG_FOCUS
                    } else {
                        BG_PANEL
                    };
                    let spans = vec![
                        Span::styled(
                            format!("{:04X}: ", row.address as u16),
                            Style::default().fg(FG_ADDR).bg(row_bg),
                        ),
                        Span::styled(
                            format!("{:<11}", row.opcode),
                            Style::default().fg(FG_BYTES).bg(row_bg),
                        ),
                        Span::raw(" "),
                        Span::styled(
                            row.mnemonic.clone(),
                            Style::default().fg(FG_MNEMONIC).bg(row_bg),
                        ),
                    ];
                    ListItem::new(Line::from(spans))
                })
                .collect();
            if history_items.is_empty() {
                history_items.push(ListItem::new(Line::styled(
                    "(no entries)",
                    Style::default().fg(FG_DIM).bg(BG_PANEL),
                )));
            }

            frame.render_widget(
                List::new(history_items).block(
                    Block::default()
                        .borders(Borders::ALL)
                        .title(format!("History [{}/100]", app.execution_history.len()))
                        .border_style(pane_style(app, Pane::History))
                        .style(Style::default().fg(FG_TEXT).bg(BG_PANEL)),
                ),
                area,
            );
        }
    }

    let reg_visible_rows = right[0].height.saturating_sub(2) as usize;
    let reg_total = app.snapshot.registers.len();
    let reg_inner_width = right[0].width.saturating_sub(2) as usize;
    let reg_cols = if reg_inner_width >= 60 {
        3usize
    } else if reg_inner_width >= 36 {
        2usize
    } else {
        1usize
    };
    let reg_page_size = reg_visible_rows.max(1) * reg_cols;
    let reg_scroll = if app.focused_pane == Pane::Registers {
        app.scroll as usize
    } else {
        0
    };
    let reg_start = if reg_total <= reg_page_size {
        0
    } else {
        reg_scroll.min(reg_total.saturating_sub(reg_page_size))
    };
    let reg_col_width = (reg_inner_width / reg_cols).max(1);
    let reg_items: Vec<ListItem> = (0..reg_visible_rows.max(1))
        .map(|row_idx| {
            let mut spans: Vec<Span<'static>> = Vec::new();
            for col_idx in 0..reg_cols {
                let idx = reg_start + row_idx + (col_idx * reg_visible_rows.max(1));
                if idx >= reg_total {
                    continue;
                }
                let row = &app.snapshot.registers[idx];
                let ch = if row.changed { "!" } else { " " };
                let mut cell = format!("{} {:<7} {:<10}", ch, row.name, row.hex_value);
                if cell.len() > reg_col_width {
                    cell.truncate(reg_col_width);
                } else if cell.len() < reg_col_width {
                    cell.push_str(&" ".repeat(reg_col_width - cell.len()));
                }
                let style = if row.changed {
                    Style::default().fg(FG_CHANGED).bg(BG_PANEL)
                } else {
                    Style::default().fg(FG_TEXT).bg(BG_PANEL)
                };
                spans.push(Span::styled(cell, style));
            }
            ListItem::new(Line::from(spans))
        })
        .collect();
    let reg_end = (reg_start + reg_page_size).min(reg_total);
    let reg_title = if reg_total > reg_page_size {
        format!(
            "Registers [{}-{} / {} | {} col]",
            reg_start + 1,
            reg_end,
            reg_total,
            reg_cols
        )
    } else {
        format!("Registers [{} | {} col]", reg_total, reg_cols)
    };
    frame.render_widget(
        List::new(reg_items).block(
            Block::default()
                .borders(Borders::ALL)
                .title(reg_title)
                .border_style(pane_style(app, Pane::Registers))
                .style(Style::default().fg(FG_TEXT).bg(BG_PANEL)),
        ),
        right[0],
    );

    let flag_line = app
        .snapshot
        .flags
        .iter()
        .map(|f| {
            let ch = if f.changed { "!" } else { " " };
            format!("{ch}{}={}", f.name, if f.value { 1 } else { 0 })
        })
        .collect::<Vec<_>>()
        .join(" ");
    frame.render_widget(
        Paragraph::new(flag_line).block(panel_block(app, Pane::Flags, "Flags")),
        right[1],
    );

    let bp_visible_rows = right[2].height.saturating_sub(2) as usize;
    let bp_total = app.snapshot.breakpoints.len();
    let bp_inner_width = right[2].width.saturating_sub(2) as usize;
    let bp_cols = if bp_inner_width >= 42 {
        4usize
    } else if bp_inner_width >= 30 {
        3usize
    } else if bp_inner_width >= 18 {
        2usize
    } else {
        1usize
    };
    let bp_page_size = bp_visible_rows.max(1) * bp_cols;
    let bp_scroll = if app.focused_pane == Pane::Breakpoints {
        app.scroll as usize
    } else {
        0
    };
    let bp_start = if bp_total <= bp_page_size {
        0
    } else {
        bp_scroll.min(bp_total.saturating_sub(bp_page_size))
    };
    let bp_col_width = (bp_inner_width / bp_cols).max(1);
    let bp_items: Vec<ListItem> = if bp_total == 0 {
        vec![ListItem::new(Line::styled(
            "(none)",
            Style::default().fg(FG_DIM).bg(BG_PANEL),
        ))]
    } else {
        (0..bp_visible_rows.max(1))
            .map(|row_idx| {
                let mut spans: Vec<Span<'static>> = Vec::new();
                for col_idx in 0..bp_cols {
                    let idx = bp_start + row_idx + (col_idx * bp_visible_rows.max(1));
                    if idx >= bp_total {
                        continue;
                    }
                    let bp = &app.snapshot.breakpoints[idx];
                    let mut cell = format!(
                        "{:04X} {}",
                        bp.address as u16,
                        if bp.enabled { "on" } else { "off" }
                    );
                    if cell.len() > bp_col_width {
                        cell.truncate(bp_col_width);
                    } else if cell.len() < bp_col_width {
                        cell.push_str(&" ".repeat(bp_col_width - cell.len()));
                    }
                    let style = if bp.enabled {
                        Style::default().fg(FG_CURRENT).bg(BG_PANEL)
                    } else {
                        Style::default().fg(FG_DIM).bg(BG_PANEL)
                    };
                    spans.push(Span::styled(cell, style));
                }
                ListItem::new(Line::from(spans))
            })
            .collect()
    };
    let bp_end = (bp_start + bp_page_size).min(bp_total);
    let bp_title = if bp_total > bp_page_size {
        format!(
            "Breakpoints [{}-{} / {} | {} col]",
            bp_start + 1,
            bp_end,
            bp_total,
            bp_cols
        )
    } else {
        format!("Breakpoints [{} | {} col]", bp_total, bp_cols)
    };
    frame.render_widget(
        List::new(bp_items).block(
            Block::default()
                .borders(Borders::ALL)
                .title(bp_title)
                .border_style(pane_style(app, Pane::Breakpoints))
                .style(Style::default().fg(FG_TEXT).bg(BG_PANEL)),
        ),
        right[2],
    );

    let stack_visible_rows = right[3].height.saturating_sub(2) as usize;
    let stack_total = app.snapshot.stack.len();
    let stack_selected_index = app
        .snapshot
        .stack
        .iter()
        .position(|row| row.is_sp)
        .unwrap_or(0);
    let stack_window_start = if stack_visible_rows == 0 || stack_total <= stack_visible_rows {
        0
    } else {
        let half = stack_visible_rows / 2;
        let base = stack_selected_index.saturating_sub(half);
        base.min(stack_total.saturating_sub(stack_visible_rows))
    };
    let stack_items: Vec<ListItem> = app
        .snapshot
        .stack
        .iter()
        .enumerate()
        .skip(stack_window_start)
        .take(stack_visible_rows.max(1))
        .map(|(idx, s)| {
            let sel = if idx == stack_selected_index {
                ">"
            } else {
                " "
            };
            let ch = if s.changed { "!" } else { " " };
            let hi = ((s.value >> 8) & 0xFF) as u8;
            let lo = (s.value & 0xFF) as u8;
            let bytes = format!("{hi:02X} {lo:02X}");
            let ascii = [hi, lo]
                .into_iter()
                .map(|b| {
                    if (0x20..=0x7E).contains(&b) {
                        b as char
                    } else {
                        '.'
                    }
                })
                .collect::<String>();
            let tag = if s.is_sp { "SP" } else { "  " };
            let style = if idx == stack_selected_index {
                Style::default().fg(FG_ACCENT).bg(BG_FOCUS)
            } else if s.changed {
                Style::default().fg(FG_CHANGED).bg(BG_PANEL)
            } else {
                Style::default().fg(FG_TEXT).bg(BG_PANEL)
            };
            ListItem::new(Line::styled(
                format!(
                    "{sel}{ch} {:04X}: {:<5} {} {}",
                    s.address as u16, bytes, ascii, tag
                ),
                style,
            ))
        })
        .collect();
    let stack_start = app
        .snapshot
        .stack
        .first()
        .map(|r| r.address as u16)
        .unwrap_or(0);
    let stack_end = app
        .snapshot
        .stack
        .last()
        .map(|r| r.address as u16)
        .unwrap_or(0);
    frame.render_widget(
        List::new(stack_items).block(
            Block::default()
                .borders(Borders::ALL)
                .title(format!("Stack [{stack_start:04X}-{stack_end:04X}]"))
                .border_style(pane_style(app, Pane::Stack))
                .style(Style::default().fg(FG_TEXT).bg(BG_PANEL)),
        ),
        right[3],
    );

    let th_items: Vec<ListItem> = app
        .snapshot
        .threads
        .iter()
        .map(|t| {
            ListItem::new(format!(
                "id={} {: <8} ip={:04X}",
                t.thread_id, t.state, t.ip as u16
            ))
        })
        .collect();
    frame.render_widget(
        List::new(th_items).block(panel_block(app, Pane::Threads, "Threads")),
        right[4],
    );

    let mem_visible_rows = left[1].height.saturating_sub(2) as usize;
    let mem_total = app.memory_rows.len();
    let selected_index = app.memory_selected_index();
    let mem_window_start = if mem_visible_rows == 0 || mem_total <= mem_visible_rows {
        0
    } else {
        let half = mem_visible_rows / 2;
        let base = selected_index.saturating_sub(half);
        base.min(mem_total.saturating_sub(mem_visible_rows))
    };

    let mem_items: Vec<ListItem> = app
        .memory_rows
        .iter()
        .enumerate()
        .skip(mem_window_start)
        .take(mem_visible_rows.max(1))
        .map(|(idx, m)| {
            let sel = if idx == selected_index { ">" } else { " " };
            let ch = if m.changed { "!" } else { " " };
            let style = if idx == selected_index {
                Style::default().fg(FG_ACCENT).bg(BG_FOCUS)
            } else if m.changed {
                Style::default().fg(FG_CHANGED).bg(BG_PANEL)
            } else {
                Style::default().fg(FG_TEXT).bg(BG_PANEL)
            };
            ListItem::new(Line::styled(
                format!(
                    "{sel}{ch} {:04X}: {:<48} {}",
                    m.address as u16, m.hex_bytes, m.ascii
                ),
                style,
            ))
        })
        .collect();
    let mem_start = app
        .memory_rows
        .first()
        .map(|r| r.address as u16)
        .unwrap_or(0);
    let mem_end = app
        .memory_rows
        .last()
        .map(|r| r.address as u16)
        .unwrap_or(0);
    frame.render_widget(
        List::new(mem_items).block(
            Block::default()
                .borders(Borders::ALL)
                .title(format!("Memory [{mem_start:04X}-{mem_end:04X}]"))
                .border_style(pane_style(app, Pane::Memory))
                .style(Style::default().fg(FG_TEXT).bg(BG_PANEL)),
        ),
        left[1],
    );

    let shortcuts = Paragraph::new(build_shortcut_lines(root[2].width.saturating_sub(2))).block(
        Block::default()
            .borders(Borders::ALL)
            .title("Shortcuts")
            .style(Style::default().fg(FG_TEXT).bg(BG_SHORTCUTS))
            .border_style(Style::default().fg(FG_ACCENT).bg(BG_SHORTCUTS)),
    );
    frame.render_widget(shortcuts, root[2]);

    if app.jump_dialog.active {
        let area = centered_rect(52, 22, frame.area());
        let target_label = match app.jump_dialog.target {
            JumpTarget::Disassembly => "Disassembly (nearest instruction)",
            JumpTarget::Memory => "Memory (line address)",
        };
        let content = vec![
            Line::from(vec![
                Span::styled("Target: ", Style::default().fg(FG_DIM)),
                Span::styled(target_label, Style::default().fg(FG_ACCENT)),
            ]),
            Line::from(vec![
                Span::styled("Address: ", Style::default().fg(FG_DIM)),
                Span::styled(
                    if app.jump_dialog.input.is_empty() {
                        "<type address>".to_string()
                    } else {
                        app.jump_dialog.input.clone()
                    },
                    Style::default().fg(FG_TEXT),
                ),
            ]),
            Line::from(vec![
                Span::styled("Enter", Style::default().fg(FG_ACCENT)),
                Span::raw(" apply  "),
                Span::styled("Esc", Style::default().fg(FG_ACCENT)),
                Span::raw(" cancel"),
            ]),
        ];
        frame.render_widget(Clear, area);
        frame.render_widget(
            Paragraph::new(content).block(
                Block::default()
                    .borders(Borders::ALL)
                    .title("Jump To Address")
                    .style(Style::default().fg(FG_TEXT).bg(BG_STATUS))
                    .border_style(Style::default().fg(FG_ACCENT).bg(BG_STATUS)),
            ),
            area,
        );
    }
}
