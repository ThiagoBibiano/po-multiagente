"""Dossiê de uma execução (requisito R5).

Reúne, num só registro, o que o usuário e um avaliador precisam para
inspecionar e reproduzir a execução: o pedido, o quadro de especificação, o
modelo (JSON e LaTeX), a solução e o log do solver, as validações, a
explicação com a procedência de cada número, as chamadas ao modelo de
linguagem (entrada e saída), a configuração, as versões e o hash de cada
fonte de dados no início e no fim da execução.

O dossiê é montado a partir do estado final, sem acesso a gabaritos, e
exportado como ZIP (um arquivo por artefato, mais ``index.html``) ou como uma
página HTML autocontida.
"""

import html
import io
import json
import platform
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from po_multiagente.config import ConfiguracaoExecucao, carregar_perfil
from po_multiagente.dados import arquivo_da_fonte, sha256_arquivo
from po_multiagente.dominio import (
    Especificacao,
    Explicacao,
    ModeloIR,
    ParecerValidador,
    ResultadoSolver,
)
from po_multiagente.modelo import ErroCompilacao, compilar, para_latex
from po_multiagente.prompts import AGENTES_COM_INSTRUCAO, carregar_instrucao

PACOTES = ("po-multiagente", "pulp", "langgraph", "pydantic", "lark", "openai")
NULO = 1e-9
"""Abaixo disso, o valor de uma variável não aparece na tabela da solução."""


@dataclass(frozen=True)
class Dossie:
    """Registro completo de uma execução."""

    criado_em: str
    descricao: str
    versoes: dict[str, str]
    configuracao: dict[str, Any]
    perfil_modelo: dict[str, Any]
    instrucoes_sha256: dict[str, str]
    hashes_inicio: dict[str, str]
    hashes_fim: dict[str, str | None]
    especificacao: Especificacao | None = None
    modelo: ModeloIR | None = None
    formulacao_latex: str | None = None
    resultado: ResultadoSolver | None = None
    log_solver: str = ""
    pareceres: tuple[ParecerValidador, ...] = ()
    explicacao: Explicacao | None = None
    falha: str | None = None
    chamadas: list[dict[str, Any]] = field(default_factory=list)
    eventos: list[dict[str, Any]] = field(default_factory=list)

    @property
    def dados_inalterados(self) -> bool:
        """Cada fonte lida tem, no fim, o mesmo hash do início."""
        return all(self.hashes_fim.get(a) == h for a, h in self.hashes_inicio.items())

    def como_dict(self) -> dict[str, Any]:
        """Representação JSON do dossiê inteiro."""
        return {
            "criado_em": self.criado_em,
            "descricao": self.descricao,
            "versoes": self.versoes,
            "configuracao": self.configuracao,
            "perfil_modelo": self.perfil_modelo,
            "instrucoes_sha256": self.instrucoes_sha256,
            "fontes": {
                "hash_inicio": self.hashes_inicio,
                "hash_fim": self.hashes_fim,
                "inalteradas": self.dados_inalterados,
            },
            "especificacao": _json(self.especificacao),
            "modelo": _json(self.modelo),
            "formulacao_latex": self.formulacao_latex,
            "resultado": _json(self.resultado),
            "log_solver": self.log_solver,
            "pareceres": [_json(p) for p in self.pareceres],
            "explicacao": _json(self.explicacao),
            "falha": self.falha,
            "chamadas": self.chamadas,
            "eventos": self.eventos,
        }


