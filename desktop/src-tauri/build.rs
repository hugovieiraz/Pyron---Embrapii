// Antes de compilar: a abertura usa os tokens, os estilos, os ícones, os textos e a logo da interface (fonte única em
// app/interface e app/estatico), e o ícone do executável é o da marca (marca/pyron.ico). As cópias ficam em
// desktop/abertura/gerado e desktop/src-tauri/icons, fora do git.

use std::path::PathBuf;

fn copiar(de: &str, para: &str) {
    let aqui = PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR"));
    let origem = aqui.join("../..").join(de);
    let destino = aqui.join(para);
    std::fs::create_dir_all(destino.parent().expect("pasta")).expect("criar pasta");
    std::fs::copy(&origem, &destino).unwrap_or_else(|e| panic!("{}: {e}", origem.display()));
    println!("cargo:rerun-if-changed={}", origem.display());
}

fn main() {
    for arquivo in ["tokens.css", "base.css", "componentes.css", "textos.js"] {
        copiar(&format!("app/interface/{arquivo}"), &format!("../abertura/gerado/{arquivo}"));
    }
    copiar("app/interface/js/icones.js", "../abertura/gerado/icones.js");
    copiar("app/estatico/marca/logo-cor.svg", "../abertura/gerado/logo-cor.svg");
    copiar("marca/pyron.ico", "icons/icon.ico");

    // o único comando do aplicativo; a permissão "allow-reiniciar" vai só para a abertura (capabilities/abertura.json)
    let manifesto = tauri_build::AppManifest::new().commands(&["reiniciar"]);
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(manifesto)).expect("tauri-build");
}
