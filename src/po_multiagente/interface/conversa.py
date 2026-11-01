"""Conversa: o fluxo do ``Assistente`` em forma de chat, sem depender do Gradio.

Cada mensagem do usuário (texto e anexos) avança a conversa conforme a fase:

- **pedido:** junta a descrição e as planilhas, em uma ou várias mensagens, e
  executa quando tem as duas. Sem planilha, o Organizador (ADR-015) monta
  tabelas com os números escritos na conversa;
- **dados:** o usuário confere essas tabelas, já lidas como o fluxo vai usá-las,
  e confirma, corrige ou anexa planilhas;
- **solicitações:** o fluxo pediu planilhas ajustadas; os anexos respondem a
  elas, pelo nome do arquivo ou pela ordem da lista;
- **confirmação:** o resultado coincide com uma cota trivial (ADR-011); o
  usuário diz se faz sentido e, se não, o que falta;
- **resultado:** a resposta foi dada; um texto vira ajuste do pedido (o fluxo
  é refeito com os mesmos dados, depois de confirmado), e anexos começam um
  problema novo.

Os pontos que o Interpretador marcou como ambíguos aparecem no chat, com a
leitura adotada, sem interromper o fluxo. Nada aqui muda os agentes nem o
grafo: a conversa só traduz as interrupções que já existem.
"""

import csv
import shutil
import tempfile
import time
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from po_multiagente.agentes import ErroAgente, Registro
from po_multiagente.agentes.organizador import DadosOrganizados, Organizador, TabelaProposta
from po_multiagente.dados import Celula, ErroDados, ler_csv
from po_multiagente.dominio import AlertaAmbiguidade, Especificacao, Solicitacao
from po_multiagente.interface import apresentacao
from po_multiagente.interface.assistente import Assistente, ErroAssistente, Etapa, Resultado
from po_multiagente.llm import ErroLLM

Fase = Literal[
    "pedido", "dados", "solicitacoes", "confirmacao", "observacao", "resultado", "ajuste"
]
Progresso = Callable[[str], None]

SIM = "Sim, faz sentido"
NAO = "Não faz sentido"
REFAZER = "Refazer com esse ajuste"
NOVO = "Começar um problema novo"
SEGUIR_SEM = "Seguir sem esse ajuste"
USAR = "Usar estas tabelas"
CORRIGIR = "Quero corrigir"

DADOS = frozenset({".csv", ".xlsx"})
TEXTOS = frozenset({".txt", ".md"})
ORGANIZANDO = "Organizador: montando tabelas com os números que você escreveu"

BOAS_VINDAS = """\
Olá! Eu ajudo a decidir quanto produzir, comprar, transportar ou misturar para \
ter o melhor resultado, seja o maior lucro ou o menor custo, dentro dos limites \
do seu negócio.

**Para começar, me conte:**
- o que você quer decidir (por exemplo, quanto produzir de cada produto);
- o que quer maximizar ou minimizar (por exemplo, a margem total);
- quais limites existem (por exemplo, a madeira e as horas de montagem do mês).

Se tiver os números em **planilhas** (CSV ou Excel), anexe aqui. Se não tiver, \
escreva os números na conversa: eu monto as tabelas para você conferir antes de \
usar, e pergunto o que faltar.

Pode mandar tudo numa mensagem ou em partes. Se quiser ver como funciona, use o \
exemplo da marcenaria."""

_NEGATIVAS = ("nao", "n ", "errado", "falta", "nao faz")
_AFIRMATIVAS = ("sim", "faz sentido", "ok", "pode", "isso", "correto", "certo", "confirmo")
_SEM_ARQUIVO = ("nao tenho", "pular", "seguir sem", "continuar sem", "sem ajuste", "nao consigo")


@dataclass(frozen=True)
class Mensagem:
    """Uma mensagem da plataforma no chat.

    Attributes:
        texto: Markdown, com LaTeX entre ``$$``.
        titulo: Se houver, a mensagem aparece recolhida sob esse título
            (detalhes técnicos).
        arquivo: Arquivo para baixar.
        opcoes: Respostas rápidas, que o usuário pode clicar em vez de escrever.
    """

    texto: str = ""
    titulo: str | None = None
    arquivo: Path | None = None
    opcoes: tuple[str, ...] = ()


