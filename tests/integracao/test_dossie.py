"""Dossiê de uma execução completa (R5), com modelo roteirizado."""

import io
import json
import zipfile
from pathlib import Path

from po_multiagente.avaliacao.instancia import carregar_instancia
from po_multiagente.config import ConfiguracaoExecucao
from po_multiagente.experimento.calibracao import calibrar, executar_instancia
from po_multiagente.experimento.roteiro import roteiro_do_gabarito
from po_multiagente.rastreabilidade import Dossie, exportar_zip, montar_dossie, para_html
from tests.instancias import VALOR, criar_instancia

CONFIGURACAO = ConfiguracaoExecucao()


def _dossie(tmp_path: Path, semanal: bool = True) -> tuple[Path, Dossie]:
    pasta = criar_instancia(tmp_path / "inst", semanal=semanal)
    instancia = carregar_instancia(pasta)
    _, estado = executar_instancia(instancia, CONFIGURACAO, roteiro_do_gabarito(instancia))
    return pasta, montar_dossie(estado, CONFIGURACAO, [pasta / "dados", pasta / "dados_tratados"])


def test_dossie_reune_os_artefatos_da_execucao(tmp_path: Path) -> None:
    _, dossie = _dossie(tmp_path)
    assert dossie.resultado is not None
    assert dossie.resultado.valor_objetivo == VALOR
    assert dossie.especificacao is not None
    assert dossie.formulacao_latex
    assert dossie.pareceres
    assert dossie.explicacao is not None
    assert {c["agente"] for c in dossie.chamadas} == {"interpretador", "modelador", "explicador"}
    assert set(dossie.instrucoes_sha256) == {"interpretador", "modelador", "explicador"}
    assert dossie.versoes["solver"].startswith("pulp/cbc")
    assert dossie.dados_inalterados
    assert set(dossie.hashes_inicio) == {f.arquivo for f in dossie.especificacao.fontes}


def test_hash_final_acusa_planilha_alterada(tmp_path: Path) -> None:
    pasta, dossie = _dossie(tmp_path, semanal=False)
    arquivo = next(iter(dossie.hashes_inicio))
    (pasta / "dados" / arquivo).write_text("alterado\n", encoding="utf-8")
    estado = {"especificacao": dossie.especificacao}
    alterado = montar_dossie(estado, CONFIGURACAO, [pasta / "dados"])
    assert not alterado.dados_inalterados
    assert "ALTERADAS" in para_html(alterado)


def test_html_escapa_o_texto_do_usuario(tmp_path: Path) -> None:
    _, dossie = _dossie(tmp_path, semanal=False)
    html = para_html(type(dossie)(**{**dossie.__dict__, "descricao": "<script>alert(1)</script>"}))
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<h2>Validações</h2>" in html


def test_zip_tem_um_arquivo_por_artefato(tmp_path: Path) -> None:
    _, dossie = _dossie(tmp_path)
    with zipfile.ZipFile(io.BytesIO(exportar_zip(dossie))) as zip_:
        nomes = set(zip_.namelist())
        manifesto = json.loads(zip_.read("dossie/manifesto.json"))
        chamadas = zip_.read("dossie/chamadas.jsonl").decode().splitlines()
    assert {
        "dossie/index.html",
        "dossie/especificacao.json",
        "dossie/modelo.json",
        "dossie/formulacao.tex",
        "dossie/solver.log",
        "dossie/validacoes.json",
        "dossie/explicacao.json",
    } <= nomes
    assert manifesto["fontes"]["inalteradas"] is True
    assert len(chamadas) == len(dossie.chamadas)


def test_executor_grava_um_dossie_por_execucao(tmp_path: Path) -> None:
    criar_instancia(tmp_path / "conjunto" / "a")
    calibrar([tmp_path / "conjunto" / "a"], tmp_path / "saida", "roteiro", [CONFIGURACAO])
    assert (tmp_path / "saida" / "dossies" / "a__com__r1.zip").exists()