def montar_dossie(
    estado: Mapping[str, Any],
    configuracao: ConfiguracaoExecucao,
    pastas_dados: Sequence[Path] | None = None,
) -> Dossie:
    """Monta o dossiê a partir do estado final de uma sessão.

    Args:
        estado: Estado final do grafo.
        configuracao: Configuração da execução.
        pastas_dados: Onde estão as fontes no fim da execução, para o hash
            final; o padrão são as pastas registradas no estado.
    """
    especificacao: Especificacao | None = estado.get("especificacao")
    modelo: ModeloIR | None = estado.get("modelo")
    formulacao = None
    if modelo is not None:
        try:
            formulacao = para_latex(compilar(modelo))
        except ErroCompilacao:
            formulacao = None
    if pastas_dados is None:
        pastas_dados = [
            Path(p) for p in [estado.get("pasta_dados"), *estado.get("pastas_tratadas", [])] if p
        ]
    inicio = {f.arquivo: f.sha256 for f in especificacao.fontes} if especificacao else {}
    return Dossie(
        criado_em=datetime.now(UTC).isoformat(),
        descricao=str(estado.get("descricao", "")),
        versoes=_versoes(estado.get("resultado")),
        configuracao=configuracao.model_dump(mode="json"),
        perfil_modelo=carregar_perfil(configuracao.perfil_modelo).model_dump(mode="json"),
        instrucoes_sha256={a: carregar_instrucao(a).sha256 for a in AGENTES_COM_INSTRUCAO},
        hashes_inicio=inicio,
        hashes_fim={arquivo: _hash_atual(arquivo, pastas_dados) for arquivo in inicio},
        especificacao=especificacao,
        modelo=modelo,
        formulacao_latex=formulacao,
        resultado=estado.get("resultado"),
        log_solver=str(estado.get("log_solver", "")),
        pareceres=tuple(estado.get("pareceres", [])),
        explicacao=estado.get("explicacao"),
        falha=estado.get("falha"),
        chamadas=list(estado.get("chamadas", [])),
        eventos=list(estado.get("eventos", [])),
    )


def arquivos_do_dossie(dossie: Dossie) -> dict[str, str]:
    """Um arquivo por artefato, mais ``index.html`` para leitura."""
    dados = dossie.como_dict()
    return {
        "index.html": para_html(dossie),
        "dossie.json": _dump(dados),
        "descricao.md": dossie.descricao + "\n",
        "especificacao.json": _dump(dados["especificacao"]),
        "modelo.json": _dump(dados["modelo"]),
        "formulacao.tex": (dossie.formulacao_latex or "") + "\n",
        "resultado.json": _dump(dados["resultado"]),
        "solver.log": dossie.log_solver,
        "validacoes.json": _dump(dados["pareceres"]),
        "explicacao.json": _dump(dados["explicacao"]),
        "chamadas.jsonl": "".join(
            json.dumps(c, ensure_ascii=False, default=str) + "\n" for c in dossie.chamadas
        ),
        "manifesto.json": _dump(
            {
                k: dados[k]
                for k in (
                    "criado_em",
                    "versoes",
                    "configuracao",
                    "perfil_modelo",
                    "instrucoes_sha256",
                    "fontes",
                )
            }
        ),
    }


def exportar_zip(dossie: Dossie) -> bytes:
    """ZIP com os arquivos do dossiê, numa pasta ``dossie/``."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_:
        for nome, conteudo in arquivos_do_dossie(dossie).items():
            zip_.writestr(f"dossie/{nome}", conteudo)
    return buffer.getvalue()


def gravar_zip(dossie: Dossie, caminho: Path) -> Path:
    """Grava o ZIP do dossiê em ``caminho``."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(exportar_zip(dossie))
    return caminho


# ------------------------------------------------------------------ HTML