class Conversa:
    """Uma conversa do usuário com a plataforma.

    Args:
        criar_assistente: Cria um ``Assistente`` novo para cada problema (e
            para cada refação com ajuste).
        pasta: Onde guardar as planilhas recebidas; o padrão é uma pasta
            temporária.
        organizador: Monta tabelas com os números da conversa quando o
            usuário não tem planilhas; sem ele, as planilhas são obrigatórias.
        copias: Pasta onde guardar também uma cópia de cada arquivo oferecido
            para baixar. No Colab, é uma pasta de ``/content``, que aparece no
            painel de arquivos: o download pelo chat depende do proxy do Colab.
    """

    def __init__(
        self,
        criar_assistente: Callable[[], Assistente],
        pasta: Path | None = None,
        organizador: Organizador | None = None,
        copias: Path | None = None,
    ) -> None:
        self._criar = criar_assistente
        self._copias = copias
        self._organizador = organizador
        self._registro = Registro()
        self._propostas: list[Path] = []
        self._dados_da_conversa = False
        self._raiz = pasta or Path(tempfile.mkdtemp(prefix="po-conversa-"))
        self._recebidos = 0
        self.fase: Fase = "pedido"
        self._descricao = ""
        self._arquivos: list[Path] = []
        self._assistente: Assistente | None = None
        self._etapa: Etapa | None = None
        self._alertas_mostrados: set[str] = set()
        self._ajuste = ""

    def boas_vindas(self) -> list[Mensagem]:
        """Primeira mensagem da plataforma."""
        return [Mensagem(BOAS_VINDAS)]

    def responder(
        self, texto: str, arquivos: Sequence[Path] = (), ao_progresso: Progresso | None = None
    ) -> list[Mensagem]:
        """Mensagens da plataforma em resposta a uma mensagem do usuário.

        Args:
            texto: O que o usuário escreveu (ou a resposta rápida que clicou).
            arquivos: Planilhas anexadas.
            ao_progresso: Recebe a descrição de cada passo do fluxo enquanto ele roda.
        """
        dados = [a for a in arquivos if Path(a).suffix.lower() in DADOS]
        textos = [a for a in arquivos if Path(a).suffix.lower() in TEXTOS]
        outros = [a for a in arquivos if a not in dados and a not in textos]
        texto = "\n\n".join(
            [texto.strip(), *(Path(a).read_text(encoding="utf-8").strip() for a in textos)]
        ).strip()
        aviso = (
            [
                Mensagem(
                    "Não consigo ler "
                    + ", ".join(f"`{Path(a).name}`" for a in outros)
                    + ". Leio planilhas CSV ou Excel e textos .txt ou .md."
                )
            ]
            if outros
            else []
        )
        if outros and not texto and not dados:
            return aviso
        recebidos = self._guardar(dados)
        try:
            return [*aviso, *self._responder(texto, recebidos, ao_progresso)]
        except (ErroAssistente, ErroLLM, ErroAgente) as erro:
            return [*aviso, Mensagem(f"⚠️ {erro}")]

    # ------------------------------------------------------------- fases

    def _responder(
        self, texto: str, arquivos: list[Path], ao_progresso: Progresso | None
    ) -> list[Mensagem]:
        if self.fase == "dados":
            return self._conferir_dados(texto, arquivos, ao_progresso)
        if self.fase == "solicitacoes":
            return self._tratar(texto, arquivos, ao_progresso)
        if self.fase == "confirmacao":
            return self._confirmar(texto, ao_progresso)
        if self.fase == "observacao":
            return self._rodar(lambda a: a.confirmar(False, texto or None), ao_progresso)
        if self.fase == "ajuste":
            return self._decidir_ajuste(texto, arquivos, ao_progresso)
        if self.fase == "resultado":
            return self._depois_do_resultado(texto, arquivos, ao_progresso)
        return self._pedido(texto, arquivos, ao_progresso)

    def _depois_do_resultado(
        self, texto: str, arquivos: list[Path], ao_progresso: Progresso | None
    ) -> list[Mensagem]:
        if arquivos:
            self._reiniciar()
            return self._pedido(texto, arquivos, ao_progresso)
        if not texto:
            return []
        self._ajuste = texto
        self.fase = "ajuste"
        return [
            Mensagem(
                f"Posso refazer a análise com os mesmos dados, acrescentando ao pedido: "
                f"«{texto}». Quer que eu refaça, ou é um problema novo?",
                opcoes=(REFAZER, NOVO),
            )
        ]

    def _pedido(
        self, texto: str, arquivos: list[Path], ao_progresso: Progresso | None
    ) -> list[Mensagem]:
        if texto:
            self._descricao = f"{self._descricao}\n\n{texto}".strip()
        self._arquivos += arquivos
        if not self._descricao and not self._arquivos:
            return [Mensagem("Me conte o que você quer decidir e anexe as planilhas.")]
        if not self._arquivos:
            if self._organizador is not None:
                return self._organizar(ao_progresso)
            return [
                Mensagem(
                    "Entendi o pedido. Agora **anexe as planilhas** com os números (CSV ou "
                    "Excel): eles vêm sempre das planilhas, e não do texto."
                )
            ]
        if not self._descricao:
            nomes = ", ".join(f"`{a.name}`" for a in self._arquivos)
            return [
                Mensagem(
                    f"Recebi {nomes}. Agora me diga o que você quer decidir, o que quer "
                    "maximizar ou minimizar e quais limites existem."
                )
            ]
        descricao, planilhas = self._descricao, list(self._arquivos)
        return self._rodar(lambda a: a.comecar(descricao, planilhas), ao_progresso, novo=True)

    def _organizar(self, ao_progresso: Progresso | None) -> list[Mensagem]:
        """Tabelas com os números da conversa, para o usuário conferir."""
        assert self._organizador is not None
        if ao_progresso is not None:
            ao_progresso(ORGANIZANDO)
        dados = self._organizador.organizar(self._descricao, self._registro)
        faltam = _faltantes(dados)
        if not dados.tabelas:
            self.fase = "pedido"
            return [
                Mensagem(
                    "Para resolver, preciso dos números do problema. Se tiver planilhas, "
                    "anexe aqui. Se não tiver, escreva os dados na conversa."
                    + (f"\n\n{faltam}" if faltam else "")
                )
            ]
        self._recebidos += 1
        pasta = self._raiz / f"tabelas_{self._recebidos}"
        try:
            self._propostas = [gravar_tabela(t, pasta) for t in dados.tabelas]
            vistas = [
                _tabela_lida(t, c) for t, c in zip(dados.tabelas, self._propostas, strict=True)
            ]
        except ErroDados as erro:
            self.fase = "pedido"
            return [
                Mensagem(f"⚠️ Não consegui montar as tabelas: {erro}. Pode reescrever os dados?")
            ]
        self.fase = "dados"
        copia = guardar_copia(self._propostas, self._copias, "tabelas")
        return [
            Mensagem(
                "Montei estas tabelas **só com os números que você escreveu**, já lidas "
                "como vou usá-las. Confira:\n\n"
                + "\n\n".join(vistas)
                + (f"\n\n{faltam}" if faltam else "")
                + "\n\nSe estiver certo, confirme. Para corrigir ou completar, escreva o "
                "que mudar; se preferir, anexe suas planilhas.",
                opcoes=(USAR, CORRIGIR),
            ),
            *(
                Mensagem(
                    f"```csv\n{caminho.read_text(encoding='utf-8')}```",
                    titulo=f"{caminho.name}: texto para copiar",
                )
                for caminho in self._propostas
            ),
            *(Mensagem(arquivo=caminho) for caminho in self._propostas),
            *([Mensagem(copia)] if copia else []),
        ]

    def _conferir_dados(
        self, texto: str, arquivos: list[Path], ao_progresso: Progresso | None
    ) -> list[Mensagem]:
        if arquivos:
            self._propostas = []
            self.fase = "pedido"
            return self._pedido(texto, arquivos, ao_progresso)
        if texto == USAR or (texto != CORRIGIR and _afirmativa(texto)):
            self._arquivos = list(self._propostas)
            self._dados_da_conversa = True
            descricao, planilhas = self._descricao, list(self._arquivos)
            return self._rodar(lambda a: a.comecar(descricao, planilhas), ao_progresso, novo=True)
        if texto == CORRIGIR or not texto:
            return [Mensagem("Escreva o que corrigir ou completar nos dados.")]
        self._descricao = f"{self._descricao}\n\n{texto}"
        return self._organizar(ao_progresso)

    def _tratar(
        self, texto: str, arquivos: list[Path], ao_progresso: Progresso | None
    ) -> list[Mensagem]:
        pendentes = self._etapa.solicitacoes if self._etapa else ()
        if not arquivos:
            if texto == SEGUIR_SEM or _contem(texto, _SEM_ARQUIVO):
                return self._rodar(lambda a: a.tratar({}), ao_progresso)
            return [
                Mensagem(
                    "Para seguir, preciso da planilha ajustada como **anexo**: os números "
                    "vêm sempre das planilhas, e eu não altero dados por conta própria. "
                    "Se não tiver como ajustar agora, posso seguir sem esse dado, mas o "
                    "resultado pode não sair.",
                    opcoes=(SEGUIR_SEM,),
                )
            ]
        if len(arquivos) > len(pendentes):
            return [
                Mensagem(
                    f"Recebi {len(arquivos)} arquivo(s), mas pedi {len(pendentes)}. "
                    "Mande só as planilhas ajustadas da lista."
                )
            ]
        respostas = _associar(pendentes, arquivos)
        return self._rodar(lambda a: a.tratar(respostas), ao_progresso)

    def _confirmar(self, texto: str, ao_progresso: Progresso | None) -> list[Mensagem]:
        if texto == SIM or (texto != NAO and _afirmativa(texto)):
            return self._rodar(lambda a: a.confirmar(True), ao_progresso)
        if texto == NAO or _negativa(texto):
            observacao = _sem_negacao(texto) if texto != NAO else ""
            if observacao:
                return self._rodar(lambda a: a.confirmar(False, observacao), ao_progresso)
            self.fase = "observacao"
            return [
                Mensagem(
                    "Certo. O que está faltando ou errado? Por exemplo: «falta a produção "
                    "mínima de cada produto». Vou refazer levando isso em conta."
                )
            ]
        return [
            Mensagem(
                "Não entendi se o resultado faz sentido. Responda sim, ou não seguido do "
                "que está faltando.",
                opcoes=(SIM, NAO),
            )
        ]

    def _decidir_ajuste(
        self, texto: str, arquivos: list[Path], ao_progresso: Progresso | None
    ) -> list[Mensagem]:
        if arquivos or texto == NOVO:
            self._reiniciar()
            if arquivos or (texto and texto != NOVO):
                return self._pedido("" if texto == NOVO else texto, arquivos, ao_progresso)
            return [Mensagem("Certo. Descreva o problema novo e anexe as planilhas.")]
        if texto == REFAZER or _afirmativa(texto):
            self._descricao = f"{self._descricao}\n\nAjuste pedido pelo usuário: {self._ajuste}"
            descricao, planilhas = self._descricao, list(self._arquivos)
            return self._rodar(lambda a: a.comecar(descricao, planilhas), ao_progresso, novo=True)
        # Outro texto: substitui o ajuste proposto.
        self._ajuste = texto
        return [Mensagem(f"Refaço acrescentando: «{texto}»?", opcoes=(REFAZER, NOVO))]

    # ------------------------------------------------------------ execução

    def _rodar(
        self,
        passo: Callable[[Assistente], Etapa],
        ao_progresso: Progresso | None,
        *,
        novo: bool = False,
    ) -> list[Mensagem]:
        if novo or self._assistente is None:
            self._assistente = self._criar()
            self._alertas_mostrados = set()
        assistente = self._assistente
        assistente.ao_avancar = ao_progresso
        inicio = time.perf_counter()
        try:
            self._etapa = passo(assistente)
        finally:
            assistente.ao_avancar = None
        return self._apos(self._etapa, assistente.resultado(), time.perf_counter() - inicio)

    def _apos(self, etapa: Etapa, resultado: Resultado, segundos: float) -> list[Mensagem]:
        mensagens = self._alertas(resultado.especificacao)
        if etapa.tipo == "solicitacoes":
            self.fase = "solicitacoes"
            return [*mensagens, Mensagem(texto_solicitacoes(etapa.solicitacoes))]
        if etapa.tipo == "confirmacao":
            self.fase = "confirmacao"
            perguntas = "\n\n".join(etapa.perguntas)
            return [*mensagens, Mensagem(perguntas, opcoes=(SIM, NAO))]
        self.fase = "resultado"
        if self._dados_da_conversa:
            mensagens.append(
                Mensagem(
                    "Os números vieram das tabelas que montei com os dados da conversa e "
                    "você conferiu."
                )
            )
        return [
            *mensagens,
            *mensagens_do_resultado(resultado, segundos, self._raiz, self._copias),
        ]

    def _alertas(self, especificacao: Especificacao | None) -> list[Mensagem]:
        if especificacao is None:
            return []
        novos = [a for a in especificacao.alertas if a.trecho not in self._alertas_mostrados]
        self._alertas_mostrados |= {a.trecho for a in novos}
        return [Mensagem(texto_alerta(a, especificacao)) for a in novos]

    # ------------------------------------------------------------ auxiliares

    def _guardar(self, arquivos: Sequence[Path]) -> list[Path]:
        """Copia os anexos para a pasta da conversa (os do Gradio são temporários)."""
        if not arquivos:
            return []
        self._recebidos += 1
        pasta = self._raiz / f"recebidos_{self._recebidos}"
        pasta.mkdir(parents=True, exist_ok=True)
        return [Path(shutil.copy(a, pasta / Path(a).name)) for a in arquivos]

    def _reiniciar(self) -> None:
        self.fase = "pedido"
        self._descricao = ""
        self._arquivos = []
        self._assistente = None
        self._etapa = None
        self._ajuste = ""
        self._propostas = []
        self._dados_da_conversa = False


