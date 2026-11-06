# TikTok Live Recorder 2.0 (protótipo)

## Novidades
- Cole `https://www.tiktok.com/@usuario`, `@usuario` ou apenas `usuario`.
- Cartões de perfil com foto pública quando disponível, ou inicial como alternativa.
- Estados por perfil, checagem manual, monitoramento periódico, pasta personalizada e visual renovado.
- Configuração persistida em `%LOCALAPPDATA%\TikTokLiveRecorder\config.json`.

## Como usar
1. Instale Python 3.11+ e Streamlink para Windows. Confirme no CMD: `streamlink --version`.
2. Extraia o ZIP. Execute `build.bat` para instalar PySide6/PyInstaller e criar o EXE.
3. Abra `dist\TikTokLiveRecorder.exe`, adicione perfis e clique em **Verificar agora**.
4. Gravações, quando possíveis, ficam em `Vídeos\TikTokLiveRecorder\usuario`.

## Limitações importantes
- **Não há garantia de gravação de TikTok LIVE**: o Streamlink pode não reconhecer links do TikTok. O aplicativo exibe um erro específico quando o plugin não existe. Para captura real seria necessário integrar uma fonte de stream autorizada e funcional.
- A foto de perfil é obtida, quando possível, de metadados públicos da página. TikTok pode bloquear esse acesso, então o cartão mostrará a inicial do usuário.
- O app **não foi testado em Windows neste ambiente** e é entregue como código-fonte para compilação, não como EXE pronto.
- Não contorna contas privadas, autenticação ou controles de acesso. Grave apenas transmissões cujo uso seja permitido.
- O vídeo é gravado em `.ts` para reduzir risco de perda se a live cair. Não inclui conversão para MP4 nesta versão.


## Novidades v3.0
- Logo roxa exclusiva no aplicativo, na barra de tarefas e no executável.
- Fechar no X minimiza para a área de notificação (ícones ocultos) quando o Windows oferece suporte.
- Clique duplo no ícone da bandeja abre a janela.
- Menu com Abrir, Verificar agora e Encerrar aplicativo.
- Para realmente encerrar, clique com o botão direito no ícone da bandeja e escolha Encerrar aplicativo.
- O monitoramento automático permanece ativo enquanto o processo estiver em execução e a opção estiver marcada.
- Se a bandeja não estiver disponível, fechar encerra o programa normalmente.


## Novidades v4.0: pesquisa de perfis
- Ao digitar, a barra sugere perfis **já adicionados** cujo @ corresponde às letras.
- O botão **Pesquisar no TikTok** abre a busca de usuários no site oficial para descobrir novos perfis. Copie o link ou @ encontrado e cole no aplicativo.
- Importante: a API oficial não disponibiliza uma pesquisa pública irrestrita de usuários. Por isso, **o aplicativo não apresenta sugestões remotas automaticamente** nem inventa perfis.
- A gravação continua condicionada ao suporte do Streamlink e pode não funcionar para TikTok.
