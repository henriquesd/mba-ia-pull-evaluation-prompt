"""
Testes automatizados para validação de prompts.
"""
import re
import pytest
import yaml
import sys
from pathlib import Path

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils import validate_prompt_structure

PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "bug_to_user_story_v2.yml"
PROMPT_KEY = "bug_to_user_story_v2"


def load_prompts(file_path: str):
    """Carrega prompts do arquivo YAML."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def prompt():
    """Retorna o bloco do prompt otimizado v2."""
    data = load_prompts(PROMPT_FILE)
    assert data is not None, f"Não foi possível carregar {PROMPT_FILE}"
    assert PROMPT_KEY in data, f"Chave '{PROMPT_KEY}' ausente em {PROMPT_FILE}"
    return data[PROMPT_KEY]


@pytest.fixture(scope="module")
def full_text(prompt):
    """Texto completo (system + user) em minúsculas, para buscas."""
    return f"{prompt.get('system_prompt', '')}\n{prompt.get('user_prompt', '')}".lower()


class TestPrompts:
    def test_prompt_has_system_prompt(self, prompt):
        """Verifica se o campo 'system_prompt' existe e não está vazio."""
        assert "system_prompt" in prompt, "Campo 'system_prompt' não existe"

        system_prompt = prompt["system_prompt"]
        assert isinstance(system_prompt, str), "'system_prompt' deve ser texto"
        assert system_prompt.strip(), "'system_prompt' está vazio"
        assert len(system_prompt.strip()) > 200, (
            "'system_prompt' é curto demais para um prompt otimizado"
        )

    def test_prompt_has_role_definition(self, full_text):
        """Verifica se o prompt define uma persona (ex: "Você é um Product Manager")."""
        assert re.search(r"voc[eê]\s+[eé]\s+(um|uma|o|a)\s+", full_text), (
            "O prompt não define uma persona ('Você é um ...')"
        )
        personas = ["product manager", "product owner", "engenheiro", "analista"]
        assert any(p in full_text for p in personas), (
            f"Nenhuma persona reconhecida encontrada. Esperado uma de: {personas}"
        )

    def test_prompt_mentions_format(self, full_text):
        """Verifica se o prompt exige formato Markdown ou User Story padrão."""
        assert "como um" in full_text, "O prompt não exige o template 'Como um ...'"
        assert "eu quero" in full_text, "O prompt não exige a parte 'eu quero ...'"
        assert "para que" in full_text, "O prompt não exige a parte 'para que ...'"

        assert re.search(r"crit[eé]rios de aceita[cç][aã]o", full_text), (
            "O prompt não pede a seção 'Critérios de Aceitação'"
        )

        given_when_then = ["dado que", "quando", "ent[aã]o"]
        for token in given_when_then:
            assert re.search(token, full_text), (
                f"O prompt não usa o formato Given-When-Then (faltou '{token}')"
            )

    def test_prompt_has_few_shot_examples(self, prompt):
        """Verifica se o prompt contém exemplos de entrada/saída (técnica Few-shot)."""
        system_prompt = prompt["system_prompt"].lower()

        input_markers = len(re.findall(r"^\s*relato:", system_prompt, flags=re.MULTILINE))
        output_markers = len(re.findall(r"^\s*resposta:", system_prompt, flags=re.MULTILINE))

        assert input_markers >= 2, (
            f"Few-shot exige ao menos 2 entradas de exemplo, encontradas: {input_markers}"
        )
        assert output_markers >= 2, (
            f"Few-shot exige ao menos 2 saídas de exemplo, encontradas: {output_markers}"
        )
        assert input_markers == output_markers, (
            "Cada exemplo de entrada deve ter uma saída correspondente "
            f"(entradas: {input_markers}, saídas: {output_markers})"
        )

        techniques = [t.lower() for t in prompt.get("techniques_applied", [])]
        assert any("few-shot" in t or "few shot" in t for t in techniques), (
            "Few-shot Learning não está listado em 'techniques_applied'"
        )

    def test_prompt_no_todos(self, prompt):
        """Garante que você não esqueceu nenhum `[TODO]` no texto."""
        for field in ("description", "system_prompt", "user_prompt"):
            value = str(prompt.get(field, ""))
            assert "TODO" not in value.upper(), (
                f"O campo '{field}' ainda contém um TODO pendente"
            )

    def test_minimum_techniques(self, prompt):
        """Verifica (através dos metadados do yaml) se pelo menos 2 técnicas foram listadas."""
        techniques = prompt.get("techniques_applied", [])

        assert isinstance(techniques, list), "'techniques_applied' deve ser uma lista"
        assert len(techniques) >= 2, (
            f"Mínimo de 2 técnicas requeridas, encontradas: {len(techniques)}"
        )
        assert all(str(t).strip() for t in techniques), (
            "Há técnicas vazias na lista 'techniques_applied'"
        )

        # Reaproveita a validação oficial do projeto
        is_valid, errors = validate_prompt_structure(prompt)
        assert is_valid, f"validate_prompt_structure falhou: {errors}"


class TestPromptTemplate:
    def test_prompt_declares_bug_report_variable(self, prompt):
        """A variável {bug_report} precisa existir para o evaluate.py funcionar."""
        user_prompt = str(prompt.get("user_prompt", ""))
        assert "{bug_report}" in user_prompt, (
            "'user_prompt' precisa conter a variável {bug_report}"
        )

    def test_template_renders_without_stray_braces(self, prompt):
        """Chaves soltas quebrariam o template f-string do LangChain no push."""
        from langchain_core.prompts import ChatPromptTemplate

        chat_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", prompt["system_prompt"]),
                ("human", prompt["user_prompt"]),
            ]
        )

        assert set(chat_prompt.input_variables) == {"bug_report"}, (
            f"Variáveis inesperadas no template: {chat_prompt.input_variables}"
        )

        rendered = chat_prompt.format(bug_report="Botão de login não responde.")
        assert "Botão de login não responde." in rendered


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