# ------------------------------------------------------------------ textos


def texto_solicitacoes(solicitacoes: Sequence[Solicitacao]) -> str:
    """Pedido de planilhas ajustadas, só sobre os dados (nunca sobre a formulação)."""
    linhas = [
        "Para continuar, preciso que você ajuste "
        + ("um dado:" if len(solicitacoes) == 1 else "alguns dados:"),
        "",
    ]
    for numero, solicitacao in enumerate(solicitacoes, start=1):
        coluna = f", coluna `{solicitacao.coluna}`" if solicitacao.coluna else ""
        motivo = apresentacao.MOTIVOS.get(solicitacao.motivo.value, solicitacao.motivo.value)
        linhas.append(
            f"{numero}. Planilha `{solicitacao.arquivo}`{coluna}: o dado {motivo}. "
            f"Como deve ficar: {solicitacao.forma_esperada}"
        )
    linhas += [
        "",
        "Anexe aqui a planilha ajustada"
        + (
            "."
            if len(solicitacoes) == 1
            else "s, todas de uma vez: reconheço cada uma pelo nome do arquivo "
            "original ou, se os nomes mudarem, pela ordem da lista."
        ),
    ]
    return "\n".join(linhas)


def texto_alerta(alerta: AlertaAmbiguidade, especificacao: Especificacao) -> str:
    """Ponto ambíguo do pedido, com a leitura adotada quando ela é conhecida."""
    requisitos = {r.id: r.texto for r in especificacao.requisitos}
    adotada = requisitos.get(alerta.requisito_id or "")
    leituras = "\n".join(f"- {leitura}" for leitura in alerta.leituras)
    considerado = (
        f"\n\nConsiderei: **{adotada}**" if adotada else "\n\nSegui a leitura mais provável."
    )
    return (
        f"🔎 Um trecho do pedido admite mais de uma leitura: «{alerta.trecho}».\n\n"
        f"Leituras possíveis:\n{leituras}{considerado}\n\n"
        "Se não era isso, me diga quando a resposta sair, e eu refaço com o ajuste."
    )


