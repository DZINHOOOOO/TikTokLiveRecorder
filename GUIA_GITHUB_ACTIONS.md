# Compilacao automatica no GitHub Actions

Este projeto e a base **5.2.0 beta**. Nao publique como atualizacao estavel sem testar as funcoes de gravacao/conversao.

## Primeira configuracao (uma unica vez)
1. No repositorio `DZINHOOOOO/TikTokLiveRecorder`, envie **todos os arquivos deste projeto**, incluindo a pasta oculta `.github/workflows/release.yml`, para a branch `main`. No GitHub, use **Add file > Upload files**. Arraste o conteudo da pasta do projeto, nao o ZIP inteiro. Para a pasta oculta `.github`, pode ser mais facil usar GitHub Desktop ou Git.
2. Em **Settings > Actions > General > Workflow permissions**, escolha **Read and write permissions** e salve (se disponivel). O workflow usa `GITHUB_TOKEN` do repositorio; nao precisa criar token pessoal.
3. **Nao crie uma tag v5.2.0 enquanto estiver testando a beta.** O workflow publica a Release assim que receber uma tag correspondente a versao em `updater.py`.

## Para publicar uma versao testada
1. Atualize o codigo e `VERSION` em `updater.py`, por exemplo `5.2.0`.
2. Envie as mudancas para a branch `main`.
3. No GitHub, crie uma tag **nova** `v5.2.0` apontando para o commit correto. Pode usar `git tag v5.2.0` seguido de `git push origin v5.2.0` ou a interface do GitHub para criar uma Release/tag. **Nao publique uma Release manualmente com assets**, pois o workflow criara a Release e anexara os arquivos.
4. Em **Actions > Build and publish Windows release**, acompanhe a compilacao.
5. Em **Releases**, confira `TikTokLiveRecorder.exe` e `TikTokLiveRecorder.exe.sha256`.
6. Teste atualizacao com backup da versao anterior.

## Importante
- Cada nova versao precisa de uma **nova tag**. Tags ja publicadas nao devem ser reutilizadas.
- O workflow so roda automaticamente em tags `v...`, evitando publicar a cada alteracao no codigo.
- Nao existe garantia de compilacao/reproducao sem teste real no Windows. O GitHub Actions compila, mas nao testa o TikTok ou a conversao FFmpeg.
- A versao de FFmpeg instalada no seu PC continua necessaria para conversao local.
- Para o atualizador continuar funcionando, o EXE e SHA256 mantem os mesmos nomes.
- Caso a compilacao falhe, abra a execucao em Actions para ver o erro antes de publicar.
