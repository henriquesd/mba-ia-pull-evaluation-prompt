# Pull, Otimização e Avaliação de Prompts com LangChain e LangSmith

Desafio técnico do MBA em Engenharia de Software com IA (Full Cycle).

O projeto puxa um prompt de baixa qualidade do LangSmith Prompt Hub
(`leonanluppi/bug_to_user_story_v1`), refatora esse prompt com técnicas
avançadas de Prompt Engineering, publica a versão otimizada de volta no Hub e
avalia o resultado contra 15 relatos de bug usando 5 métricas com LLM-as-Judge.

**Meta de aprovação:** Helpfulness, Correctness, F1-Score, Clarity e Precision
todas `>= 0.8`.

---

## Técnicas Aplicadas (Fase 2)

O prompt otimizado está em [`prompts/bug_to_user_story_v2.yml`](prompts/bug_to_user_story_v2.yml).

### Diagnóstico da v1

O prompt original tinha quatro problemas graves:

| Problema na v1 | Efeito nas métricas |
| --- | --- |
| `{bug_report}` duplicado no system **e** no user prompt | O modelo recebia o bug duas vezes e às vezes respondia duas vezes — derruba Precision e Clarity |
| Nenhuma persona definida ("Você é um assistente") | Saída genérica, sem vocabulário de produto — derruba Helpfulness |
| Nenhum formato de saída especificado | Cada resposta saía com uma estrutura diferente da referência — derruba F1-Score |
| Nenhum exemplo, nenhuma regra, nenhum edge case | Sem âncora de estilo, o modelo inventava seções e detalhes — derruba Precision |

### Técnicas escolhidas

#### 1. Few-shot Learning (obrigatória)

**Por quê:** as métricas comparam a saída com uma referência (`ground truth`) de
formato muito específico. Descrever o formato em palavras não é suficiente —
mostrar exemplos reais é o que faz o modelo copiar o formato exato.

**Como apliquei:** três pares entrada/saída dentro do system prompt, um para
cada nível de complexidade do dataset (simples, médio, complexo), cada um
marcado com `Relato:` e `Resposta:`.

```
### Exemplo 1 - relato SIMPLES

Relato:
Campo de email aceita texto sem arroba, permitindo cadastros invalidos.

Resposta:
Como um usuario criando uma conta, eu quero que o sistema valide meu email
corretamente, para que eu nao insira um endereco invalido por engano.

Criterios de Aceitacao:
- Dado que estou no formulario de cadastro
- Quando digito um email sem o caractere arroba
- Entao devo ver uma mensagem de erro
...
```

#### 2. Role Prompting

**Por quê:** a métrica de Helpfulness e o tom das referências são de documentação
ágil profissional. Uma persona sênior e específica muda o vocabulário inteiro da
resposta ("critério testável", "valor de negócio") sem precisar listar isso regra
a regra.

**Como apliquei:**

```
Voce e um Product Manager senior com 10 anos de experiencia em times ageis
de produtos digitais. Voce e especialista em traduzir relatos de bug ... em
User Stories acionaveis que o time consegue estimar e testar sem precisar
fazer perguntas de volta.
```

#### 3. Chain of Thought (CoT)

**Por quê:** transformar bug em user story exige inferência — quem é a persona
afetada, qual o comportamento correto (não o defeito), qual o valor de negócio.
Sem raciocínio explícito o modelo repete o bug em vez de reformulá-lo, o que
destrói o F1-Score contra a referência.

**Como apliquei:** cinco etapas de raciocínio **interno**, explicitamente não
exibidas na resposta — isso preserva o Clarity, que penalizaria o "pensamento em
voz alta" como informação redundante.

```
## Raciocinio interno (pense passo a passo, NUNCA mostre estes passos)

1. QUEM: identifique a persona real afetada pelo bug ...
2. O QUE: descreva o comportamento CORRETO desejado - nunca o defeito.
3. POR QUE: identifique o valor de negocio concreto ...
4. COMO VALIDAR: derive de 4 a 6 criterios de aceitacao testaveis ...
5. COMPLEXIDADE: classifique o relato como SIMPLES, MEDIO ou COMPLEXO ...
```

#### 4. Skeleton of Thought

**Por quê:** o dataset tem três formatos de referência diferentes. Bug simples
recebe só story + critérios; bug médio ganha `Contexto Técnico`; bug complexo
ganha seções `=== ... ===` com tasks técnicas. Um único formato fixo perderia
pontos nos dois extremos: informação demais nos simples (Precision cai) ou de
menos nos complexos (F1-Score cai).

