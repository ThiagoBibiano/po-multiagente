"""Coleção das fontes de dados de uma sessão, lidas de um diretório."""

import hashlib
import re
from collections.abc import Iterable
from pathlib import Path

from po_multiagente.dados.erros import ErroDados
from po_multiagente.dados.leitura import Tabela, ler_csv, ler_xlsx
from po_multiagente.dominio import Coluna, FonteDados

EXTENSOES = frozenset({".csv", ".xlsx"})
"""Formatos aceitos. XLS e ODS precisam ser salvos como XLSX pelo usuário."""

_BLOCO_HASH = 1 << 16
_ABA = re.compile(r"^(?P<arquivo>.+\.xlsx)\[(?P<aba>.+)\]$", re.IGNORECASE)


def arquivo_da_fonte(nome: str) -> str:
    """Arquivo de uma fonte: ``custos.xlsx[Março]`` está em ``custos.xlsx``."""
    aba = _ABA.fullmatch(nome)
    return aba["arquivo"] if aba else nome


def sha256_arquivo(caminho: Path) -> str:
    """Resumo SHA-256 do conteúdo do arquivo, em hexadecimal minúsculo."""
    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        while bloco := arquivo.read(_BLOCO_HASH):
            resumo.update(bloco)
    return resumo.hexdigest()


class Fontes:
    """Fontes de dados de uma sessão, com acesso somente leitura.

    Cada arquivo é lido uma vez e guardado em memória. Os arquivos nunca são
    abertos para escrita; ``conferir_integridade`` compara o hash atual com o
    registrado no inventário para provar isso a cada execução.

    Args:
        diretorio: Diretório com os arquivos do usuário. Só os arquivos
            diretamente nele, com extensão aceita, são fontes.
    """

    def __init__(self, diretorio: Path) -> None:
        if not diretorio.is_dir():
            raise NotADirectoryError(diretorio)
        self._diretorio = diretorio
        self._tabelas: dict[str, tuple[Tabela, ...]] = {}

    @property
    def arquivos(self) -> tuple[str, ...]:
        """Nomes dos arquivos de dados do diretório, em ordem alfabética."""
        return tuple(
            sorted(
                caminho.name
                for caminho in self._diretorio.iterdir()
                if caminho.is_file() and caminho.suffix.lower() in EXTENSOES
            )
        )

    def tabelas(self, arquivo: str) -> tuple[Tabela, ...]:
        """Tabelas de um arquivo: uma para CSV, uma por aba para XLSX.

        Raises:
            ErroDados: Se o arquivo não for uma fonte do diretório ou não
                puder ser lido.
        """
        if arquivo not in self._tabelas:
            caminho = self._caminho(arquivo)
            if caminho.suffix.lower() == ".csv":
                self._tabelas[arquivo] = (ler_csv(caminho),)
            else:
                self._tabelas[arquivo] = ler_xlsx(caminho)
        return self._tabelas[arquivo]

    def tabela(self, nome: str) -> Tabela:
        """Tabela pelo nome da fonte: ``arquivo`` ou ``arquivo.xlsx[aba]``.

        Raises:
            ErroDados: Se não houver fonte com esse nome.
        """
        for tabela in self.tabelas(arquivo_da_fonte(nome)):
            if tabela.nome == nome:
                return tabela
        raise ErroDados(f"Não há fonte chamada {nome!r}", arquivo=nome)

    def inventario(self) -> tuple[FonteDados, ...]:
        """Inventário de todas as fontes: nome, hash e colunas com tipo."""
        fontes: list[FonteDados] = []
        for arquivo in self.arquivos:
            sha256 = sha256_arquivo(self._caminho(arquivo))
            fontes.extend(
                FonteDados(
                    arquivo=tabela.nome,
                    sha256=sha256,
                    colunas=tuple(
                        Coluna(nome=nome, tipo=tipo)
                        for nome, tipo in zip(tabela.colunas, tabela.tipos, strict=True)
                    ),
                )
                for tabela in self.tabelas(arquivo)
            )
        return tuple(fontes)

    def conferir_integridade(self, fontes: Iterable[FonteDados]) -> tuple[str, ...]:
        """Fontes cujo arquivo mudou ou sumiu desde o inventário.

        Returns:
            Nomes das fontes alteradas; vazio quando nada mudou.
        """
        alteradas = []
        for fonte in fontes:
            caminho = self._diretorio / arquivo_da_fonte(fonte.arquivo)
            if not caminho.is_file() or sha256_arquivo(caminho) != fonte.sha256:
                alteradas.append(fonte.arquivo)
        return tuple(alteradas)

    def _caminho(self, arquivo: str) -> Path:
        # Só nomes simples: impede ler fora do diretório (``../``).
        if Path(arquivo).name != arquivo or arquivo not in self.arquivos:
            raise ErroDados(f"Não há arquivo de dados chamado {arquivo!r}", arquivo=arquivo)
        return self._diretorio / arquivo
