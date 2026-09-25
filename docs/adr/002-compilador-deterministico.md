# ADR-002: Compilador determinístico e representação intermediária em JSON

- **Estado:** aceita
- **Data:** 2026-09-25

## Contexto

O Gerador-Executor traduz o modelo em código. Se essa tradução fosse feita
por LLM, seria mais uma fonte de erro, e o piloto mostrou o LLM afirmando uma
solução que não correspondia ao próprio modelo.

## Decisão

- O Modelador escreve o modelo em **JSON validado por esquema Pydantic**
  (`dominio.ModeloIR`), em forma **algébrica indexada**: conjuntos,
  parâmetros e variáveis indexados e restrições "para todo".
- A estrutura fica em JSON; as **expressões ficam em texto**, numa
  mini-linguagem algébrica restrita, interpretada por gramática Lark.
- Os parâmetros **apontam para dados** (arquivo, coluna, chaves); o LLM nunca
  escreve números.
- Um **compilador determinístico** de três estágios substitui a geração de
  código: parse e checagem → modelo instanciado neutro → adaptador do
  solver.

## Consequências

- Some uma classe de falha: no TG2, a categoria "Geração de código" da
  taxonomia vira **"Compilação do modelo"**.
- O tamanho do modelo não cresce com os dados, e a comparação com o gabarito
  por componente (critério 1) fica direta.
- A gramática é um componente novo, que exige testes próprios e precisa ser
  ensinada ao Modelador no prompt.