**Como apliquei:** três esqueletos de saída, escolhidos pela etapa 5 do CoT.

```
## Esqueleto de saida - nivel MEDIO

Igual ao nivel SIMPLES, e ao final acrescente uma secao:

Contexto Tecnico:
- de 3 a 5 bullets com os fatos tecnicos que ESTAO no relato ...
  Nunca invente dados que o relato nao trouxe.
```

### Outros cuidados

- **System vs User prompt:** o system prompt carrega persona, regras, esqueletos
  e exemplos; o user prompt carrega **apenas** o `{bug_report}`. Isso elimina a
  duplicação da v1.
- **Anti-alucinação:** regra explícita de usar só o que está no relato, com
  marcadores entre colchetes (`[nome do gateway de pagamento]`) quando falta
  informação — exatamente o que a referência do dataset faz.
- **Edge cases:** relato vago, vários bugs no mesmo texto, texto que não é bug,
  relato em outro idioma e relato com dado sensível.
- **Restrição técnica:** o arquivo YAML não pode conter chaves `{ }` além de
  `{bug_report}`, porque o LangChain trata o texto como template f-string. O
  teste `test_template_renders_without_stray_braces` protege contra isso.

---

## Resultados Finais

Avaliação executada em 14/09/2026 sobre os 15 exemplos de
`datasets/bug_to_user_story.jsonl`.

**STATUS: APROVADO — todas as 5 métricas >= 0.8**

**Prompt público no Hub:**
https://smith.langchain.com/prompts/bug_to_user_story_v2/80fcb0c9?organizationId=12961472-f400-4233-9489-871f15840b65

**Projeto no LangSmith:** `prompt-optimization-challenge-resolved`
**Dataset de avaliação:** `prompt-optimization-challenge-resolved-eval` (15 exemplos)

### Tabela comparativa: v1 (ruim) vs v2 (otimizado)

| Métrica | v1 (referência) | v2 (medido) | Meta | Status |
| --- | --- | --- | --- | --- |
| Helpfulness | 0.45 | **0.90** | >= 0.8 | ✅ |
| Correctness | 0.52 | **0.91** | >= 0.8 | ✅ |
| F1-Score | 0.48 | **0.90** | >= 0.8 | ✅ |
| Clarity | 0.50 | **0.89** | >= 0.8 | ✅ |
| Precision | 0.46 | **0.91** | >= 0.8 | ✅ |
| **Média geral** | 0.48 | **0.9008** | >= 0.8 | ✅ |

> Os números da coluna **v1** são os valores ilustrativos do enunciado do
> desafio, não uma medição própria: o `src/evaluate.py` avalia apenas
> `{username}/bug_to_user_story_v2`. A coluna **v2** é medição real desta
> execução.

### Notas por exemplo (v2)

| # | F1 | Clarity | Precision |
| --- | --- | --- | --- |
| 1 | 0.92 | 0.45 | 0.80 |
| 2 | 0.91 | 0.95 | 0.93 |
| 3 | 0.90 | 0.95 | 0.93 |
| 4 | 0.81 | 0.85 | 0.97 |
| 5 | 0.77 | 0.85 | 1.00 |
| 6 | 0.92 | 0.95 | 0.80 |
| 7 | 0.97 | 0.95 | 0.95 |
| 8 | 0.90 | 1.00 | 0.93 |
| 9 | 0.82 | 0.90 | 0.87 |
| 10 | 0.87 | 0.95 | 0.87 |
| 11 | 1.00 | 0.85 | 0.93 |
| 12 | 0.80 | 0.95 | 0.83 |
| 13 | 0.97 | 0.80 | 1.00 |
| 14 | 0.97 | 0.95 | 1.00 |
| 15 | 1.00 | 0.95 | 0.83 |

Ponto fraco conhecido: o exemplo 1 tirou Clarity 0.45, bem abaixo dos demais
(todos >= 0.80). É o melhor candidato para a próxima iteração.

### Screenshots

> Salve as imagens em `docs/` e referencie aqui.

- `docs/langsmith-dataset.png` — dataset de avaliação com os 15 exemplos
- `docs/langsmith-scores.png` — execuções da v2 com todas as notas >= 0.8
- `docs/langsmith-tracing.png` — tracing detalhado de pelo menos 3 exemplos

### Registro de iterações