def mensagens_do_resultado(
    resultado: Resultado, segundos: float, pasta: Path, copias: Path | None = None
) -> list[Mensagem]:
    """A resposta primeiro; os detalhes técnicos (R5) recolhidos; o arquivo para baixar."""
    if not resultado.explicacao:
        motivo = resultado.falha or f"status do solver: {resultado.status or 'sem resultado'}"
        return [
            Mensagem(
                f"{apresentacao.destaque(resultado)}\n\n**Não consegui chegar a uma "
                "resposta.** Confira se o pedido diz o que decidir, o que otimizar e quais "
                "limites existem, e se as planilhas trazem os números com cabeçalho. Você "
                "pode escrever um ajuste para eu refazer, ou anexar planilhas corrigidas "
                "para começar de novo.",
            ),
            Mensagem(motivo, titulo="Detalhe técnico"),
        ]
    principal = "\n\n".join(
        parte
        for parte in (
            apresentacao.destaque(resultado),
            resultado.explicacao,
            apresentacao.plano_recomendado(resultado),
            apresentacao.selo_conferencia(resultado).replace(
                "Veja em *Detalhes técnicos → Conferências*.", "Veja em *Conferências*, abaixo."
            ),
        )
        if parte
    )
    destino = Path(tempfile.mkdtemp(prefix="po-resultado-", dir=pasta))
    detalhes = [
        ("Decisões", apresentacao.decisoes(resultado)),
        ("Modelo matemático", apresentacao.modelo_legivel(resultado)),
        ("Conferências", apresentacao.conferencias(resultado.pareceres)),
        ("Entendimento do pedido", apresentacao.entendimento(resultado.especificacao)),
        ("Execução", apresentacao.consumo(resultado, segundos)),
    ]
    pacote = apresentacao.empacotar(resultado, destino)
    copia = guardar_copia([pacote], copias, "resultado")
    return [
        Mensagem(principal),
        *(Mensagem(texto, titulo=titulo) for titulo, texto in detalhes if texto),
        Mensagem(
            "Resultados para baixar: plano em CSV, modelo, conferências e o dossiê "
            "completo da execução (abra `dossie/index.html`)." + (f" {copia}" if copia else ""),
            arquivo=pacote,
        ),
        Mensagem(
            "Quer ajustar algo? Escreva o que mudar, e eu refaço com os mesmos dados. "
            "Para um problema novo, clique em *Nova conversa*."
        ),
    ]


