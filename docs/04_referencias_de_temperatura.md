# Referências de temperatura: quando um ponto quente é um problema

> Versão 0.1, 28/09/2026. Resposta à pergunta: "de que adianta saber o ponto mais quente se não
> sabemos quanto o componente aguenta nem qual é a temperatura normal dele?"

## 1. O que as normas brasileiras dizem

| Norma | O que resolve |
|---|---|
| **ABNT NBR 15866:2010** (metodologia de avaliação de temperatura de trabalho de equipamentos em sistemas elétricos; em revisão pela ABNT/CE-058) | Diz **contra o que** uma anomalia é avaliada. São quatro referências: (i) **valor do fabricante** nas condições nominais, a **MTA** (máxima temperatura admissível); (ii) **elemento semelhante adjacente** (ΔT); (iii) **valor do usuário com base no histórico operacional**; (iv) **critério do responsável técnico** |
| **ABNT NBR 15572:2013** (guia de inspeção de equipamentos elétricos e mecânicos) | A severidade segue o critério do usuário, requisitos normativos ou recomendações do fabricante. Define responsabilidades (termografista, assistente qualificado, usuário final) e o conteúdo do relatório |
| **ABNT NBR 15763:2009** (periodicidade em sistemas de potência) | Inspeção a cada **6 meses**, sem passar de **18 meses** |
| **ABNT NBR 15424** (terminologia) e **NBR 15718** (verificação de termovisores) | Termos e verificação da câmera |
| **NR-10** | Instalações com mais de 75 kW precisam do **Prontuário das Instalações Elétricas (PIE)**. Laudos, inspeções e termografia fazem parte dele, e o laudo é emitido por engenheiro com ART. Seguradoras costumam exigir manutenção preditiva comprovada |

## 2. As três referências que respondem à pergunta

### 2.1 Quanto o componente aguenta: a MTA

A MTA vem do fabricante. Sem ela, das normas de projeto do componente:

| Componente | Limite (ambiente de projeto de 40 °C) | Fonte |
|---|---|---|
| Conexão aparafusada de cobre ou alumínio nus, no ar | 100 °C (60 K de elevação) | IEC 62271-1 (NBR IEC 62271-1), tabela de limites |
| Conexão aparafusada estanhada | 105 °C (65 K) | IEC 62271-1 |
| Conexão prateada ou niquelada | 115 °C (75 K) | IEC 62271-1 |
| Terminal para condutor externo, nu | 100 °C (60 K) | IEC 62271-1 |
| Terminal de bucha | 55 K de elevação (95 °C) | IEC 60137 |
| Óleo no topo do transformador | 60 K (100 °C) | NBR 5356-2 / IEC 60076-2 |
| Enrolamento, média / ponto mais quente | 65 K / 78 K | NBR 5356-2 / IEC 60076-2 |
| Cabo isolado PVC / XLPE-EPR (condutor) | 70 °C / 90 °C | NBR 5410 / NBR 14039 |
| **Sem informação: conexões e componentes metálicos** | **90 °C** | Prática brasileira de inspeção em subestações |
| **Sem informação: cabos isolados** | **70 °C** | Idem |

### 2.2 O que é normal: o componente semelhante

É o mesmo componente em outra fase, sob a mesma carga, no mesmo momento. Anula o efeito da carga,
do sol e do vento. É o ΔT da NETA MTS e do Infraspection Institute.

### 2.3 O que é normal para este componente: o histórico

É o mesmo componente em inspeções anteriores, normalizado por carga e ambiente. É daqui que sai a
previsão: tendência e tempo até atingir a MTA.

## 3. As contas que os termografistas fazem

**Projeção para plena carga e ambiente de projeto.** A elevação de temperatura de uma parte
resistiva cresce com o quadrado da corrente:

```
T_projetada = T_amb,ref + (T_medida − T_amb) × (I_nominal / I_medida)^n       n ≈ 2 (1,6 a 2)
% da MTA    = T_projetada / MTA
```

**Quanto de carga falta até a MTA** (é o que a operação quer saber):

```
fator de carga limite = sqrt( (MTA − T_amb) / (T_medida − T_amb) )
```

Exemplo: um conector a 60 °C com ambiente de 30 °C e MTA de 90 °C suporta √(60/30) ≈ 1,41 vez a
corrente do momento da medição antes de chegar ao limite.

**Vento.** Resfria muito: com 7,2 m/s a elevação pode cair a um sexto. Fatores multiplicativos
simples de correção são criticados pela literatura. A regra prática é **não fazer medição
quantitativa com vento acima de cerca de 4 m/s (15 km/h)** e registrar o vento no laudo.

**Carga mínima.** Abaixo de cerca de 40% da nominal, a projeção fica pouco confiável.

## 4. Faixas de prioridade usadas no Brasil

Tabela que cruza as duas referências (capítulo "Ensaios termográficos", revista O Setor Elétrico,
a partir da NBR 15866 e do Infraspection Institute):

| Prioridade | ΔT (semelhante) | % da MTA | Ação |
|---|---|---|---|
| 4 | 5 a 10 °C | acima de 60% até 70% | Corrigir na próxima manutenção periódica |
| 3 | acima de 10 até 20 °C | acima de 70% até 80% | Corrigir com agendamento |
| 2 | acima de 20 até 40 °C | acima de 80% até 100% | Corrigir o mais rápido possível |
| 1 | acima de 40 °C | acima de 100% | Corrigir imediatamente |

### Para-raios: regra própria

O aquecimento do para-raios não vem da carga, mas da corrente de fuga nos varistores de óxido
metálico. Por isso diferenças pequenas já importam:

- Os fabricantes recomendam fotografar **as três fases no mesmo momento** e procurar um perfil
  diferente dos outros.
