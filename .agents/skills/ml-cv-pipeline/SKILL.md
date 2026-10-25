---
name: ml-cv-pipeline
description: Auxilia no desenvolvimento de pipelines de Machine Learning e Visão Computacional aplicando princípios de Clean Code. Use quando o usuário pedir para tratar datasets de imagens, treinar modelos PyTorch/YOLO/OpenCV, avaliar métricas de CV ou refatorar código de IA.
version: "2.0.0"
requires:
  tools:
    - python3
---

# Machine Learning & Computer Vision Skill (Clean Code Edition)

## Objetivo
Padronizar o desenvolvimento, pré-processamento, auditoria e treinamento de modelos de Visão Computacional e Machine Learning, garantindo modularidade, legibilidade, reprodutibilidade e conformidade rigorosa com princípios de Clean Code.

---

## 🛠️ Scripts Utilitários Disponíveis

- **Validador de Dataset:** [`scripts/validate_cv_dataset.py`](./scripts/validate_cv_dataset.py)  
  Script determinístico para verificar integridade física de imagens, detectar arquivos corrompidos/vazios e auditar anotações (YOLO e Classificação).

---

## 📋 Instruções Procedimentais

### 1. Validação do Dataset e Pré-processamento
Antes de iniciar qualquer pipeline de treinamento ou manipulação de dados, execute a auditoria determinística:

```bash
# Validação básica
python .agents/skills/ml-cv-pipeline/scripts/validate_cv_dataset.py --data-dir "caminho/para/dataset"

# Validação com formato específico e exportação de relatório JSON
python .agents/skills/ml-cv-pipeline/scripts/validate_cv_dataset.py --data-dir "caminho/para/dataset" --format yolo --output "relatorio_dataset.json"
```

- **Resiliência a imagens truncadas:** Em pipelines com fluxos contínuos de imagens térmicas ou radiométricas, inclua obrigatoriamente:
  ```python
  from PIL import ImageFile
  ImageFile.LOAD_TRUNCATED_IMAGES = True
  ```
- **Auditoria de Splits:** Assegure que os conjuntos `train`, `val` e `test` não compartilhem amostras da mesma fonte ou sequência temporal (evitar *data leakage*).

---

### 2. Arquitetura Modular e Clean Code (Separação de Responsabilidades)
Estruture o código em módulos desacoplados com responsabilidade única (SRP):

- `dataset.py` / `dataloader.py`: Apenas carregamento, decodificação e augmentação de dados.
- `model.py` / `backbone.py`: Definição pura da arquitetura neural (sem loops de treino ou métricas).
- `trainer.py`: Orquestração do loop de treinamento, checkpoints e gerenciamento de épocas.
- `metrics.py`: Cálculo matemático de métricas de avaliação.
- `infer.py` / `export.py`: Inferência em produção e exportação para formatos como ONNX ou TorchScript.

#### Configuração via Dataclass (Eliminação de Magic Numbers)
Centralize todos os hiperparâmetros em `dataclass` ou arquivos de configuração estruturados:

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class TrainingConfig:
    data_dir: Path
    epochs: int = 50
    batch_size: int = 16
    learning_rate: float = 1e-4
    seed: int = 42
    device: str = "cuda"
    checkpoint_dir: Path = Path("checkpoints")
```

---

### 3. Reprodutibilidade e Determinismo
Fixe sementes no início de qualquer execução de treino ou amostragem:

```python
import random
import os
import numpy as np
import torch

def set_seed(seed: int = 42) -> None:
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
```

---

### 4. Loop de Treinamento e Gestão Eficiente de Recursos
- **Uso de Precision Mista (AMP):** Reduz consumo de VRAM e acelera o treino em GPUs modernas.
- **Isolamento de Gradientes:** Use `torch.inference_mode()` (ou `torch.no_grad()`) em fases de validação e inferência.
- **Evitar Vazamento de Memória (OOM):** Nunca acumule tensores com grafo de computação no histórico de métricas. Use `.item()` ou `.detach()`:
  ```python
  # Incorreto: acumula o grafo na memória
  total_loss += loss

  # Correto: extrai o escalar numérico
  total_loss += loss.item()
  ```
- **Limpeza Periódica de VRAM:** Utilize `torch.cuda.empty_cache()` estrategicamente caso enfrente picos transitórios de alocação.

---

### 5. Avaliação e Métricas de Visão Computacional
Nunca avalie o modelo apenas por acurácia global bruta quando houver desbalanceamento de classes:

- **Detecção de Objetos (YOLO/Faster R-CNN):** Calcular $mAP@50$ e $mAP@50:95$, acompanhados de Precision, Recall e IoU.
- **Classificação:** Calcular F1-Score ponderado/macro e matriz de confusão normalizada por linha.
- **Segmentação Semântica:** Reportar mean IoU (mIoU) e Dice Coefficient por classe.

---

### 6. Exportação e Inferência Limpa
- Prepare pipelines para exportação limpa via **ONNX** ou **TorchScript**.
- Valide paridade numérica entre a saída nativa PyTorch e o modelo exportado (tolerância $\text{atol} < 10^{-4}$).
- Forneça classes de inferência com interface concisa:
  ```python
  class ModelPredictor:
      def __init__(self, model_path: Path, device: str = "cpu"): ...
      def predict(self, image: np.ndarray) -> PredictionResult: ...
  ```

---

## ⚠️ Erros Comuns e Como Evitá-los

| Erro Comum | Consequência | Ação Corretiva |
| :--- | :--- | :--- |
| **Esquecer `model.eval()`** | Dropout e BatchNorm continuam ativos durante validação, corrompendo métricas. | Sempre alternar com `model.train()` e `model.eval()`. |
| **Misturar Bounding Box Formats** | Confusão entre $(x_{min}, y_{min}, x_{max}, y_{max})$ e $(x_c, y_c, w, h)$ normalizados. | Declarar explicitamente nos nomes das variáveis ou usar `dataclass` tipada (ex.: `BBoxXYWH`). |
| **Data Leakage no Augmentation** | Aplicar augmentações probabilísticas de treino no conjunto de validação/teste. | Manter pipelines separados: `train_transform` com augmentação; `val_transform` estritamente determinístico (Resize + Normalize). |
| **Hardcoding de Device** | Quebra em ambientes sem GPU ou com múltiplas placas. | Usar `device = torch.device("cuda" if torch.cuda.is_available() else "cpu")`. |
