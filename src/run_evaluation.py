"""
Runner da avaliação com rate limiting e revezamento de modelos.

Por que este arquivo existe:

O tier gratuito do Gemini hoje permite, POR MODELO:
  - 5 requisições por minuto
  - 20 requisições por dia

O `evaluate.py` dispara 4 chamadas por exemplo (1 geração + 3 avaliações), ou
seja 60 chamadas para os 15 bugs do dataset. Isso não cabe em nenhum modelo
sozinho: ao estourar, as chamadas viram erro 429, os scores viram 0.0 e o
relatório parece dizer "prompt ruim" quando na verdade é "cota acabou".

Este runner resolve os dois problemas sem tocar em `evaluate.py`,
`metrics.py` ou `utils.py` (que o desafio proíbe alterar). Ele apenas
substitui `utils.get_llm` por uma versão que:

  1. aplica um rate limiter POR MODELO, respeitando as 5 req/min;
  2. usa um modelo fixo para a geração e reveza os demais nas avaliações,
     somando cota diária suficiente para as 60 chamadas;
  3. troca de modelo sozinha quando a cota diária de um deles acaba.

Uso (a partir da raiz do repositório):

    python src/run_evaluation.py

Configuração opcional no .env:

    GEMINI_REQUESTS_PER_MINUTE=4
    GEMINI_MODEL_POOL=gemini-3.8-flash,gemini-3.5-flash,gemini-3.1-flash-lite

O primeiro modelo da lista faz as gerações; os demais revezam as avaliações.
"""

import os
import sys
import time
from itertools import cycle
from dotenv import load_dotenv

load_dotenv()

# Windows: o console usa cp1252 e quebra ao imprimir emoji dos utils/evaluate.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from langchain_core.rate_limiters import InMemoryRateLimiter

import utils

# Free tier: o teto real é 5 req/min por modelo. 4 deixa margem.
REQUESTS_PER_MINUTE = float(os.getenv("GEMINI_REQUESTS_PER_MINUTE", "4"))

# 0 = nao insiste no mesmo modelo; preferimos trocar de modelo na hora.
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "0"))

# Quantas voltas completas dar no pool antes de desistir.
MINUTE_QUOTA_ROUNDS = int(os.getenv("GEMINI_QUOTA_ROUNDS", "8"))

# Espera entre voltas, para a cota por minuto se recompor.
MINUTE_QUOTA_WAIT = float(os.getenv("GEMINI_QUOTA_WAIT_SECONDS", "20"))

DEFAULT_POOL = (
    "gemini-3.8-flash,"
    "gemini-3.5-flash,"
    "gemini-3.1-flash-lite,"
    "gemini-3.5-flash-lite,"
    "gemini-2.5-flash-lite,"
    "gemini-3-flash-preview"
)

MODEL_POOL = [
    m.strip() for m in os.getenv("GEMINI_MODEL_POOL", DEFAULT_POOL).split(",") if m.strip()
]

# Primeiro modelo gera as user stories; os outros revezam as avaliações.
GENERATION_MODEL = MODEL_POOL[0]
EVAL_POOL = MODEL_POOL[1:] or MODEL_POOL

_original_get_llm = utils.get_llm

# Cada modelo tem sua própria cota por minuto, logo seu próprio balde.
_rate_limiters = {}

# Modelos cuja cota DIÁRIA já acabou nesta execução.
_exhausted = set()

# Quantas chamadas cada modelo recebeu (só para o resumo no fim).
_call_counts = {}

# Quantas vezes cada modelo bateu na cota por minuto.
_minute_blocked = {}

_eval_cycle = cycle(EVAL_POOL)


class AllModelsExhausted(BaseException):
    """
    Todos os modelos do pool ficaram sem cota diária.

    Herda de BaseException, e não de Exception, de propósito: evaluate.py e
    metrics.py fazem `except Exception` e transformam qualquer falha em score
    0.0, o que disfarçaria o erro de cota como "prompt ruim" e ainda deixaria
    o loop martelar os 15 exemplos. Assim a execução aborta de verdade.
    """


def _is_quota_error(error: BaseException) -> bool:
    text = str(error)
    return "429" in text or "ResourceExhausted" in text or "quota" in text.lower()


def _is_daily_quota_error(error: BaseException) -> bool:
    return "PerDayPerProjectPerModel" in str(error)


def _limiter_for(model_name: str) -> InMemoryRateLimiter:
    """Um balde de tokens por modelo: as cotas por minuto são independentes."""
    if model_name not in _rate_limiters:
        _rate_limiters[model_name] = InMemoryRateLimiter(
            requests_per_second=REQUESTS_PER_MINUTE / 60.0,
            check_every_n_seconds=0.1,
            max_bucket_size=1,
        )
    return _rate_limiters[model_name]


def _build_llm(model_name: str, temperature: float):
    """LLM real, sem wrapper, já com freio e retentativas."""
    llm = _original_get_llm(model=model_name, temperature=temperature)

    try:
        llm.rate_limiter = _limiter_for(model_name)
        llm.max_retries = MAX_RETRIES
    except Exception as e:  # provider sem suporte: segue sem o freio
        print(f"⚠️  Não foi possível aplicar o rate limiter em {model_name}: {e}")

    return llm


