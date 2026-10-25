---
name: clean-code-refactoring
description: Aplica princípios e padrões de Clean Code (SOLID, DRY, KISS, Boy Scout Rule) na refatoração, auditoria e revisão de código-fonte sem alterar o comportamento externo. Use quando o usuário pedir para refatorar código, eliminar code smells, simplificar condicionais aninhadas, remover valores mágicos ou melhorar legibilidade e manutenibilidade.
---

# Clean Code Refactoring & Audit Skill

## Objetivo
Transformar código-fonte bruto ou legado em um software limpo, legível, testável e de fácil manutenção, sem alterar seu comportamento externo (refatoração estrita).

---

## 📋 Diretrizes de Execução (Passo a Passo)

### 1. Análise de Odores de Código (Code Smells Identification)
Antes de modificar o código, audite e identifique os seguintes sintomas:

- **Bloaters (Funções e Classes Gigantes):** Funções com mais de 20–30 linhas ou classes com excesso de responsabilidades.
- **Valores Mágicos:** Números (`0.05`, `86400`, `404`) ou strings de configuração embutidos diretamente no fluxo de execução.
- **Nesting Profundo (Arrow Anti-Pattern):** Três ou mais níveis de indentação gerados por `if/else`, `try/except` ou laços aninhados.
- **Comentários Redundantes ou Mentiroso:** Comentários que apenas repetem o que o código faz ou que ficaram defasados após alterações anteriores.
- **Parâmetros Excessivos:** Funções que recebem mais de 3 argumentos, dificultando testes unitários e legibilidade.
- **Efeitos Colaterais Ocultos:** Funções que modificam objetos passados por parâmetro ou alteram estado global sem evidenciar isso no nome ou assinatura.

---

### 2. Aplicação das Regras de Refatoração

- **Nomenclatura Intencional e Reveladora:**
  - Nomes devem explicar claramente o *porquê* de existirem e o que representam.
  - Substitua variáveis crípticas (`d`, `usr`, `tmp_val`) por termos de domínio claros (`elapsed_time_in_days`, `active_user`, `intermediate_result`).
  - Funções devem usar verbos de ação (`calculate_user_tax`, `validate_order_items`).

- **Princípio da Responsabilidade Única (SRP) e Único Nível de Abstração (SLAP):**
  - Cada função deve realizar apenas uma tarefa bem definida em um único nível conceitual de abstração.
  - Funções orquestradoras chamam funções especializadas sem misturar lógica de baixo nível com regras de negócio.

- **Eliminação de Duplicação (DRY - Don't Repeat Yourself):**
  - Extraia blocos repetidos para funções utilitárias ou métodos auxiliares privados.

- **Substituição de Magia por Constantes ou Enums:**
  - Extraia números e strings literais para constantes expressivas no topo do módulo ou use Enumerações tipadas (`enum.Enum`).

- **Cláusulas de Guarda (Guard Clauses / Early Returns):**
  - Elimine estruturas em pirâmide de `if/else`. Valide pré-condições no início da função e retorne imediatamente caso falhem.

- **Agrupamento de Parâmetros:**
  - Quando uma função necessitar de 4 ou mais parâmetros correlacionados, agrupe-os em uma estrutura de dados explícita (`dataclass`, `NamedTuple` ou modelo Pydantic).

---

### 3. Aplicação da Regra do Escoteiro (Boy Scout Rule)
- Entregue o arquivo alterado sempre mais limpo do que como ele foi encontrado:
  - Adicione anotações de tipo (*Type Hints*).
  - Remova importações não utilizadas e variáveis mortas.
  - Garanta formatação consistente (ex.: PEP 8 para Python, Prettier para JS/TS).

---

## 🚫 Regras Negativas (Restrições Estritas)

- **Não altere o comportamento funcional externo:** Refatoração pura não adiciona features nem altera contratos de saída. Garanta paridade comportamental.
- **Sem parâmetros booleanos de controle (Flag Arguments):** Evite funções como `process_user(user, is_admin=True)`. Divida em duas funções explícitas: `process_admin_user(user)` e `process_regular_user(user)`.
- **Não adicione comentários óbvios:** O código limpo deve ser autoexplicativo. Comentários devem explicar apenas o "porquê" de decisões complexas de negócio ou restrições de arquitetura, nunca o "como".
- **Evite Over-Engineering (YAGNI - You Aren't Gonna Need It):** Não crie abstrações complexas (padrões de projeto pesados, fábricas desnecessárias) para problemas simples.

---

## 💡 Exemplo Demonstrativo (Few-Shot Pattern)

### ❌ Código Poluído (Antes)
```python
def p(u, t):
    # Verifica se usuario é ativo e calcula taxa
    if u[2] == True:
        if t == 1:
            return u[3] * 0.05
        elif t == 2:
            return u[3] * 0.10
    return 0
```

### ✅ Código Limpo (Depois)
```python
from enum import IntEnum
from dataclasses import dataclass

class AccountType(IntEnum):
    STANDARD = 1
    PREMIUM = 2

STANDARD_TAX_RATE: float = 0.05
PREMIUM_TAX_RATE: float = 0.10

@dataclass(frozen=True)
class UserAccount:
    id: str
    name: str
    is_active: bool
    balance: float
    account_type: AccountType

def calculate_user_tax(user_balance: float, account_type: AccountType) -> float:
    """Calcula o valor da taxa com base no tipo de conta e saldo disponível."""
    if account_type == AccountType.STANDARD:
        return user_balance * STANDARD_TAX_RATE
    if account_type == AccountType.PREMIUM:
        return user_balance * PREMIUM_TAX_RATE
    return 0.0

def process_active_user_tax(user: UserAccount) -> float:
    """Valida pré-condição de ativação e delega o cálculo fiscal."""
    if not user.is_active:
        return 0.0
    return calculate_user_tax(user.balance, user.account_type)
```

---

## 📌 Checklist de Auditoria e Code Review

Ao refatorar qualquer trecho de código, valide os seguintes pontos antes da entrega:

- [ ] As variáveis e funções possuem nomes que revelam claramente sua intenção sem necessidade de comentários explicativos?
- [ ] Todas as constantes e números mágicos foram devidamente nomeados?
- [ ] O aninhamento de `if/else` foi reduzido ao mínimo utilizando cláusulas de guarda (*early returns*)?
- [ ] As funções têm no máximo 15–20 linhas e realizam apenas uma única responsabilidade (SRP)?
- [ ] Não foram introduzidas flags booleanas como parâmetros de controle de fluxo?
- [ ] O contrato de tipos (*type hints*) está presente nas assinaturas de funções públicas?
- [ ] O comportamento externo original foi 100% preservado?