def guardar_copia(arquivos: Sequence[Path], destino: Path | None, rotulo: str) -> str:
    """Copia os arquivos para ``destino`` e devolve o aviso ao usuário; sem destino, nada."""
    if destino is None or not arquivos:
        return ""
    pasta = destino / f"{datetime.now():%Y%m%d-%H%M%S}-{rotulo}"
    pasta.mkdir(parents=True, exist_ok=True)
    for arquivo in arquivos:
        shutil.copy(arquivo, pasta / arquivo.name)
    return (
        f"Também salvei uma cópia em `{pasta}`. No Colab, abra o painel de arquivos "
        "(ícone de pasta, à esquerda), clique com o botão direito no arquivo e escolha "
        "*Fazer download*."
    )


def gravar_tabela(tabela: TabelaProposta, pasta: Path) -> Path:
    """CSV com separador ``;`` (notação numérica brasileira), como o usuário escreveu."""
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / tabela.arquivo
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";")
        escritor.writerow(tabela.colunas)
        escritor.writerows(tabela.linhas)
    return caminho


def _tabela_lida(tabela: TabelaProposta, caminho: Path) -> str:
    """A tabela como o fluxo vai lê-la, com os números já interpretados."""
    lida = ler_csv(caminho)
    cabecalho = "| " + " | ".join(lida.colunas) + " |"
    separador = "|" + "---|" * len(lida.colunas)
    linhas = ["| " + " | ".join(_celula(c) for c in linha) + " |" for linha in lida.linhas]
    return f"**`{tabela.arquivo}`**: {tabela.descricao}\n\n" + "\n".join(
        [cabecalho, separador, *linhas]
    )


