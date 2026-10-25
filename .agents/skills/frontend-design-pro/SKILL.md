---
name: frontend-design-pro
description: Constrói e refatora interfaces de usuário (UI/UX) modernas, acessíveis e profissionais em React/Next.js e Tailwind CSS. Ative quando o usuário pedir para criar componente, desenhar tela, melhorar layout, estilizar interface ou corrigir design.
version: "2.0.0"
requires:
  tools:
    - node
---

# Frontend & UI/UX Design System Skill

## Objetivo
Criar interfaces de usuário com alto apelo visual, usabilidade excepcional, responsividade e código limpo, eliminando padrões genéricos de "interface de IA" e respeitando rigorosamente os tokens do Design System do projeto.

---

## 🎨 Recursos do Design System

- **Tokens Semânticos Padrão:** [`resources/design_tokens.json`](./resources/design_tokens.json)  
  Contém definições de paleta de cores (modo claro e escuro), escalas de espaçamento (base 4px), tipografia e raios de borda.
- **Tokens do Projeto (se aplicável):** Sempre verifique se o projeto possui arquivos específicos como `tailwind.config.js`, `tokens.css` ou `tokens.json` e priorize-os.

---

## 🚫 Antipadrões Proibidos (Combate ao "Visual IA")

1. **Sem Gradientes Genéricos Roxos/Azuis:** Evite gradientes purpúreos genéricos sobre fundos pretos chapados. Prefira fundos foscos, sutis contrastes de superfície e acentos pontuais que representem a identidade do projeto.
2. **Sem Grades Repetitivas de Cards Idênticos:** Evite construir páginas compostas exclusivamente por matrizes homogêneas de cartões. Varie o peso visual com:
   - Painéis com divisões funcionais (*split views*).
   - Tabelas densas com cabeçalhos fixos (*sticky headers*) para dados tabulares.
   - Listas detalhadas e barras laterais contextuais.
3. **Sem Textos Centralizados sem Justificativa:** Parágrafos e blocos de leitura devem estar sempre alinhados à esquerda (`text-left`) para garantir leitura fluida.
4. **Sem Valores Mágicos de CSS:** Nunca use classes arbitrárias como `w-[347px]`, `h-[71px]` ou cores hexadecimais soltas como `bg-[#1a2b3c]`. Utilize as classes da escala do Tailwind (`w-full`, `max-w-md`) e variáveis/tokens do tema (`bg-card`, `text-foreground`, `border-border`).

---

## 📐 Diretrizes de Design e UX

### 1. Hierarquia Visual e Tipografia
- Estabeleça contraste tipográfico claro:
  - Títulos de destaque: `text-2xl` a `text-3xl`, peso `font-semibold` ou `font-bold`.
  - Títulos de seção/cartão: `text-lg` ou `text-base`, `font-medium`.
  - Corpo de texto: `text-sm` com cor secundária (`text-muted-foreground`).
  - Metadados, tags e rótulos: `text-xs` com caixa alta ou tracking ajustado.
- Numerais e telemetria: use fontes monoespaçadas ou numerais tabulares (`tabular-nums` / `font-mono`) para evitar saltos visuais em atualizações em tempo real.

### 2. Espaçamento Consistente (Grid de 4px)
- Mantenha espaçamento harmonioso utilizando múltiplos de 4:
  - Microespaçamentos (ícones, badges): `gap-1.5`, `p-1`, `space-x-2`.
  - Preenchimento interno de componentes: `p-3`, `p-4`, `p-6`.
  - Separação entre seções: `space-y-6`, `gap-8`.

### 3. Acessibilidade Nativa (a11y)
- **Semântica HTML:** Use `<article>`, `<section>`, `<nav>`, `<main>`, `<header>` e `<aside>` em vez de árvores intermináveis de `<div>`.
- **Foco Visível:** Todos os elementos interativos (`<button>`, `<a>`, `<input>`) devem possuir anéis de foco acessíveis:
  ```css
  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2
  ```
- **Ícones Decorativos:** Ícones de bibliotecas como `lucide-react` devem conter `aria-hidden="true"`. Botões contendo apenas ícone exigem `aria-label`.
- **Contraste de Cores:** Garanta conformidade mínima com a norma WCAG AA (proporção 4.5:1 para texto padrão).

