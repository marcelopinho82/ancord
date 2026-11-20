#!/usr/bin/env python3
"""
video_report.py
Gera um relatório com a duração de todos os vídeos em um diretório (e subdiretórios).
Dependência: ffprobe (instalar via: sudo apt install ffmpeg)

Uso:
    python3 video_report.py /caminho/do/diretório
    python3 video_report.py /caminho/do/diretório --output relatorio.txt
"""

import os
import sys
import json
import subprocess
import argparse
from pathlib import Path

# Extensões de vídeo reconhecidas
VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".m4v", ".mpg", ".mpeg", ".ts", ".mts", ".m2ts", ".vob",
    ".ogv", ".3gp", ".rm", ".rmvb", ".divx", ".f4v"
}


def format_duration(seconds: float) -> str:
    """Converte segundos em formato HH:MM:SS."""
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def get_video_duration(filepath: str) -> float | None:
    """Retorna a duração do vídeo em segundos usando ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        filepath
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
        return duration
    except (subprocess.TimeoutExpired, KeyError, ValueError, json.JSONDecodeError):
        return None


def find_videos(root_dir: str) -> list[Path]:
    """Percorre o diretório recursivamente e retorna todos os arquivos de vídeo."""
    videos = []
    root = Path(root_dir)
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            videos.append(path)
    return videos


def generate_report(root_dir: str, output_file: str | None = None):
    """Gera o relatório completo."""
    root = Path(root_dir).resolve()

    if not root.exists():
        print(f"Erro: diretório '{root_dir}' não encontrado.")
        sys.exit(1)

    print(f"Buscando vídeos em: {root}")
    videos = find_videos(str(root))

    if not videos:
        print("Nenhum arquivo de vídeo encontrado.")
        sys.exit(0)

    print(f"Encontrados {len(videos)} arquivo(s). Lendo durações...\n")

    lines = []
    total_seconds = 0.0
    errors = []
    max_name_len = 0

    results = []
    for i, video in enumerate(videos, 1):
        rel_path = video.relative_to(root)
        duration = get_video_duration(str(video))

        print(f"  [{i}/{len(videos)}] {rel_path}", end="")

        if duration is not None:
            total_seconds += duration
            fmt = format_duration(duration)
            results.append((str(rel_path), fmt, duration))
            max_name_len = max(max_name_len, len(str(rel_path)))
            print(f"  →  {fmt}")
        else:
            errors.append(str(rel_path))
            results.append((str(rel_path), "ERRO", None))
            max_name_len = max(max_name_len, len(str(rel_path)))
            print("  →  ERRO ao ler duração")

    # Monta o relatório
    sep = "─" * (max_name_len + 16)
    header = f"\n{'RELATÓRIO DE DURAÇÃO DE VÍDEOS':^{max_name_len + 16}}"
    subheader = f"{'Diretório: ' + str(root)}"

    lines.append(header)
    lines.append(f"{'─' * len(header.strip()):^{max_name_len + 16}}")
    lines.append(subheader)
    lines.append(sep)
    lines.append(f"{'ARQUIVO':<{max_name_len}}   {'DURAÇÃO':>8}")
    lines.append(sep)

    for rel_path, fmt, _ in results:
        lines.append(f"{rel_path:<{max_name_len}}   {fmt:>8}")

    lines.append(sep)
    lines.append(f"{'TOTAL DE ARQUIVOS:':<{max_name_len}}   {len(videos):>8}")
    lines.append(f"{'TEMPO TOTAL:':<{max_name_len}}   {format_duration(total_seconds):>8}")

    if errors:
        lines.append("")
        lines.append(f"⚠ {len(errors)} arquivo(s) com erro:")
        for e in errors:
            lines.append(f"  - {e}")

    lines.append(sep)

    report = "\n".join(lines)
    print("\n" + report)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(report + "\n")
        print(f"\nRelatório salvo em: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Gera relatório de duração de vídeos em um diretório."
    )
    parser.add_argument("directory", help="Diretório raiz para buscar vídeos")
    parser.add_argument(
        "--output", "-o",
        help="Arquivo de saída para salvar o relatório (opcional)",
        default=None
    )
    args = parser.parse_args()
    generate_report(args.directory, args.output)


if __name__ == "__main__":
    main()
    
# python3 video_report.py -o relatorio.txt .