def _celula(valor: Celula) -> str:
    if isinstance(valor, bool) or valor is None:
        return "" if valor is None else str(valor)
    if isinstance(valor, int | float):
        return apresentacao.numero(valor)
    return str(valor).replace("|", "\\|")


def _faltantes(dados: DadosOrganizados) -> str:
    if not dados.faltantes:
        return ""
    return "**Ainda faltam:**\n" + "\n".join(f"- {f}" for f in dados.faltantes)


def _associar(pendentes: Sequence[Solicitacao], arquivos: list[Path]) -> dict[str, Path]:
    """Cada anexo vai para a solicitação do mesmo arquivo; os demais, pela ordem."""
    respostas: dict[str, Path] = {}
    restantes = list(arquivos)
    for solicitacao in pendentes:
        mesmo_nome = next((a for a in restantes if a.name == solicitacao.arquivo), None)
        if mesmo_nome is not None:
            respostas[solicitacao.id] = mesmo_nome
            restantes.remove(mesmo_nome)
    for solicitacao in pendentes:
        if solicitacao.id not in respostas and restantes:
            respostas[solicitacao.id] = restantes.pop(0)
    return respostas


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().replace(",", " ").replace(".", " ").split()) + " "


def _contem(texto: str, termos: Sequence[str]) -> bool:
    normalizado = _normalizar(texto)
    return any(t in normalizado for t in termos)


def _negativa(texto: str) -> bool:
    normalizado = _normalizar(texto)
    return any(normalizado.startswith(t) for t in _NEGATIVAS)


def _afirmativa(texto: str) -> bool:
    return not _negativa(texto) and any(_normalizar(texto).startswith(t) for t in _AFIRMATIVAS)


def _sem_negacao(texto: str) -> str:
    """O que vem depois do «não» inicial: a observação do usuário."""
    restante = texto.strip()
    for prefixo in ("não faz sentido", "nao faz sentido", "não", "nao"):
        if restante.lower().startswith(prefixo):
            restante = restante[len(prefixo) :]
            break
    return restante.strip(" ,.;:-—").strip()