def para_html(dossie: Dossie) -> str:
    """Página HTML autocontida, para ler o dossiê sem nenhuma ferramenta."""
    e = html.escape
    resultado = dossie.resultado
    partes = [
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>Dossiê da execução</title>",
        f"<style>{_CSS}</style></head><body><main>",
        "<h1>Dossiê da execução</h1>",
        f"<p class='meta'>Gerado em {e(dossie.criado_em)} · po-multiagente "
        f"{e(dossie.versoes.get('po-multiagente', '?'))}</p>",
        "<h2>Resumo</h2><dl>",
        _par("Situação", resultado.status.value if resultado else "sem resultado"),
        _par(
            "Valor objetivo",
            f"{resultado.valor_objetivo:g}"
            if resultado and resultado.valor_objetivo is not None
            else "—",
        ),
        _par("Falha", dossie.falha or "nenhuma"),
        _par(
            "Fontes de dados",
            "inalteradas (mesmo hash no início e no fim)"
            if dossie.dados_inalterados
            else "ALTERADAS ou ausentes no fim da execução",
        ),
        "</dl>",
    ]
    if dossie.explicacao is not None:
        partes += [
            "<h2>Explicação</h2>",
            f"<p>{e(dossie.explicacao.texto)}</p>",
            _tabela(
                ("Número", "Valor", "Origem"),
                [(i.marcador, f"{i.valor:g}", i.origem) for i in dossie.explicacao.ficha],
            ),
        ]
    partes += ["<h2>Pedido</h2>", f"<pre>{e(dossie.descricao)}</pre>"]
    especificacao = dossie.especificacao
    if especificacao is not None:
        partes += [
            "<h2>Quadro de especificação</h2><dl>",
            _par("Decisão", especificacao.decisao),
            _par("Critério", f"{especificacao.criterio} ({especificacao.sentido.value})"),
            "</dl><h3>Requisitos</h3>",
            _tabela(("Id", "Requisito"), [(r.id, r.texto) for r in especificacao.requisitos]),
            "<h3>Parâmetros e origem</h3>",
            _tabela(
                ("Parâmetro", "Descrição", "Unidade", "Arquivo", "Coluna", "Tratamento"),
                [
                    (
                        p.id,
                        p.descricao,
                        p.unidade,
                        p.origem.arquivo,
                        p.origem.coluna,
                        p.origem.solicitacao_id or "",
                    )
                    for p in especificacao.parametros
                ],
            ),
        ]
        if especificacao.solicitacoes:
            partes += [
                "<h3>Solicitações de tratamento</h3>",
                _tabela(
                    ("Id", "Arquivo", "Coluna", "Motivo", "Forma esperada"),
                    [
                        (s.id, s.arquivo, s.coluna or "", s.motivo.value, s.forma_esperada)
                        for s in especificacao.solicitacoes
                    ],
                ),
            ]
        for titulo, itens in (
            ("Premissas", especificacao.premissas),
            ("Não considerado", especificacao.nao_considerado),
        ):
            if itens:
                partes += [f"<h3>{titulo}</h3><ul>", *(f"<li>{e(i)}</li>" for i in itens), "</ul>"]
    if dossie.formulacao_latex:
        partes += ["<h2>Modelo</h2>", f"<pre>{e(dossie.formulacao_latex)}</pre>"]
    if dossie.modelo is not None:
        partes.append(_detalhes("Modelo em JSON", _dump(_json(dossie.modelo))))
    if resultado is not None and resultado.valores:
        partes += [
            "<h2>Solução</h2>",
            f"<p class='meta'>Solver: {e(resultado.solver.backend)}/{e(resultado.solver.motor)} "
            f"{e(resultado.solver.versao)}; variáveis não nulas.</p>",
            _tabela(
                ("Variável", "Valor"),
                [(n, f"{v:g}") for n, v in resultado.valores.items() if abs(v) > NULO],
            ),
        ]
    if dossie.pareceres:
        partes.append("<h2>Validações</h2>")
        for parecer in dossie.pareceres:
            partes += [
                f"<h3>Iteração {parecer.iteracao}: "
                f"{'aprovado' if parecer.aprovado else 'reprovado'}</h3>",
                _tabela(
                    ("Sinal", "Resultado", "Mensagem"),
                    [
                        (v.sinal.value, "aprovado" if v.aprovada else "reprovado", v.mensagem)
                        for v in parecer.verificacoes
                    ],
                ),
            ]
    partes += [
        "<h2>Fontes de dados</h2>",
        _tabela(
            ("Arquivo", "SHA-256 no início", "No fim"),
            [
                (
                    a,
                    h,
                    "igual"
                    if dossie.hashes_fim.get(a) == h
                    else (dossie.hashes_fim.get(a) or "ausente"),
                )
                for a, h in dossie.hashes_inicio.items()
            ],
        ),
        "<h2>Chamadas ao modelo de linguagem</h2>",
        _tabela(
            ("Agente", "Modelo", "Entrada", "Saída", "Duração (s)", "Erro"),
            [
                (
                    c.get("agente", ""),
                    c.get("modelo", ""),
                    str(c.get("uso", {}).get("entrada", "")),
                    str(c.get("uso", {}).get("saida", "")),
                    f"{c.get('duracao_s', 0):.1f}",
                    c.get("erro") or "",
                )
                for c in dossie.chamadas
            ],
        ),
        *(
            _detalhes(
                f"Chamada {i}: {c.get('agente', '')}",
                f"ENTRADA\n{c.get('entrada', '')}\n\nSAÍDA\n{c.get('saida', '')}",
            )
            for i, c in enumerate(dossie.chamadas, start=1)
        ),
        "<h2>Configuração e versões</h2>",
        _detalhes("Configuração", _dump(dossie.configuracao)),
        _detalhes("Perfil do modelo de linguagem", _dump(dossie.perfil_modelo)),
        _detalhes("Versões", _dump(dossie.versoes)),
        _detalhes("Instruções dos agentes (SHA-256)", _dump(dossie.instrucoes_sha256)),
    ]
    if dossie.log_solver:
        partes.append(_detalhes("Log do solver", dossie.log_solver))
    partes.append("</main></body></html>")
    return "\n".join(partes)


