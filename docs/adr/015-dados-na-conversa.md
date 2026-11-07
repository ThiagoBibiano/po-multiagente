# ADR-015: Dados escritos na conversa viram tabelas conferidas pelo usuário

- **Estado:** aceita
- **Data:** 2026-11-01

## Contexto

No teste da interface de chat, o autor pediu que a planilha deixasse de ser
obrigatória. O gestor deve poder enunciar o problema com os números no texto,
e o fluxo deve descobrir se há dados e pedir o que faltar. Até aqui, o desenho
exigia fontes de dados: o modelo de linguagem nunca escreve números (ADR-002,
ADR-013), e os parâmetros sempre apontam para arquivo e coluna. A ideia de uma
origem "descrição", com o número conferido por código, estava em aberto desde
a F1 (plano, seção 10, ponto 1).

## Decisão

- Um agente novo, o **Organizador**, roda só na interface de chat, antes do
  fluxo, e só quando o usuário não anexou planilhas. Ele monta tabelas (CSV)
  com os números escritos na conversa e lista os dados que faltam.
- **Nenhum número é criado.** Cada número das tabelas precisa aparecer escrito
  nas mensagens do usuário, com ou sem ponto de milhar. O código confere isso;
  uma tabela com número sem origem é recusada e volta ao modelo, até três vezes.
- O usuário **confere** as tabelas, já lidas pelo leitor de CSV do artefato,
  com os números como o fluxo vai usá-los. Ele confirma, corrige em texto (as
  tabelas são refeitas com a correção) ou anexa as próprias planilhas.
- Confirmadas, as tabelas entram no fluxo como planilhas comuns. Interpretador,
  Modelador, Validador e Explicador não mudam, e as instruções congeladas também
  não.
- Sem números no texto, o chat pede os dados, listando o que falta.

## Consequências

- O experimento não muda: as instâncias sempre trazem planilhas, e o
  Organizador não faz parte do grafo. Sua instrução (`prompts/organizador.md`)
  fica fora da lista de instruções congeladas.
- O requisito R3 (dados de fontes externas) continua sendo o caminho principal.
  O uso só com a descrição passa a funcionar na interface de chat, mas não é
  avaliado no experimento. No texto do TG, isso entra como recurso da interface
  e limitação do escopo avaliado.
- As tabelas montadas vão para o usuário como arquivos e entram no dossiê como
  fontes, com hash. As chamadas ao Organizador não entram no dossiê da
  execução, porque acontecem antes da sessão; fica como melhoria futura.
- Um número escrito por extenso ("cem", "metade") não é aceito: vira pedido do
  valor em algarismos.