A v2 passou em todas as métricas na primeira avaliação que conseguiu rodar por
completo. As execuções anteriores falharam por **cota da API**, não por
qualidade do prompt — todas as notas vinham 0.00 porque as chamadas nem
chegavam ao modelo.

| # | O que aconteceu | Diagnóstico | Resultado |
| --- | --- | --- | --- |
| 1 | Todas as métricas 0.00 | `gemini-2.5-flash` foi descontinuado para contas novas (HTTP 404) | Troquei para `gemini-3.6-flash` |
| 2 | 43 erros HTTP 429, métricas 0.00 | Cota **por minuto** estourada; onde passou, as notas já vinham 0.90-1.00 | Criei `src/run_evaluation.py` com rate limiting |
| 3 | 50 erros HTTP 429 | O teto real é **5 req/min**, não os 15 do enunciado; e minha trava estava em 8/min | Baixei para 4 req/min |
| 4 | Cota **diária** esgotada | O free tier dá **20 req/dia por modelo**, e a avaliação precisa de 60 | Implementei revezamento entre modelos |
| 5 | **APROVADO — média 0.9008** | Revezamento distribuiu as 60 chamadas por 5 modelos | Todas as métricas >= 0.8 |

Distribuição das chamadas na execução aprovada:

```
gemini-3.1-flash-lite:  22
gemini-3.5-flash-lite:  12
gemini-2.5-flash-lite:  11
gemini-3-flash-preview: 11
gemini-3.8-flash:        4  (cota diária esgotada, failover automático)
```

---

## Como Executar

### Pré-requisitos

