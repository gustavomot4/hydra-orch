# S16 — Segurança local e proveniência

## Contrato entregue pela T09

Todas as rotas HTTP, inclusive health, inferência, documentação e aliases M1,
exigem um token Bearer. Ausência de configuração impede o startup antes de
inicializar gateway, banco ou SSH. Requisições sem token ou com credencial inválida
retornam `401 unauthorized` e `WWW-Authenticate: Bearer`, inclusive em loopback.
A CLI que chama diretamente o serviço local continua independente de HTTP.

O operador configura exatamente uma variável externa: `HYDRA_API_TOKEN_HASH`
(preferida) ou `HYDRA_API_TOKEN`. Tokens têm 32 a 4096 caracteres sem espaços;
o operador deve gerar valores aleatórios. A aplicação mantém apenas o verificador
PBKDF2-HMAC-SHA256 com salt aleatório de 16 bytes, 600.000 iterações e digest
de 32 bytes. O formato é `pbkdf2_sha256$iterations$salt_hex$digest_hex`.
Verificadores carregados exigem entre 600.000 e 2.000.000 iterações. A comparação
usa `hmac.compare_digest`; a derivação por requisição roda fora do event loop.
Rotação exige substituir a configuração externa e reiniciar o servidor.
Nenhuma credencial é escrita em YAML, SQLite ou arquivo pelo serviço de auth.

`HYDRA_CORS_ALLOW_ORIGINS` aceita uma lista JSON de origens HTTP(S) explícitas
em `localhost`, `127.0.0.1` ou `[::1]`, sem credenciais, paths, query ou fragmento.
O padrão preserva portas 8000, 3000 e 5173 em localhost/127.0.0.1.
Wildcard e origens externas são recusados. Origin não autorizado retorna 403
antes da autenticação. Clientes nativos podem omitir Origin e continuam sujeitos
ao Bearer. Preflight OPTIONS com Origin permitido não exige Bearer, pois browsers
não o enviam nessa etapa; o middleware CORS valida método e headers e não executa
o endpoint. OPTIONS comum continua autenticado.

## Sanitização e integridade

`core/redaction.py` remove campos sensíveis recursivamente e padrões textuais
de tokens conhecidos, Bearer, senhas, credenciais OAuth, URLs com user:pass e
chaves privadas PEM completas ou truncadas. O marcador é `[REDACTED]` e a
operação é idempotente. IDs, hashes e contadores de tokens são preservados.

- Eventos são sanitizados antes do INSERT na mesma transação do estado.
- Replay sanitiza também payloads legados sem reescrever sua sequência.
- JSON de evidência/erros e payloads SSE têm uma barreira de saída adicional.
- O logging padrão sanitiza mensagem, argumentos, traceback e stack antes dos handlers.
- Logs stdout/stderr de workers e checks são sanitizados antes da gravação;
  SHA-256 e tamanho descrevem os bytes sanitizados efetivamente armazenados.

Patches e arquivos do repositório não são reescritos pelo redactor; isso mudaria
o código e sua atribuição. Logs antigos em disco e outros dados legados no SQLite
não são expurgados automaticamente. Credenciais sem rótulo ou padrão reconhecível
não têm detecção garantida. O corpus benigno de testes verifica preservação de
2000 mensagens sintéticas; não certifica a taxa RNF05 em tráfego real.

## Validação e limites do gate

`tests/test_auth.py` cobre falhas de autenticação/configuração, ausência de token
no startup, preflight, CORS inválido, redaction recursiva/textual, logs com exceção,
persistência SQLite, replay/SSE e hashes de logs sanitizados. Testes de servidor
usam autenticação explícita, mantendo as verificações funcionais M1.

T09 não fecha isoladamente G-SEG: autorização de raízes/path traversal do catálogo
pertence à T11; consentimento, discovery, SecretRef e isolamento de extensões
dependem de T17–T20. Certificação de um driver externo também permanece separada.
