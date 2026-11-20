# 📚 Painel de Estudos

Aplicativo em [Streamlit](https://streamlit.io) para acompanhar o progresso ao assistir uma grande playlist de vídeos (curso, concurso, certificação): mostra quanto já foi assistido, quanto falta e uma estimativa de quando você termina.

## Funcionalidades

- **Posição atual:** escolha o vídeo em que está (e, opcionalmente, o minuto/segundo). O app recalcula tudo.
- **Progresso salvo:** a posição e o histórico ficam em `progresso.json`; ao recarregar, o app volta de onde você parou.
- **Progresso em %:** por tempo e por quantidade de vídeos, além de horas assistidas e restantes (HH:MM:SS).
- **Estimativa de término:** tempo restante em meses, semanas, dias, horas, minutos e segundos, com data prevista. Pode usar uma meta manual (horas/dia e dias/semana) ou o seu ritmo real calculado do histórico.
- **Data da prova (opcional):** informa quantas horas por dia são necessárias para terminar a tempo.
- **Gráficos:** progresso (rosquinhas), horas acumuladas, distribuição de durações, horas por módulo, treemap, % por módulo, horas avançadas por dia, projeção até o fim e simulador de ritmo.
- **Lista de vídeos:** próximos vídeos, maiores pendentes e lista completa com busca e filtro por status.
- **Regerar relatório:** botão na barra lateral que varre a pasta de vídeos, mede só os arquivos novos e atualiza `relatorio.txt` e `playlist.m3u`.

## Requisitos

- Python 3.10+
- [FFmpeg](https://ffmpeg.org) (para o `ffprobe`, usado ao medir a duração dos vídeos)
  - Debian/Ubuntu: `sudo apt install ffmpeg`
  - macOS: `brew install ffmpeg`
- Dependências Python: `streamlit`, `pandas`, `plotly`

## Instalação

```bash
git clone <url-do-repositorio>
cd <pasta-do-repositorio>

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

```bash
streamlit run app.py
```

Na primeira execução não existe `relatorio.txt`. Na barra lateral:

1. Informe a **pasta dos vídeos** (as subpastas também são varridas).
2. Clique em **Regerar relatório e playlist**.

Depois, é só marcar em qual vídeo você está. Sempre que adicionar vídeos novos, repita o passo 2; com a opção "Reaproveitar durações já medidas" marcada, só os arquivos novos são medidos.

### Importando um relatório existente

Se você já tem um `relatorio.txt` no formato abaixo, basta colocá-lo na pasta do app:

```
Diretório: /caminho/dos/videos
ARQUIVO         DURAÇÃO
101101.mp4     00:04:49
101102.mp4     00:04:45
```

## Arquivos do projeto

| Arquivo            | Descrição                                                              |
|--------------------|------------------------------------------------------------------------|
| `app.py`           | Aplicativo Streamlit                                                   |
| `requirements.txt` | Dependências Python                                                    |
| `relatorio.txt`    | Durações dos vídeos (gerado; não versionado)                           |
| `playlist.m3u`     | Playlist para o player (gerada; não versionada)                        |
| `progresso.json`   | Posição, histórico e configurações (gerado; não versionado)            |

## Como funciona

- Os vídeos são ordenados por caminho, na mesma ordem do relatório.
- A posição é guardada pelo **nome do vídeo**, então adicionar novos vídeos não desloca o seu progresso.
- Os módulos dos gráficos são agrupados pelos 3 primeiros dígitos do nome do arquivo (ex.: `101`, `204`), por letras iniciais (ex.: `MF`) ou pela primeira subpasta.
- O ritmo real é calculado pelo avanço entre o primeiro e o último registro do histórico (precisa de registros em dias diferentes).
- Nas estimativas, 1 mês equivale a 30 dias.

## Licença

Uso pessoal. Defina a licença que preferir antes de publicar.
