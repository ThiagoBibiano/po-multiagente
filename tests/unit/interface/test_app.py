import gc
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import gradio as gr
import pytest

from po_multiagente import iniciar
from po_multiagente.dominio import MotivoTratamento, Solicitacao
from po_multiagente.interface import Assistente, Etapa, Resultado
from po_multiagente.interface.app import (
    carregar_exemplo,
    construir_app,
    formatar_execucao,
    formatar_explicacao,
    formatar_solicitacoes,
)
from po_multiagente.llm import ErroLLM, LLMRoteirizado

# Montar a tela abre um event loop e sockets que o próprio Gradio não fecha. O
# aviso sai quando o coletor de lixo os recolhe; a coleta é forçada aqui, dentro
# do teste marcado, para o aviso não vazar para o teste seguinte.
sem_aviso_do_gradio = pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")


@pytest.fixture(autouse=True)
def _coletar_lixo() -> Iterator[None]:
    yield
    gc.collect()


@sem_aviso_do_gradio
def test_app_monta_sem_abrir_servidor() -> None:
    app = construir_app(lambda: Assistente(LLMRoteirizado({})), modelo="gemini-3.5-flash-lite")
    assert isinstance(app, gr.Blocks)


def test_exemplo_da_marcenaria() -> None:
    descricao, arquivos = carregar_exemplo()
    assert "mesas e cadeiras" in descricao
    assert [Path(a).name for a in arquivos] == ["produtos.csv", "recursos.csv"]
    assert all(Path(a).is_file() for a in arquivos)
    # O Gradio recusa devolver arquivos fora da pasta de trabalho e da temporária,
    # e o pacote instalado fica fora das duas (no Colab, em dist-packages).
    temporaria = Path(tempfile.gettempdir()).resolve()
    assert all(temporaria in Path(a).resolve().parents for a in arquivos)


def test_solicitacoes_numeradas_e_so_sobre_dados() -> None:
    solicitacao = Solicitacao(
        id="s1",
        parametro_id="cap",
        arquivo="horas.csv",
        coluna="Horas",
        motivo=MotivoTratamento.GRANULARIDADE,
        forma_esperada="Horas do mês",
    )
    texto = formatar_solicitacoes(Etapa("solicitacoes", solicitacoes=(solicitacao,)))
    assert "1. Planilha `horas.csv`, coluna `Horas`: o dado está em outro período" in texto
    assert "Como deve ficar: Horas do mês" in texto
    assert "mesma ordem" in texto


def test_explicacao_ou_motivo_da_falha() -> None:
    com = Resultado(
        explicacao="Produza 55 mesas.", status="otimo", valor_objetivo=4950.0, falha=None
    )
    sem = Resultado(explicacao=None, status=None, valor_objetivo=None, falha="modelador: erro")
    assert formatar_explicacao(com) == "Produza 55 mesas."
    assert "Não foi possível chegar a uma resposta" in formatar_explicacao(sem)
    assert "modelador: erro" in formatar_explicacao(sem)
    assert "Valor do objetivo: 4950" in formatar_execucao(com)


def test_iniciar_exige_chave(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ErroLLM, match="GEMINI_API_KEY"):
        iniciar()


@sem_aviso_do_gradio
def test_iniciar_abre_a_interface(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[dict[str, Any]] = []
    monkeypatch.setenv("GEMINI_API_KEY", "chave-de-teste")
    monkeypatch.setattr(gr.Blocks, "launch", lambda _self, **kwargs: chamadas.append(kwargs))
    iniciar()
    assert chamadas == [{"share": False, "show_error": True}]
