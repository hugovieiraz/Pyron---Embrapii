# Pyron 0.9.0

Versão fechada em 30/10/2026: modo servidor, tablet (PWA), laudo em Typst, TensorRT no servidor com placa NVIDIA e o
Pyron desktop em Tauri v2. O modo local continua igual ao da 0.8 (`Pyron.exe` → 127.0.0.1, sem login).

## Fases

| Fase | Relatório | O que entrou |
|---|---|---|
| F0 | [0-diagnostico.md](0-diagnostico.md) | classificação das rotas, concorrência, motivo do ONNX na CPU, tempos do laudo, decisões |
| F1 | [1-servidor.md](1-servidor.md) | `--modo servidor`, login e perfis, comentários, histórico com autor, laudos emitidos, WAL, edição simultânea; implantação em [../servidor/implantacao.md](../servidor/implantacao.md) |
| F2 | [2-tablet.md](2-tablet.md) | PWA, gestos de toque, layout de tablet, Tailscale ([../servidor/tablet.md](../servidor/tablet.md)) |
| F3 | [3-laudo.md](3-laudo.md) | laudo em Typst (padrão desde 30/10/2026), Noto Sans |
| F4 | [4-tensorrt.md](4-tensorrt.md) | provedores TensorRT/CUDA/DirectML/CPU, cache do motor, benchmark e paridade |
| F5 | [5-tauri.md](5-tauri.md) | Pyron desktop (`desktop/`), adaptador de janela, bandeja, aviso do Windows |

## Decisões do usuário

| Assunto | Decisão |
|---|---|
| Assinatura do laudo | nome e registro de quem está logado |
| Time | até 20 pessoas; técnico muda pendência que não seja Urgente/Imediato; só engenheiro apaga; administrador é marca à parte |
| Login | usuário e senha definidos no cadastro do time |
| WAL | nos dois modos |
| HTTPS dos tablets | Tailscale gratuito (uso não comercial, até 6 usuários) |
| Fonte do laudo | Noto Sans (OFL); visual do Typst aprovado e padrão |
| TensorRT | FP32 como padrão (FP16 perdeu uma detecção na borda do limiar) |
| Licenças | as listadas no F0 aprovadas, inclusive NVIDIA (CUDA, cuDNN, TensorRT) e Visual Studio Build Tools |
| Tauri | seguir com a implementação (Rust instalado pelo usuário); licenças indiretas (MPL-2.0, Unicode-3.0, BSD-3, Zlib) aprovadas |

## Pendente

- **Pyron desktop:** assinatura do executável e teste numa máquina com o Controle Inteligente de Aplicativos ligado;
  conferência à mão da bandeja, do aviso do Windows, do arraste e do PDF. Até lá o `Pyron.exe` em C# é o padrão.
  Ao distribuir, junto do executável: `desktop/LICENCAS-TERCEIROS.txt` (`python desktop/licencas_terceiros.py`).
- **TensorRT:** paridade e tempo no servidor NVIDIA real e com o modelo treinado da equipe.
- **Tablet:** instalação real num iPad e num Android pela rede Tailscale.
- **Laudo:** prova do Controle Inteligente para o `typst` (`.pyd`) numa máquina com ele ligado.
- **Servidor:** telas de Modelos e Captura ainda mostram ações de administrador a quem não é (o servidor recusa com 403);
  Dockerfile não feito (precisa de aprovação).