- Variações de 5 a 10 °C ao longo do corpo, **iguais nas três fases**, são normais: a tensão não
  se distribui de forma uniforme.
- **10 °C a mais na parte superior** indicam aquecimento local anormal.
- Em varistores degradados, o invólucro esquenta cerca de 4 °C, e a diferença global chega a
  2,5–3,7 °C.
- A confirmação é pela **corrente de fuga resistiva** (IEC 60099-5).

Faixas adotadas no Pyron para para-raios e isoladores (ΔT contra a fase semelhante), a
confirmar com fabricante e termografista:
- **2 °C:** atenção;
- **5 °C:** programar a medição da corrente de fuga;
- **10 °C:** substituição urgente.

## 5. A solução no Pyron

1. **Biblioteca de componentes.** Cada classe (terminal, conexão, bucha, para-raio, isolador,
   tanque, cabo) tem MTA, fonte da MTA e tipo de aquecimento (resistivo, dielétrico ou óleo).
   Valores padrão das normas, editáveis por cliente e por fabricante.
2. **Três avaliações por região:**
   - **absoluta:** T projetada contra a MTA (percentual e margem em °C);
   - **relativa:** ΔT contra a fase semelhante, com faixa própria para para-raios e isoladores;
   - **histórica:** tendência do mesmo componente nas inspeções anteriores, na fase de previsão.
3. **Severidade final:** a pior das avaliações aplicáveis, sempre dizendo qual critério a
   disparou e com quais números. Isso dá rastreabilidade.
4. **Resultado que orienta a manutenção**, além de "está quente":
   - percentual da MTA;
   - quanto de carga ainda cabe até a MTA;
   - ação e prazo;
   - com histórico, o tempo estimado até a MTA.
5. **Entradas mínimas para avaliação absoluta:** temperatura ambiente e carga no momento. Sem
   elas, o sistema mostra a avaliação relativa e marca a absoluta como "incompleta", em vez de
   inventar números.

## Fontes

- [ABNT NBR 15866 (Target)](https://www.target.com.br/produtos/normas-tecnicas/42015/nbr15866-ensaio-nao-destrutivo-termografia-metodologia-de-avaliacao-de-temperatura-de-trabalho-de-equipamentos-em-sistemas-eletricos)
- [ABENDI, CE-058 Termografia: plano de trabalho](https://www1.abendi.org.br/wp-content/uploads/2024/01/CE-058-000-011-Termografia-Plano-de-Trabalho-14-12-2023.pdf)
- [O Setor Elétrico, fascículo "Inspeção de instalações elétricas", cap. VII: Ensaios termográficos](https://www.osetoreletrico.com.br/wp-content/uploads/2014/08/ed-102_Fasciculo_Cap-VII-Inspecao-de-instalacoes-eletricas.pdf)
- [Termografia quantitativa como ferramenta de gestão de ativos (CEMIG)](https://sites.google.com/site/tqfgasep/capitulo-7)
- [Termografia infravermelha em subestações de alta tensão desabrigadas](https://www.researchgate.net/publication/276293466_TERMOGRAFIA_INFRAVERMELHA_em_Subestacoes_de_Alta_Tensao_Desabrigadas)
- [UFRJ: aplicação da termografia na manutenção de instalações elétricas industriais](http://repositorio.poli.ufrj.br/monografias/monopoli10031777.pdf)
- [UNIFEI: termografia infravermelha (dissertação)](https://repositorio.unifei.edu.br/jspui/bitstream/123456789/3833/1/Disserta%C3%A7%C3%A3o_200632852.pdf)
- [IEC 62271-1: ensaio de corrente contínua em painéis de média tensão](https://www.atlantis-press.com/article/125994120.pdf)
- [IEC 60137:2017](https://webstore.iec.ch/en/publication/29183)
- [ONS: elevação de temperatura de transformadores em sobrecarga](https://www.ons.org.br/AcervoDigitalDocumentosEPublicacoes/ONSNT038-2014_ElevacaoTemperatura_transformadoresemsobrecarga.pdf)
- [NR-10 (Ministério do Trabalho)](https://www.gov.br/trabalho-e-emprego/pt-br/acesso-a-informacao/participacao-social/conselhos-e-orgaos-colegiados/comissao-tripartite-partitaria-permanente/arquivos/normas-regulamentadoras/nr-10.pdf)
- [Prontuário de instalações elétricas NR-10](https://www.manutencaoemfoco.com.br/prontuario-de-instalacoes-eletricas-nr-10/)
- [Laudo NR-10: obrigatoriedade e periodicidade](https://base.ohub.com.br/facilities/conformidade-e-seguranca-predial/documentacao-predial/artigos/laudo-tecnico-de-instalacoes-eletricas-nr-10-obrigatorio-periodicidade)
- [INMR: monitoramento da condição de para-raios](https://www.inmr.com/monitoring-condition-surge-arresters/)
- [Fluke: diagnóstico de para-raios de alta tensão](https://www.fluke.com/en-us/learn/blog/power-quality/diagnose-high-voltage-surge-arresters)
- [Termovision diagnostics of metal oxide surge arresters](https://www.researchgate.net/publication/234035016_Termovision_diagnostics_of_metal_oxide_surge_arresters)
- [Megger: inspeção de pontos quentes](https://www.megger.com/en/et-online/december-2021/Electrical-hot-spot-inspection-and-preventative-maintenance)
- [Conducting Thermographic Inspections in Electrical Substations: A Survey (MDPI)](https://doi.org/10.3390/app122010381)
- [Thermographic Measurements in Electrical Power Engineering: how to interpret the results (MDPI)](https://www.mdpi.com/2076-3417/14/11/4920)