---

## 🛠️ Procedimento de Construção

1. **Consulta e Herança de Tokens:**
   - Inspecione as configurações do projeto (`tailwind.config.js` ou [`resources/design_tokens.json`](./resources/design_tokens.json)).
   - Adote os nomes semânticos de classes (`bg-background`, `bg-card`, `border-border`, `text-primary`).

2. **Separação de Responsabilidades (Clean Code / SRP):**
   - **Componente Presentacional:** Recebe dados tipados via `props` e foca exclusivamente em layout, estados visuais e acessibilidade.
   - **Hooks / Containers:** Encapsulam regras de negócio, requisições de rede e mutações de estado.

3. **Responsividade e Suporte a Temas:**
   - Construa com abordagem *mobile-first* (`w-full sm:w-auto`, `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3`).
   - Garanta legibilidade tanto no tema claro quanto no escuro utilizando tokens semânticos.

---

## 💡 Exemplo Demonstrativo (Few-Shot Pattern)

### ❌ Interface Genérica e Frágil (Antes)
```tsx
// Ruim: sem tipagem, sem acessibilidade, cores hardcoded, div soup sem semântica
export function Card({ title, desc, onClick }: any) {
  return (
    <div 
      className="bg-[#1e1e24] w-[320px] p-5 rounded-[12px] text-center shadow-lg hover:bg-[#25252d]"
      onClick={onClick}
    >
      <h3 className="text-white text-lg font-bold">{title}</h3>
      <p className="text-gray-400 text-sm mt-2">{desc}</p>
      <div className="mt-4 text-purple-400 font-semibold cursor-pointer">
        Ver detalhes
      </div>
    </div>
  );
}
```

### ✅ Interface Profissional, Limpa e Acessível (Depois)
```tsx
import React from "react";
import { ArrowRight } from "lucide-react";

interface FeatureCardProps {
  title: string;
  description: string;
  badge?: string;
  onAction?: () => void;
  className?: string;
}

export function FeatureCard({
  title,
  description,
  badge,
  onAction,
  className = "",
}: FeatureCardProps) {
  return (
    <article
      className={`group relative flex flex-col justify-between rounded-xl border border-border bg-card p-6 text-card-foreground shadow-sm transition-all duration-200 hover:shadow-md hover:border-border/80 ${className}`}
    >
      <div>
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-base font-semibold leading-snug tracking-tight text-foreground">
            {title}
          </h3>
          {badge && (
            <span className="inline-flex items-center rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium text-secondary-foreground">
              {badge}
            </span>
          )}
        </div>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground text-left">
          {description}
        </p>
      </div>

      {onAction && (
        <div className="mt-6 pt-4 border-t border-border/50 flex justify-end">
          <button
            type="button"
            onClick={onAction}
            className="inline-flex items-center gap-1.5 rounded-lg text-sm font-medium text-primary hover:text-primary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 transition-colors"
            aria-label={`Ver detalhes sobre ${title}`}
          >
            <span>Ver detalhes</span>
            <ArrowRight
              className="h-4 w-4 transition-transform group-hover:translate-x-0.5"
              aria-hidden="true"
            />
          </button>
        </div>
      )}
    </article>
  );
}
```

---

## 📌 Checklist de Validação de UI/UX

Antes de finalizar qualquer componente ou tela, confirme:

- [ ] Foi eliminada qualquer dependência de classes arbitrárias mágicas (ex.: `bg-[#...]` ou `w-[...px]`)?
- [ ] O componente respeita a hierarquia tipográfica e o alinhamento à esquerda em textos longos?
- [ ] Elementos interativos (`<button>`, `<a>`) possuem estados claros de `:hover`, `:active` e `:focus-visible`?
- [ ] Ícones decorativos possuem `aria-hidden="true"` e botões de ação contêm rótulos descritivos (`aria-label`)?
- [ ] O layout foi testado para diferentes viewports (`sm:`, `md:`, `lg:`) sem quebras visuais?
- [ ] Os tipos das propriedades (`Props`) estão estritamente definidos em TypeScript?
