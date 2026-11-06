# TikTok Live Recorder 5.0 | Atualizações pelo GitHub

## Primeira configuração (uma única vez)

1. Crie um repositório **público** no GitHub, por exemplo `TikTokLiveRecorder`.
2. Edite `release_config.json` e substitua `SEU_USUARIO` pelo seu nome de usuário no GitHub. Se o nome do repositório for outro, altere também `repo`.
3. Instale Python 3.11+ no Windows, execute `build.bat` e aguarde.
4. O build gera `dist/TikTokLiveRecorder.exe` e `dist/TikTokLiveRecorder.exe.sha256`.
5. No GitHub, abra **Releases > Draft a new release**, crie a tag **v5.0.0**, anexe **os dois arquivos** e publique. Este é o primeiro lançamento, usado para instalar o aplicativo.
6. Instale/copie `TikTokLiveRecorder.exe` para uma pasta permanente gravável pelo usuário, por exemplo `%LOCALAPPDATA%\Programs\TikTokLiveRecorder\`. Evite `Program Files` sem instalador e privilégios apropriados.

## Publicando a próxima atualização

1. Altere `VERSION` em `updater.py` para `5.1.0` (ou outro número maior no formato X.Y.Z).
2. Faça as alterações no código, execute `build.bat` novamente e teste o EXE.
3. Publique um novo GitHub Release com a tag `v5.1.0`, anexando `TikTokLiveRecorder.exe` e `TikTokLiveRecorder.exe.sha256` gerados juntos.
4. O aplicativo instalado verifica `releases/latest` ao iniciar e ao clicar em **Verificar atualizações**. Ao aceitar, baixa o EXE, confere o SHA-256, fecha o aplicativo, substitui o executável e o abre novamente.

## Segurança e limitações

- O checksum confirma integridade, **não prova autoria**. Proteja sua conta GitHub com 2FA e, para distribuição pública, considere assinatura Authenticode.
- O updater confia nas versões publicadas no repositório configurado. Não use repositórios de terceiros.
- A substituição funciona em pasta gravável pelo usuário. Pode falhar se antivírus, permissões ou outra instância bloquearem o EXE.
- O arquivo anterior permanece como `TikTokLiveRecorder.exe.bak` para recuperação manual.
- Os perfis/configurações ficam em `%LOCALAPPDATA%\TikTokLiveRecorder` e as gravações na pasta escolhida. Não são apagados ao atualizar.
- O aplicativo precisa estar em execução para verificar atualizações. Não há servidor de atualização separado.
- O instalador não é assinado. O Windows SmartScreen pode mostrar avisos.
- O Streamlink ainda não garante suporte a TikTok LIVE. Este updater não altera essa limitação.
- Esta versão foi verificada por compilação de sintaxe, mas **não foi testada no Windows**.
