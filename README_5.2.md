# TikTok Live Recorder 5.2.0 (beta)

- Dashboard e biblioteca local, abre vídeos com o player padrão do Windows. Para .ts, use VLC.
- Vários perfis são gravados em threads independentes, limitados por rede/CPU e suporte do Streamlink.
- Diagnóstico Streamlink e verificação FFprobe; MP4 remux sem perda com FFmpeg.
- TS originais: `<pasta>/<perfil>/_TS_originais`. MP4: `<pasta>/<perfil>`.
- Limpeza por dias: somente TS cujo MP4 validado existe na pasta de originais.
- Busca por perfis cadastrados e busca oficial no navegador. **Busca remota com foto/nome dentro do app ainda não implementada**: TikTok não disponibiliza endpoint público estável para esse uso.
- Para MP4 instale FFmpeg e FFprobe no PATH. Se não estiverem disponíveis, TS é preservado.
- A conversão sem recodificação pode falhar se o stream usar codecs incompatíveis com MP4; nesse caso o TS é preservado.
- A interface e o EXE não foram testados em Windows neste ambiente. Faça backup e valide antes de publicar a release.
