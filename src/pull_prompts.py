"""
Script para fazer pull de prompts do LangSmith Prompt Hub.

Este script:
1. Conecta ao LangSmith usando credenciais do .env
2. Faz pull dos prompts do Hub
3. Salva localmente em prompts/bug_to_user_story_v1.yml

SIMPLIFICADO: Usa serialização nativa do LangChain para extrair prompts.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from langchain import hub
from utils import save_yaml, check_env_vars, print_section_header

load_dotenv()

# Windows: o console usa cp1252 e quebra ao imprimir emoji dos utils/evaluate.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Prompt de baixa qualidade fornecido pelo desafio
SOURCE_PROMPT = "leonanluppi/bug_to_user_story_v1"

# Onde salvar o prompt puxado
OUTPUT_FILE = "prompts/bug_to_user_story_v1.yml"

# Chave raiz usada dentro do YAML
PROMPT_KEY = "bug_to_user_story_v1"


def extract_messages(prompt_template) -> dict:
    """
    Extrai system_prompt e user_prompt de um ChatPromptTemplate do LangChain.

    Args:
        prompt_template: Objeto retornado por hub.pull()

    Returns:
        Dicionário com as chaves 'system_prompt' e 'user_prompt'
    """
    extracted = {"system_prompt": "", "user_prompt": ""}

    messages = getattr(prompt_template, "messages", None)

    # PromptTemplate simples (não-chat): usa o template direto como system
    if not messages:
        extracted["system_prompt"] = getattr(prompt_template, "template", "")
        return extracted

    for message in messages:
        template = getattr(getattr(message, "prompt", None), "template", "")
        if not template:
            continue

        role = type(message).__name__.lower()

        if "system" in role:
            extracted["system_prompt"] = template
        elif "human" in role or "user" in role:
            extracted["user_prompt"] = template

    return extracted


def pull_prompts_from_langsmith():
    """
    Faz pull do prompt inicial do LangSmith Hub e salva em YAML.

    Returns:
        True se sucesso, False caso contrário
    """
    print(f"Puxando prompt do LangSmith Hub: {SOURCE_PROMPT}")

    try:
        prompt_template = hub.pull(SOURCE_PROMPT)
    except Exception as e:
        print(f"❌ Erro ao puxar '{SOURCE_PROMPT}': {e}")
        print("\nVerifique:")
        print("- LANGSMITH_API_KEY está configurada corretamente no .env")
        print("- Sua conexão com a internet está funcionando")
        print(f"- O prompt '{SOURCE_PROMPT}' continua público no Hub")
        return False

    print("   ✓ Prompt carregado com sucesso")

    messages = extract_messages(prompt_template)

    if not messages["system_prompt"]:
        print("❌ Não foi possível extrair o system_prompt do template.")
        return False

    input_variables = list(getattr(prompt_template, "input_variables", []))

    prompt_data = {
        PROMPT_KEY: {
            "description": "Prompt para converter relatos de bugs em User Stories",
            "system_prompt": messages["system_prompt"],
            "user_prompt": messages["user_prompt"],
            "version": "v1",
            "source": SOURCE_PROMPT,
            "input_variables": input_variables,
            "tags": ["bug-analysis", "user-story", "product-management"],
        }
    }

    if not save_yaml(prompt_data, OUTPUT_FILE):
        return False

    print(f"   ✓ Prompt salvo em: {OUTPUT_FILE}")
    print(f"   ✓ Variáveis de entrada: {', '.join(input_variables) or 'nenhuma'}")

    return True


def main():
    """Função principal"""
    print_section_header("PULL DE PROMPTS DO LANGSMITH HUB")

    if not check_env_vars(["LANGSMITH_API_KEY"]):
        return 1

    Path("prompts").mkdir(parents=True, exist_ok=True)

    if not pull_prompts_from_langsmith():
        print("\n❌ Falha ao puxar o prompt.")
        return 1

    print("\n✅ Pull concluído com sucesso!")
    print("\nPróximos passos:")
    print(f"1. Analise o prompt em {OUTPUT_FILE}")
    print("2. Crie sua versão otimizada em prompts/bug_to_user_story_v2.yml")
    print("3. Execute: python src/push_prompts.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