def _next_eval_model() -> str:
    """Próximo modelo vivo do rodízio de avaliação."""
    for _ in range(len(EVAL_POOL)):
        candidate = next(_eval_cycle)
        if candidate not in _exhausted:
            return candidate

    # Rodízio todo esgotado: tenta o modelo de geração como último recurso.
    if GENERATION_MODEL not in _exhausted:
        return GENERATION_MODEL

    raise AllModelsExhausted(
        "Todos os modelos do pool ficaram sem cota diária:\n"
        f"  {', '.join(MODEL_POOL)}\n\n"
        "Opções:\n"
        "  1. Acrescente outros modelos em GEMINI_MODEL_POOL no .env.\n"
        "  2. Espere o reset (meia-noite no horário do Pacífico).\n"
        "  3. Use OpenAI: LLM_PROVIDER=openai no .env."
    )


def _rotating_llm(lane: str, temperature: float):
    """
    Devolve um LLM que troca de modelo sozinho ao esgotar a cota diária.

    lane='generation' fica grudado em um modelo (são 15 chamadas, cabem nas 20
    diárias). lane='eval' reveza a cada chamada, espalhando as 45 avaliações
    entre vários modelos.
    """
    # Casca descartável: é ela que entra no `prompt | llm` do evaluate.py.
    # As chamadas reais vão para instâncias internas, sem wrapper, evitando
    # recursão infinita.
    shell = _build_llm(GENERATION_MODEL if lane == "generation" else EVAL_POOL[0], temperature)

    state = {"model": None, "llm": None}

    def pick_model() -> str:
        if lane == "generation":
            if GENERATION_MODEL not in _exhausted:
                return GENERATION_MODEL
            return _next_eval_model()
        return _next_eval_model()

    def rotating_invoke(*args, **kwargs):
        # Uma volta completa no pool por rodada; entre rodadas, espera a cota
        # por minuto se recompor.
        for round_no in range(MINUTE_QUOTA_ROUNDS):
            if round_no:
                print(f"      ⏳ Todos os modelos bloqueados por minuto. "
                      f"Aguardando {MINUTE_QUOTA_WAIT:.0f}s...")
                time.sleep(MINUTE_QUOTA_WAIT)

            for _ in range(len(MODEL_POOL) + 1):
                if lane == "eval" or state["llm"] is None or state["model"] in _exhausted:
                    state["model"] = pick_model()
                    state["llm"] = _build_llm(state["model"], temperature)

                model_name = state["model"]

                try:
                    result = state["llm"].invoke(*args, **kwargs)
                    _call_counts[model_name] = _call_counts.get(model_name, 0) + 1
                    return result
                except AllModelsExhausted:
                    raise
                except Exception as e:
                    if not _is_quota_error(e):
                        raise

                    if _is_daily_quota_error(e):
                        # Cota do dia: o modelo sai de cena de vez.
                        print(f"      ⚠️  Cota DIÁRIA de {model_name} esgotada "
                              f"— removendo do pool.")
                        _exhausted.add(model_name)
                    else:
                        # Cota do minuto: o modelo volta a valer daqui a pouco,
                        # entao so pulamos para o proximo.
                        _minute_blocked[model_name] = _minute_blocked.get(model_name, 0) + 1

                    state["llm"] = None

        raise AllModelsExhausted(
            "Sem modelos com cota disponível para completar a chamada."
        )

    # ChatGoogleGenerativeAI é um modelo Pydantic: atribuição normal levanta
    # '"ChatGoogleGenerativeAI" object has no field "invoke"'. object.__setattr__
    # instala o wrapper no __dict__ da instância, sombreando o método da classe.
    object.__setattr__(shell, "invoke", rotating_invoke)

    return shell


def _patched_get_llm(model=None, temperature: float = 0.0):
    """
    Substitui utils.get_llm.

    evaluate.py chama get_llm() sem argumento para gerar as user stories.
    metrics.py chama get_eval_llm(), que repassa model=EVAL_MODEL. É assim que
    separamos as duas pistas.
    """
    lane = "generation" if model is None else "eval"
    return _rotating_llm(lane, temperature)


def _print_usage_summary():
    if not _call_counts:
        return

    print("\n" + "-" * 50)
    print("Chamadas bem-sucedidas por modelo:")
    for model_name, count in sorted(_call_counts.items(), key=lambda kv: -kv[1]):
        flag = " (cota diária esgotada)" if model_name in _exhausted else ""
        print(f"  - {model_name}: {count}{flag}")
    print("-" * 50)


def main():
    provider = os.getenv("LLM_PROVIDER", "openai").lower()

    # get_eval_llm() resolve utils.get_llm em tempo de chamada, então o patch
    # abaixo vale para as métricas também. Precisa vir ANTES de importar
    # evaluate, que faz "from utils import get_llm as get_configured_llm".
    if provider == "google":
        utils.get_llm = _patched_get_llm

        print(f"⏱️  Rate limiting: {REQUESTS_PER_MINUTE:.0f} req/min por modelo")
        print(f"🔁 Geração:   {GENERATION_MODEL}")
        print(f"🔁 Avaliação: revezando entre {', '.join(EVAL_POOL)}")
        print(f"📦 Cota total do pool: ~{len(MODEL_POOL) * 20} chamadas/dia "
              f"(necessárias: 60)\n")
    else:
        print("⏱️  Provider não é Google: rodando sem rate limiting.\n")

    import evaluate

    try:
        result = evaluate.main()
        _print_usage_summary()
        return result
    except AllModelsExhausted as e:
        _print_usage_summary()
        print(f"\n{'=' * 70}")
        print(f"❌ {e}")
        print(f"{'=' * 70}")
        print("\nAs notas desta execução NÃO valem — foram zeradas por cota,")
        print("não por qualidade do prompt.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