_CSS = """
:root{color-scheme:light dark;--fg:#1b2523;--muted:#5b6764;--line:#d9dfdd;--bg:#fbfbfa}
@media (prefers-color-scheme:dark){:root{--fg:#e3e8e6;--muted:#9aa7a3;--line:#2e3a37;--bg:#141a19}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,sans-serif}
main{max-width:60rem;margin:0 auto;padding:24px 16px 64px}
h1{font-size:26px}h2{font-size:20px;margin-top:32px;border-bottom:1px solid var(--line)}
h3{font-size:16px}.meta{color:var(--muted);font-size:13px}
table{border-collapse:collapse;width:100%;font-size:14px;display:block;overflow-x:auto}
th,td{text-align:left;padding:6px 10px 6px 0;border-bottom:1px solid var(--line);vertical-align:top}
pre{white-space:pre-wrap;word-break:break-word;font-size:13px}
dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 16px}dt{color:var(--muted)}
details{margin:6px 0}summary{cursor:pointer}
"""


def _par(rotulo: str, valor: str) -> str:
    return f"<dt>{html.escape(rotulo)}</dt><dd>{html.escape(valor)}</dd>"


def _tabela(cabecalho: Sequence[str], linhas: Sequence[Sequence[str]]) -> str:
    if not linhas:
        return "<p class='meta'>Nenhum.</p>"
    th = "".join(f"<th>{html.escape(c)}</th>" for c in cabecalho)
    corpo = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in linha) + "</tr>"
        for linha in linhas
    )
    return f"<table><thead><tr>{th}</tr></thead><tbody>{corpo}</tbody></table>"


def _detalhes(titulo: str, conteudo: str) -> str:
    return (
        f"<details><summary>{html.escape(titulo)}</summary>"
        f"<pre>{html.escape(conteudo)}</pre></details>"
    )


# --------------------------------------------------------------- auxiliares


def _json(objeto: BaseModel | None) -> dict[str, Any] | None:
    return objeto.model_dump(mode="json") if objeto is not None else None


def _dump(dados: object) -> str:
    return json.dumps(dados, ensure_ascii=False, indent=2, default=str) + "\n"


def _versoes(resultado: ResultadoSolver | None) -> dict[str, str]:
    versoes = {"python": platform.python_version()}
    for pacote in PACOTES:
        try:
            versoes[pacote] = version(pacote)
        except PackageNotFoundError:
            continue
    if resultado is not None:
        solver = resultado.solver
        versoes["solver"] = f"{solver.backend}/{solver.motor} {solver.versao}"
    return versoes


def _hash_atual(arquivo: str, pastas: Sequence[Path]) -> str | None:
    for pasta in pastas:
        caminho = pasta / arquivo_da_fonte(arquivo)
        if caminho.is_file():
            return sha256_arquivo(caminho)
    return None