- Python 3.9 ou superior
- Conta no [LangSmith](https://smith.langchain.com) (API key)
- Uma chave de LLM: [OpenAI](https://platform.openai.com/api-keys) **ou**
  [Google AI Studio](https://aistudio.google.com/app/apikey) (Gemini tem tier
  gratuito: 15 req/min, 1500 req/dia)

### 1. Ambiente virtual e dependências

```bash
python -m venv venv

# Linux / macOS
source venv/bin/activate
# Windows (PowerShell)
venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configurar credenciais

```bash
cp .env.example .env
```

Preencha o `.env`:

```ini
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=<sua chave do LangSmith>
LANGSMITH_PROJECT=prompt-optimization-challenge-resolved

# Seu handle no Hub (não é o e-mail). Publique qualquer prompt no LangSmith
# Hub, abra-o e clique no ícone de cadeado para descobrir.
USERNAME_LANGSMITH_HUB=<seu username>

# Escolha UM provider
GOOGLE_API_KEY=<sua chave do Google AI Studio>
LLM_PROVIDER=google
LLM_MODEL=gemini-2.5-flash
EVAL_MODEL=gemini-2.5-flash

# Alternativa OpenAI (custo estimado ~$1-5)
# OPENAI_API_KEY=<sua chave da OpenAI>
# LLM_PROVIDER=openai
# LLM_MODEL=gpt-4o-mini
# EVAL_MODEL=gpt-4o
```

O `.env` está no `.gitignore` — nunca faça commit dele.

### 3. Rodar o projeto

Execute sempre a partir da raiz do repositório.

```bash
# Fase 1 - puxar o prompt ruim do Hub
python src/pull_prompts.py

# Fase 2 - o prompt otimizado já está em prompts/bug_to_user_story_v2.yml
#          (edite esse arquivo se quiser iterar)

# Fase 3 - publicar a v2 no Hub, como prompt PÚBLICO
python src/push_prompts.py

# Fase 4 - avaliar contra os 15 bugs do dataset
python src/run_evaluation.py

# Testes de validação do prompt
pytest tests/test_prompts.py -v
```

> **Windows:** o console usa cp1252 e quebra ao imprimir os emojis do
> `evaluate.py`. Antes de rodar, defina:
>
> ```powershell
> $env:PYTHONIOENCODING = "utf-8"
> ```
>
> Os scripts `pull_prompts.py`, `push_prompts.py` e `run_evaluation.py` já se
> protegem sozinhos.

#### Por que `run_evaluation.py` e não `evaluate.py` direto

O `src/evaluate.py` roda, mas no free tier do Gemini ele não termina. Os
limites atuais, **por modelo**, são:

- **5 requisições por minuto**
- **20 requisições por dia**

A avaliação precisa de **60 chamadas** (1 geração + 3 métricas, vezes 15
exemplos). Rodando direto, as chamadas viram HTTP 429, as métricas viram 0.00
e o relatório parece dizer "prompt ruim" quando na verdade é "cota acabou".

`src/run_evaluation.py` é um arquivo **novo** — ele não altera `evaluate.py`,
`metrics.py` nem `utils.py`, que o desafio proíbe modificar. Ele só substitui
`utils.get_llm` por uma versão que:

1. aplica um rate limiter **por modelo**, respeitando as 5 req/min;
2. usa um modelo fixo para gerar e reveza os demais nas avaliações, somando
   cota diária suficiente para as 60 chamadas;
3. troca de modelo sozinha quando um deles esgota a cota.

Ajustes opcionais no `.env`:

```ini
GEMINI_REQUESTS_PER_MINUTE=4
GEMINI_MODEL_POOL=gemini-3.8-flash,gemini-3.5-flash,gemini-3.1-flash-lite,gemini-3.5-flash-lite,gemini-2.5-flash-lite,gemini-3-flash-preview
```

O primeiro modelo da lista faz as gerações; os demais revezam as avaliações.

Quem usar **OpenAI** não precisa de nada disso — `run_evaluation.py` detecta o
provider e roda sem freio.

### 4. Ciclo de iteração

Se alguma métrica ficar abaixo de 0.8:

1. Abra o tracing no LangSmith e leia o `reasoning` do avaliador
2. Ajuste `prompts/bug_to_user_story_v2.yml`
3. `pytest tests/test_prompts.py` (garante que o template não quebrou)
4. `python src/push_prompts.py`
5. `python src/run_evaluation.py`

Como ler as métricas baixas:

| Métrica baixa | Causa provável | Onde mexer |
| --- | --- | --- |
| F1-Score | Faltam informações que a referência tem | Critérios de aceitação: aumente a cobertura |
| Precision | O modelo inventou ou divagou | Reforce as regras anti-alucinação e corte seções extras |
| Clarity | Resposta longa, redundante ou desorganizada | Enxugue o esqueleto de saída |
| Helpfulness | Média de Clarity + Precision | Resolva as duas acima |
| Correctness | Média de F1 + Precision | Resolva as duas acima |

---

## Estrutura do projeto

```
mba-ia-pull-evaluation-prompt/
├── .env.example                    # Template das variáveis de ambiente
├── requirements.txt                # Dependências Python
├── README.md                       # Este arquivo
│
├── prompts/
│   ├── bug_to_user_story_v1.yml    # Prompt inicial (baixa qualidade)
│   └── bug_to_user_story_v2.yml    # Prompt otimizado  ← implementado
│
├── datasets/
│   └── bug_to_user_story.jsonl     # 15 bugs (5 simples, 7 médios, 3 complexos)
│
├── src/
│   ├── pull_prompts.py             # Pull do LangSmith        ← implementado
│   ├── push_prompts.py             # Push ao LangSmith        ← implementado
│   ├── evaluate.py                 # Avaliação automática (pronto)
│   ├── run_evaluation.py           # Runner c/ cota       ← implementado
│   ├── metrics.py                  # 5 métricas (pronto)
│   └── utils.py                    # Funções auxiliares (pronto)
│
└── tests/
    └── test_prompts.py             # Testes de validação      ← implementado
```

## Testes

`tests/test_prompts.py` cobre os 6 testes obrigatórios do desafio mais 2 extras:

| Teste | O que garante |
| --- | --- |
| `test_prompt_has_system_prompt` | `system_prompt` existe, não está vazio e tem corpo real |
| `test_prompt_has_role_definition` | O prompt define uma persona ("Você é um Product Manager...") |
| `test_prompt_mentions_format` | Exige o template User Story + Critérios de Aceitação em Given-When-Then |
| `test_prompt_has_few_shot_examples` | Há pelo menos 2 pares `Relato:` / `Resposta:` e a técnica está nos metadados |
| `test_prompt_no_todos` | Nenhum `[TODO]` sobrou em `description`, `system_prompt` ou `user_prompt` |
| `test_minimum_techniques` | `techniques_applied` lista 2+ técnicas e passa em `validate_prompt_structure` |
| `test_prompt_declares_bug_report_variable` (extra) | `{bug_report}` está no `user_prompt`, senão o `evaluate.py` quebra |
| `test_template_renders_without_stray_braces` (extra) | O YAML vira um `ChatPromptTemplate` válido, sem chaves soltas |

```bash
pytest tests/test_prompts.py -v
```

<!-- generated with AI -->
