# ADR-011: Resultado suspeito vira pergunta ao usuário

- **Estado:** aceita no mecanismo; tratamento no experimento em aberto
- **Data:** 2026-09-26

## Contexto

O sinal S5 detecta quando o valor objetivo coincide com uma cota trivial,
calculada só com os domínios das variáveis: custo mínimo zero, lucro máximo
zero. Isso costuma indicar restrição faltante ou exigência entendida ao
contrário, mas pode ser a resposta certa. Reprovar e devolver ao Modelador
arrisca uma "correção indevida" (taxonomia do Passo 8), e o Modelador não
tem como descobrir sozinho qual exigência falta: essa informação está com o
usuário. A especificação do problema é iterativa.

## Decisão

- A cota trivial **não reprova**. O S5 aprova e anexa à verificação uma
  `confirmacao`: pergunta ao usuário, em linguagem de negócio, sobre o
  **resultado** (e nunca sobre a formulação, regra do cap. 3).
- Uma verificação reprovada não pode trazer confirmação: ou o erro vai ao
  Modelador, ou a dúvida vai ao usuário.
- Na plataforma (F2), uma confirmação pendente interrompe o fluxo antes do
  Explicador. Se o usuário disser que o resultado não faz sentido, a
  especificação volta ao Interpretador com a resposta dele.

## Consequências

- O texto do cap. 3 precisa registrar que o Validador pode abrir uma
  pergunta ao usuário, além de devolver o erro ao Modelador.
- **Experimento (em aberto, F6).** Não há usuário, e a pergunta só existe
  na configuração com Validador: responder com informação nova daria a essa
  configuração uma vantagem que não é do Validador. Proposta: cada instância
  registra de antemão, em `meta.yaml`, se um resultado trivial seria
  aceitável para o gestor, sem consultar a solução de referência; a resposta
  "não faz sentido" volta ao Modelador sem nenhuma exigência nova, como uma
  reprovação comum do S5.
