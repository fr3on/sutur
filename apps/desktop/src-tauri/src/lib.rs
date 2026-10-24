use std::sync::Mutex;
use tauri::menu::{MenuBuilder, MenuItemBuilder, PredefinedMenuItem, SubmenuBuilder};
use tauri::{Manager, WebviewWindow};

const SITE: &str = "https://sutur.ink";

/// The page zoom for the main window (1.0 = actual size).
static ZOOM: Mutex<f64> = Mutex::new(1.0);

fn zoom_by(win: &WebviewWindow, step: f64) {
    let mut z = ZOOM.lock().unwrap();
    *z = if step == 0.0 { 1.0 } else { (*z + step).clamp(0.6, 2.0) };
    let _ = win.set_zoom(*z);
}

fn open_in_browser(url: &str) {
    let _ = std::process::Command::new("open").arg(url).spawn();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri::plugin::Builder::<tauri::Wry, ()>::new("sutur-mac")
            .js_init_script("document.documentElement.classList.add('sutur-mac');")
            .build())
        .setup(|app| {
            let item = |id: &str, text: &str, key: Option<&str>| {
                let b = MenuItemBuilder::with_id(id, text);
                match key { Some(k) => b.accelerator(k).build(app), None => b.build(app) }
            };

            let app_menu = SubmenuBuilder::new(app, "Sutur")
                .about(None)
                .separator()
                .services()
                .separator()
                .hide()
                .hide_others()
                .show_all()
                .separator()
                .quit()
                .build()?;

            let file = SubmenuBuilder::new(app, "File")
                .item(&item("home", "Home", Some("CmdOrCtrl+Shift+H"))?)
                .item(&item("library", "Library", Some("CmdOrCtrl+L"))?)
                .item(&item("reading", "Reading Now", Some("CmdOrCtrl+Shift+R"))?)
                .item(&item("downloads", "Downloads", Some("CmdOrCtrl+Shift+D"))?)
                .separator()
                .item(&item("profile", "My Profile", Some("CmdOrCtrl+Shift+P"))?)
                .separator()
                .item(&item("browser", "Open in Browser", Some("CmdOrCtrl+Shift+O"))?)
                .separator()
                .close_window()
                .build()?;

            let edit = SubmenuBuilder::new(app, "Edit")
                .undo()
                .redo()
                .separator()
                .cut()
                .copy()
                .paste()
                .select_all()
                .build()?;

            let view = SubmenuBuilder::new(app, "View")
                .item(&item("reload", "Reload", Some("CmdOrCtrl+R"))?)
                .separator()
                .item(&item("back", "Back", Some("CmdOrCtrl+["))?)
                .item(&item("forward", "Forward", Some("CmdOrCtrl+]"))?)
                .separator()
                .item(&item("zoom_in", "Zoom In", Some("CmdOrCtrl+="))?)
                .item(&item("zoom_out", "Zoom Out", Some("CmdOrCtrl+-"))?)
                .item(&item("zoom_reset", "Actual Size", Some("CmdOrCtrl+0"))?)
                .separator()
                .fullscreen()
                .build()?;

            let window = SubmenuBuilder::new(app, "Window")
                .minimize()
                .maximize()
                .separator()
                .item(&PredefinedMenuItem::close_window(app, None)?)
                .build()?;

            let help = SubmenuBuilder::new(app, "Help")
                .item(&item("site", "Sutur Website", None)?)
                .item(&item("apps", "About the Apps", None)?)
                .item(&item("license", "Licence and Rights", None)?)
                .item(&item("privacy", "Privacy", None)?)
                .build()?;

            let menu = MenuBuilder::new(app)
                .items(&[&app_menu, &file, &edit, &view, &window, &help])
                .build()?;
            app.set_menu(menu)?;
            Ok(())
        })
        .on_menu_event(|app, event| {
            let Some(win) = app.get_webview_window("main") else { return };
            let go = |path: &str| { let _ = win.eval(&format!("location.href = '{path}'")); };
            match event.id().as_ref() {
                "home" => go("/app"),
                "library" => go("/app/library"),
                "reading" => go("/app/me?tab=going"),
                "downloads" => go("/app/downloads"),
                "profile" => go("/app/me"),
                "reload" => { let _ = win.eval("location.reload()"); }
                "back" => { let _ = win.eval("history.back()"); }
                "forward" => { let _ = win.eval("history.forward()"); }
                "zoom_in" => zoom_by(&win, 0.1),
                "zoom_out" => zoom_by(&win, -0.1),
                "zoom_reset" => zoom_by(&win, 0.0),
                "browser" => open_in_browser(&format!("{SITE}/")),
                "site" => open_in_browser(SITE),
                "apps" => open_in_browser(&format!("{SITE}/apps")),
                "license" => open_in_browser(&format!("{SITE}/license")),
                "privacy" => open_in_browser(&format!("{SITE}/privacy")),
                _ => {}
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Sutur");
}
