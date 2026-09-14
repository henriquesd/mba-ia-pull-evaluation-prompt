"""
Script para fazer push de prompts otimizados ao LangSmith Prompt Hub.

Este script:
1. Lê os prompts otimizados de prompts/bug_to_user_story_v2.yml
2. Valida os prompts
3. Faz push PÚBLICO para o LangSmith Hub
4. Adiciona metadados (tags, descrição, técnicas utilizadas)

SIMPLIFICADO: Código mais limpo e direto ao ponto.
"""

import os
import sys
from dotenv import load_dotenv
from langchain import hub
from langchain_core.prompts import ChatPromptTemplate
from utils import load_yaml, check_env_vars, print_section_header

load_dotenv()

# Windows: o console usa cp1252 e quebra ao imprimir emoji dos utils/evaluate.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Arquivo com o prompt otimizado
PROMPT_FILE = "prompts/bug_to_user_story_v2.yml"

# Chave raiz dentro do YAML == nome do repo no Hub
PROMPT_KEY = "bug_to_user_story_v2"


def build_chat_prompt(prompt_data: dict) -> ChatPromptTemplate:
    """
    Monta um ChatPromptTemplate a partir dos dados do YAML.

    O system prompt carrega persona, regras e exemplos few-shot.
    O user prompt carrega apenas a variável {bug_report}.

    Args:
        prompt_data: Dados do prompt

    Returns:
        ChatPromptTemplate pronto para push
    """
    system_prompt = prompt_data["system_prompt"]
    user_prompt = prompt_data.get("user_prompt") or "{bug_report}"

    return ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", user_prompt),
        ]
    )


def build_readme(prompt_data: dict) -> str:
    """Gera o README publicado junto do prompt no Hub."""
    techniques = "\n".join(f"- {t}" for t in prompt_data.get("techniques_applied", []))

    return (
        f"# {PROMPT_KEY}\n\n"
        f"{prompt_data.get('description', '')}\n\n"
        f"## Técnicas de Prompt Engineering aplicadas\n\n"
        f"{techniques}\n\n"
        f"## Variável de entrada\n\n"
        f"- `bug_report`: o relato de bug em texto livre.\n\n"
        f"Versão: {prompt_data.get('version', 'v2')}\n"
    )


def validate_prompt(prompt_data: dict) -> tuple[bool, list]:
    """
    Valida estrutura básica de um prompt (versão simplificada).

    Args:
        prompt_data: Dados do prompt

    Returns:
        (is_valid, errors) - Tupla com status e lista de erros
    """
    errors = []

    for field in ("description", "system_prompt", "version"):
        if not str(prompt_data.get(field, "")).strip():
            errors.append(f"Campo obrigatório faltando ou vazio: {field}")

    system_prompt = str(prompt_data.get("system_prompt", ""))
    user_prompt = str(prompt_data.get("user_prompt", ""))

    if "TODO" in system_prompt or "TODO" in user_prompt:
        errors.append("O prompt ainda contém marcadores [TODO]")

    if "{bug_report}" not in system_prompt and "{bug_report}" not in user_prompt:
        errors.append("A variável {bug_report} não aparece no prompt")

    techniques = prompt_data.get("techniques_applied", [])
    if len(techniques) < 2:
        errors.append(
            f"Mínimo de 2 técnicas requeridas em techniques_applied, encontradas: {len(techniques)}"
        )

    return (len(errors) == 0, errors)


def push_prompt_to_langsmith(prompt_name: str, prompt_data: dict) -> bool:
    """
    Faz push do prompt otimizado para o LangSmith Hub (PÚBLICO).

    Args:
        prompt_name: Nome do prompt
        prompt_data: Dados do prompt

    Returns:
        True se sucesso, False caso contrário
    """
    print(f"\nEnviando prompt: {prompt_name}")

    is_valid, errors = validate_prompt(prompt_data)
    if not is_valid:
        print("❌ Prompt inválido:")
        for error in errors:
            print(f"   - {error}")
        return False

    print("   ✓ Validação OK")

    try:
        chat_prompt = build_chat_prompt(prompt_data)
    except Exception as e:
        print(f"❌ Erro ao montar o ChatPromptTemplate: {e}")
        print("   Dica: chaves { } soltas no texto quebram o template f-string.")
        return False

    print(f"   ✓ Template montado (variáveis: {', '.join(chat_prompt.input_variables)})")

    try:
        url = hub.push(
            prompt_name,
            chat_prompt,
            new_repo_is_public=True,
            new_repo_description=prompt_data.get("description", ""),
            readme=build_readme(prompt_data),
            tags=list(prompt_data.get("tags", [])),
        )
    except Exception as e:
        print(f"❌ Erro ao fazer push: {e}")
        print("\nVerifique:")
        print("- LANGSMITH_API_KEY e USERNAME_LANGSMITH_HUB no .env")
        print("- Seu username do Hub está correto (é o handle, não o email)")
        return False

    print(f"   ✓ Push realizado com sucesso (público)")
    print(f"   ✓ URL: {url}")

    return True


def main():
    """Função principal"""
    print_section_header("PUSH DE PROMPTS OTIMIZADOS")

    if not check_env_vars(["LANGSMITH_API_KEY", "USERNAME_LANGSMITH_HUB"]):
        return 1

    username = os.getenv("USERNAME_LANGSMITH_HUB")

    prompts = load_yaml(PROMPT_FILE)
    if not prompts:
        print(f"❌ Não foi possível carregar {PROMPT_FILE}")
        return 1

    prompt_data = prompts.get(PROMPT_KEY)
    if not prompt_data:
        print(f"❌ Chave '{PROMPT_KEY}' não encontrada em {PROMPT_FILE}")
        return 1

    techniques = prompt_data.get("techniques_applied", [])
    print(f"Arquivo: {PROMPT_FILE}")
    print(f"Técnicas: {', '.join(techniques)}")

    prompt_name = f"{username}/{PROMPT_KEY}"

    if not push_prompt_to_langsmith(prompt_name, prompt_data):
        print("\n❌ Falha no push.")
        return 1

    print("\n✅ Push concluído com sucesso!")
    print("\nPróximos passos:")
    print("1. Confira o prompt em: https://smith.langchain.com/prompts")
    print("2. Confirme que ele está marcado como PÚBLICO")
    print("3. Execute a avaliação: python src/evaluate.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
