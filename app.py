#!/usr/bin/env python3
"""
app.py — Painel de estudos: acompanhe o progresso assistindo à playlist de vídeos.

Executar:
    pip install streamlit pandas plotly
    streamlit run app.py

Arquivos usados (na mesma pasta do app):
    relatorio.txt   -> relatório de durações (gerado pelo video_report.py ou pelo próprio app)
    playlist.m3u    -> playlist (regerada pelo app junto com o relatório)
    progresso.json  -> seu progresso e configurações (criado automaticamente)
"""

import json
import os
import re
import shutil
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

BASE = Path(__file__).parent.resolve()
REPORT = BASE / "relatorio.txt"
PLAYLIST = BASE / "playlist.m3u"
PROGRESS = BASE / "progresso.json"

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".m4v", ".mpg", ".mpeg", ".ts", ".mts", ".m2ts", ".vob",
    ".ogv", ".3gp", ".rm", ".rmvb", ".divx", ".f4v",
}

LINE_RE = re.compile(r"^(?P<name>.+?)\s+(?P<h>\d+):(?P<m>\d{2}):(?P<s>\d{2})\s*$")

st.set_page_config(page_title="Painel de Estudos", page_icon="📚", layout="wide")


# ───────────────────────────── utilidades de tempo ─────────────────────────────
def fmt_hms(seconds: float) -> str:
    seconds = int(round(max(seconds, 0)))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def breakdown(seconds: float) -> dict:
    """Quebra segundos em meses (30 d), semanas, dias, horas, minutos e segundos."""
    sec = int(round(max(seconds, 0)))
    months, sec = divmod(sec, 30 * 86400)
    weeks, sec = divmod(sec, 7 * 86400)
    days, sec = divmod(sec, 86400)
    hours, sec = divmod(sec, 3600)
    minutes, seconds = divmod(sec, 60)
    return {
        "Meses": months, "Semanas": weeks, "Dias": days,
        "Horas": hours, "Minutos": minutes, "Segundos": seconds,
    }


def breakdown_text(seconds: float) -> str:
    parts = []
    for label, val in breakdown(seconds).items():
        if val:
            singular = label[:-1] if label != "Meses" else "Mês"
            if label == "Meses":
                parts.append(f"{val} {'mês' if val == 1 else 'meses'}")
            else:
                parts.append(f"{val} {singular.lower() if val == 1 else label.lower()}")
    return ", ".join(parts) if parts else "0 segundos"


def show(fig):
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
    try:
        st.plotly_chart(fig, width="stretch")
    except TypeError:
        st.plotly_chart(fig, use_container_width=True)


# ───────────────────────────── relatório de durações ───────────────────────────
def parse_report(path: Path):
    """Retorna (lista[(nome_relativo, segundos)], diretório_raiz)."""
    videos, root = [], None
    if not path.exists():
        return videos, root
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("Diretório:"):
            root = line.split(":", 1)[1].strip()
            continue
        if line.startswith(("TEMPO TOTAL", "ARQUIVO", "TOTAL DE")):
            continue
        m = LINE_RE.match(line)
        if m and Path(m["name"]).suffix.lower() in VIDEO_EXTENSIONS:
            secs = int(m["h"]) * 3600 + int(m["m"]) * 60 + int(m["s"])
            videos.append((m["name"], secs))
    return videos, root


def probe_duration(filepath: Path):
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(filepath)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(json.loads(out.stdout)["format"]["duration"])
    except Exception:
        return None


def write_report(root: Path, results, errors):
    max_len = max((len(r[0]) for r in results), default=10)
    width = max_len + 16
    sep = "─" * width
    header = f"\n{'RELATÓRIO DE DURAÇÃO DE VÍDEOS':^{width}}"
    lines = [
        header,
        f"{'─' * len(header.strip()):^{width}}",
        f"Diretório: {root}",
        sep,
        f"{'ARQUIVO':<{max_len}}   {'DURAÇÃO':>8}",
        sep,
    ]
    total = 0
    for rel, secs in results:
        total += secs if secs is not None else 0
        lines.append(f"{rel:<{max_len}}   {fmt_hms(secs) if secs is not None else 'ERRO':>8}")
    lines += [
        sep,
        f"{'TOTAL DE ARQUIVOS:':<{max_len}}   {len(results):>8}",
        f"{'TEMPO TOTAL:':<{max_len}}   {fmt_hms(total):>8}",
    ]
    if errors:
        lines += ["", f"⚠ {len(errors)} arquivo(s) com erro:"] + [f"  - {e}" for e in errors]
    lines.append(sep)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def regenerate_report(root_dir: str, reuse: bool, progress_cb=None):
    """Varre a pasta, mede só o que for novo (se reuse=True) e regrava relatório + playlist."""
    root = Path(root_dir).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Diretório não encontrado: {root}")
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe não encontrado. Instale com: sudo apt install ffmpeg")

    old_videos, old_root = parse_report(REPORT)
    cache = {}
    if reuse and old_root and Path(old_root).resolve() == root:
        cache = dict(old_videos)

    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS)
    results, errors, new_count = [], [], 0
    for i, p in enumerate(files, 1):
        rel = str(p.relative_to(root))
        secs = cache.get(rel)
        if secs is None:
            new_count += 1
            d = probe_duration(p)
            secs = int(d) if d is not None else None
            if secs is None:
                errors.append(rel)
        results.append((rel, secs))
        if progress_cb:
            progress_cb(i / max(len(files), 1), f"{i}/{len(files)} — {rel}")

    write_report(root, results, errors)
    PLAYLIST.write_text(
        "\n".join(str(root / rel) for rel, secs in results if secs is not None) + "\n",
        encoding="utf-8",
    )
    removed = len(set(cache) - {r[0] for r in results})
    return {"total": len(results), "novos": new_count, "removidos": removed, "erros": len(errors)}


# ───────────────────────────── progresso persistente ───────────────────────────
def default_progress():
    return {
        "current_index": 0,
        "current_video": None,
        "offset_seconds": 0,
        "hours_per_day": 2.0,
        "days_per_week": 5,
        "mode": "manual",
        "exam_date": None,
        "root_dir": None,
        "history": [],
    }


def load_progress():
    p = default_progress()
    if PROGRESS.exists():
        try:
            p.update(json.loads(PROGRESS.read_text(encoding="utf-8")))
        except Exception:
            pass
    return p


def save_progress(p):
    tmp = PROGRESS.with_suffix(".tmp")
    tmp.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, PROGRESS)


def log_history(p, completed_seconds):
    today = date.today().isoformat()
    entry = {"date": today, "ts": datetime.now().isoformat(timespec="seconds"),
             "completed": int(completed_seconds)}
    if p["history"] and p["history"][-1]["date"] == today:
        p["history"][-1] = entry
    else:
        p["history"].append(entry)


def group_of(name: str) -> str:
    path = Path(name)
    if len(path.parts) > 1:
        return path.parts[0]
    stem = path.stem
    if stem[:3].isdigit():
        return stem[:3]
    m = re.match(r"[A-Za-z]+", stem)
    return m.group(0).upper() if m else "Outros"


def load_videos():
    videos, root = parse_report(REPORT)
    st.session_state.videos = videos
    st.session_state.report_root = root
    prog = st.session_state.get("progress") or load_progress()
    n = len(videos)
    idx = min(int(prog.get("current_index", 0)), n)
    cur = prog.get("current_video")
    names = [v[0] for v in videos]
    if cur and cur in names:      # acompanha o vídeo pelo nome (robusto a novos vídeos)
        idx = names.index(cur)
    prog["current_index"] = idx
    st.session_state.progress = prog
    st.session_state.pos_idx = idx


def cumulative(videos):
    cum = [0]
    for _, s in videos:
        cum.append(cum[-1] + s)
    return cum


# ───────────────────────────── callbacks de posição ────────────────────────────
def persist_position():
    videos = st.session_state.videos
    p = st.session_state.progress
    n = len(videos)
    idx = min(int(st.session_state.pos_idx), n)
    p["current_index"] = idx
    p["current_video"] = videos[idx][0] if idx < n else None
    p["offset_seconds"] = 0
    completed = cumulative(videos)[idx]
    log_history(p, completed)
    save_progress(p)


def advance():
    n = len(st.session_state.videos)
    st.session_state.pos_idx = min(st.session_state.pos_idx + 1, n)
    persist_position()


def go_back():
    st.session_state.pos_idx = max(st.session_state.pos_idx - 1, 0)
    persist_position()


def persist_settings():
    p = st.session_state.progress
    p["hours_per_day"] = float(st.session_state.cfg_hpd)
    p["days_per_week"] = int(st.session_state.cfg_dpw)
    p["mode"] = "real" if st.session_state.cfg_mode.startswith("Ritmo real") else "manual"
    ex = st.session_state.cfg_exam
    p["exam_date"] = ex.isoformat() if ex else None
    save_progress(p)


# ───────────────────────────── inicialização ───────────────────────────────────
if "progress" not in st.session_state:
    st.session_state.progress = load_progress()
if "videos" not in st.session_state:
    load_videos()

prog = st.session_state.progress
videos = st.session_state.videos
n = len(videos)

# ───────────────────────────── sidebar ─────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configurações")

    st.subheader("Ritmo de estudo")
    st.number_input("Horas de estudo por dia", 0.25, 16.0, float(prog["hours_per_day"]),
                    step=0.25, key="cfg_hpd", on_change=persist_settings)
    st.slider("Dias de estudo por semana", 1, 7, int(prog["days_per_week"]),
              key="cfg_dpw", on_change=persist_settings)
    modes = ["Meta manual (horas/dia acima)", "Ritmo real (calculado do meu histórico)"]
    st.radio("Base da estimativa", modes, index=1 if prog["mode"] == "real" else 0,
             key="cfg_mode", on_change=persist_settings)
    exam = date.fromisoformat(prog["exam_date"]) if prog.get("exam_date") else None
    st.date_input("Data da prova (opcional)", value=exam, key="cfg_exam",
                  format="DD/MM/YYYY", on_change=persist_settings)

    st.divider()
    st.subheader("🔄 Atualizar relatório")
    default_root = prog.get("root_dir") or st.session_state.get("report_root") or ""
    root_input = st.text_input("Pasta dos vídeos", value=default_root,
                               help="Varre subpastas. Use quando adicionar novos vídeos.")
    reuse = st.checkbox("Reaproveitar durações já medidas (mais rápido)", value=True)
    if st.button("Regerar relatório e playlist", type="primary"):
        if not root_input.strip():
            st.error("Informe a pasta dos vídeos.")
        else:
            bar = st.progress(0.0, text="Iniciando…")
            try:
                info = regenerate_report(
                    root_input.strip(), reuse,
                    lambda frac, txt: bar.progress(min(frac, 1.0), text=txt),
                )
                prog["root_dir"] = root_input.strip()
                save_progress(prog)
                load_videos()
                bar.empty()
                st.success(f"{info['total']} vídeos • {info['novos']} novos medidos • "
                           f"{info['removidos']} removidos • {info['erros']} com erro")
                st.rerun()
            except Exception as e:
                bar.empty()
                st.error(str(e))

    st.divider()
    with st.expander("⚠️ Zerar progresso"):
        if st.checkbox("Confirmo que quero apagar meu progresso e histórico"):
            if st.button("Zerar tudo"):
                fresh = default_progress()
                for k in ("hours_per_day", "days_per_week", "mode", "exam_date", "root_dir"):
                    fresh[k] = prog[k]
                save_progress(fresh)
                st.session_state.progress = fresh
                load_videos()
                st.rerun()

# ───────────────────────────── corpo ───────────────────────────────────────────
st.title("📚 Painel de Estudos")

if n == 0:
    st.warning("Nenhum vídeo encontrado em `relatorio.txt`. Use **Regerar relatório e playlist** "
               "na barra lateral informando a pasta dos vídeos.")
    st.stop()

cum = cumulative(videos)
total_s = cum[-1]
idx = min(st.session_state.pos_idx, n)

# ── Onde estou ──
st.subheader("📍 Onde estou agora")
c1, c4 = st.columns([5, 3])
with c1:
    st.selectbox(
        "Vídeo que estou assistindo (ou o próximo a assistir)",
        options=list(range(n + 1)),
        format_func=lambda i: (f"{i + 1:>4}/{n} — {videos[i][0]}  ({fmt_hms(videos[i][1])})"
                               if i < n else "🏁 Terminei todos os vídeos"),
        key="pos_idx", on_change=persist_position,
    )
with c4:
    st.write("")
    b1, b2 = st.columns(2)
    b1.button("✅ Concluí, avançar", on_click=advance, disabled=idx >= n, width="stretch")
    b2.button("↩️ Voltar 1", on_click=go_back, disabled=idx <= 0, width="stretch")

idx = min(st.session_state.pos_idx, n)
off = 0
done_s = cum[idx]
remaining_s = max(total_s - done_s, 0)
pct_time = done_s / total_s * 100 if total_s else 0
pct_videos = idx / n * 100

# ── Ritmo e estimativa ──
hist = prog["history"]


def real_pace_per_calendar_day():
    if len(hist) < 2:
        return None
    d = (date.fromisoformat(hist[-1]["date"]) - date.fromisoformat(hist[0]["date"])).days
    gained = hist[-1]["completed"] - hist[0]["completed"]
    if d <= 0 or gained <= 0:
        return None
    return gained / d


hpd = float(prog["hours_per_day"])
dpw = int(prog["days_per_week"])
manual_pace = hpd * 3600 * dpw / 7           # segundos assistidos por dia corrido
real_pace = real_pace_per_calendar_day()
use_real = prog["mode"] == "real" and real_pace is not None
pace = real_pace if use_real else manual_pace
eta_seconds = remaining_s / pace * 86400 if pace > 0 else 0
now = datetime.now()
end_date = now + timedelta(seconds=eta_seconds)

# ── KPIs ──
st.divider()
k1, k2, k3, k4 = st.columns(4)
k1.metric("Progresso (tempo)", f"{pct_time:.2f}%")
k2.metric("Progresso (vídeos)", f"{pct_videos:.2f}%", f"{idx} de {n}", delta_color="off")
k3.metric("Assistido", fmt_hms(done_s), f"de {fmt_hms(total_s)}", delta_color="off")
k4.metric("Falta assistir", fmt_hms(remaining_s), f"{n - idx} vídeos", delta_color="off")
st.progress(min(pct_time / 100, 1.0), text=f"{pct_time:.2f}% concluído • "
            f"{done_s / 3600:.1f} h de {total_s / 3600:.1f} h")

# ── Estimativa de término ──
st.subheader("⏳ Estimativa para terminar")
if remaining_s <= 0:
    st.success("🎉 Parabéns! Você assistiu todos os vídeos.")
else:
    src = (f"ritmo real do histórico ({pace * 7 / 3600:.1f} h/semana)" if use_real
           else f"meta manual ({hpd:g} h/dia, {dpw} dias/semana)")
    if prog["mode"] == "real" and real_pace is None:
        st.info("Ainda não há histórico suficiente (preciso de registros em dias diferentes) — "
                "usando a meta manual por enquanto.")
    cols = st.columns(6)
    for col, (label, val) in zip(cols, breakdown(eta_seconds).items()):
        col.metric(label, val)
    st.caption(f"Base: {src}. Previsão de término: **{end_date:%d/%m/%Y}** "
               f"({end_date:%A}). Tempo corrido: {breakdown_text(eta_seconds)} "
               f"(mês = 30 dias).")
    if abs(manual_pace - (real_pace or manual_pace)) > 1 and real_pace:
        other = remaining_s / (manual_pace if use_real else real_pace) * 86400
        st.caption(f"Comparação: pela {'meta manual' if use_real else 'média real'} seriam "
                   f"{breakdown_text(other)}.")
    if prog.get("exam_date"):
        exam_d = date.fromisoformat(prog["exam_date"])
        days_left = (exam_d - date.today()).days
        if days_left <= 0:
            st.error("A data da prova já passou ou é hoje.")
        else:
            study_days = days_left * dpw / 7
            need_h = remaining_s / 3600 / study_days if study_days > 0 else float("inf")
            status = "✅ dá tempo no ritmo atual" if end_date.date() <= exam_d else "⚠️ no ritmo atual não termina antes"
            st.info(f"Faltam **{days_left} dias** para a prova. Para terminar os vídeos até lá, "
                    f"precisa assistir ≈ **{need_h:.2f} h por dia de estudo** "
                    f"({dpw} dias/semana). {status}.")

st.divider()

# ── dados auxiliares ──
rows = []
for i, (name, secs) in enumerate(videos):
    if i < idx:
        d, status = secs, "✅ Concluído"
    elif i == idx:
        d, status = off, "▶️ Atual"
    else:
        d, status = 0, "⏳ Pendente"
    rows.append({"#": i + 1, "Vídeo": name, "Módulo": group_of(name), "Duração (s)": secs,
                 "Assistido (s)": d, "Status": status, "Acumulado (h)": cum[i + 1] / 3600})
df = pd.DataFrame(rows)
df["Duração"] = df["Duração (s)"].apply(fmt_hms)

tab1, tab2, tab3, tab4 = st.tabs(["📊 Visão geral", "🧩 Por módulo", "📈 Ritmo e projeção", "🎬 Vídeos"])

# ── Visão geral ──
with tab1:
    a, b = st.columns(2)
    with a:
        fig = go.Figure(go.Pie(labels=["Assistido", "Falta"], values=[done_s, remaining_s],
                               hole=0.6, sort=False, marker=dict(colors=["#2ecc71", "#e5e7eb"]),
                               textinfo="percent"))
        fig.update_layout(title="Progresso por tempo", annotations=[
            dict(text=f"{pct_time:.1f}%", x=0.5, y=0.5, font_size=28, showarrow=False)])
        show(fig)
    with b:
        fig = go.Figure(go.Pie(labels=["Concluídos", "Restantes"], values=[idx, n - idx],
                               hole=0.6, sort=False, marker=dict(colors=["#3498db", "#e5e7eb"]),
                               textinfo="percent"))
        fig.update_layout(title="Progresso por vídeos", annotations=[
            dict(text=f"{pct_videos:.1f}%", x=0.5, y=0.5, font_size=28, showarrow=False)])
        show(fig)

    a, b = st.columns(2)
    with a:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["#"], y=df["Acumulado (h)"], mode="lines", fill="tozeroy",
                                 name="Horas acumuladas", line=dict(color="#6366f1")))
        fig.add_trace(go.Scatter(x=[idx], y=[done_s / 3600], mode="markers",
                                 marker=dict(size=14, color="#ef4444", symbol="star"),
                                 name="Você está aqui"))
        fig.update_layout(title="Horas acumuladas ao longo da playlist",
                          xaxis_title="Nº do vídeo", yaxis_title="Horas")
        show(fig)
    with b:
        fig = px.histogram(df, x=df["Duração (s)"] / 60, nbins=30, color="Status",
                           color_discrete_map={"✅ Concluído": "#2ecc71", "▶️ Atual": "#f59e0b",
                                               "⏳ Pendente": "#94a3b8"},
                           title="Distribuição das durações dos vídeos")
        fig.update_layout(xaxis_title="Minutos", yaxis_title="Qtd. de vídeos", barmode="stack")
        show(fig)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Duração média", fmt_hms(df["Duração (s)"].mean()))
    m2.metric("Mediana", fmt_hms(df["Duração (s)"].median()))
    m3.metric("Mais curto", fmt_hms(df["Duração (s)"].min()))
    m4.metric("Mais longo", fmt_hms(df["Duração (s)"].max()))

# ── Por módulo ──
with tab2:
    g = df.groupby("Módulo", sort=True).agg(
        videos=("#", "count"), total=("Duração (s)", "sum"), feito=("Assistido (s)", "sum"),
        concluidos=("Status", lambda s: (s == "✅ Concluído").sum())).reset_index()
    g["falta"] = g["total"] - g["feito"]
    g["pct"] = g["feito"] / g["total"] * 100
    fig = go.Figure()
    fig.add_bar(y=g["Módulo"], x=g["feito"] / 3600, name="Assistido", orientation="h",
                marker_color="#2ecc71")
    fig.add_bar(y=g["Módulo"], x=g["falta"] / 3600, name="Falta", orientation="h",
                marker_color="#cbd5e1")
    fig.update_layout(barmode="stack", title="Horas por módulo (assistido × falta)",
                      xaxis_title="Horas", yaxis=dict(type="category", autorange="reversed"),
                      height=max(350, 22 * len(g) + 120))
    show(fig)

    a, b = st.columns(2)
    with a:
        fig = px.treemap(g, path=["Módulo"], values="total", color="pct",
                         color_continuous_scale="RdYlGn", range_color=(0, 100),
                         title="Tamanho (horas) e % concluído por módulo")
        show(fig)
    with b:
        fig = px.bar(g, x="Módulo", y="pct", text=g["pct"].round(0).astype(int).astype(str) + "%",
                     title="% concluído por módulo")
        fig.update_layout(yaxis_range=[0, 100], xaxis=dict(type="category"))
        show(fig)

    tbl = pd.DataFrame({
        "Módulo": g["Módulo"], "Vídeos": g["videos"], "Concluídos": g["concluidos"],
        "Total": g["total"].apply(fmt_hms), "Falta": g["falta"].apply(fmt_hms),
        "% concluído": g["pct"].round(1),
    })
    st.dataframe(tbl, hide_index=True, width="stretch",
                 column_config={"% concluído": st.column_config.ProgressColumn(
                     "% concluído", min_value=0, max_value=100, format="%.1f%%")})

# ── Ritmo e projeção ──
with tab3:
    if len(hist) >= 2:
        hdf = pd.DataFrame(hist)
        hdf["date"] = pd.to_datetime(hdf["date"])
        hdf["ganho_h"] = hdf["completed"].diff().clip(lower=0) / 3600
        daily = hdf.dropna(subset=["ganho_h"])
        a, b = st.columns(2)
        with a:
            fig = px.bar(daily, x="date", y="ganho_h", title="Horas avançadas por dia")
            fig.add_hline(y=hpd, line_dash="dot", line_color="#ef4444")
            fig.update_layout(xaxis_title="", yaxis_title="Horas")
            show(fig)
        with b:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=hdf["date"], y=hdf["completed"] / 3600, mode="lines+markers",
                                     name="Progresso real", line=dict(color="#2ecc71")))
            if remaining_s > 0:
                fig.add_trace(go.Scatter(x=[now, end_date], y=[done_s / 3600, total_s / 3600],
                                         mode="lines", name="Projeção",
                                         line=dict(color="#6366f1", dash="dash")))
            fig.add_hline(y=total_s / 3600, line_dash="dot", line_color="#94a3b8")
            if prog.get("exam_date"):
                ex_dt = datetime.fromisoformat(prog["exam_date"])
                fig.add_shape(type="line", x0=ex_dt, x1=ex_dt, y0=0, y1=1, yref="paper",
                              line=dict(color="#ef4444", dash="dot"))
                fig.add_annotation(x=ex_dt, y=1, yref="paper", text="Prova", showarrow=False,
                                   font_color="#ef4444")
            fig.update_layout(title="Progresso acumulado e projeção", yaxis_title="Horas assistidas")
            show(fig)
        s1, s2, s3 = st.columns(3)
        s1.metric("Dias com registro", len(hist))
        s2.metric("Média real", f"{real_pace * 7 / 3600:.1f} h/sem" if real_pace else "—")
        s3.metric("Melhor dia", f"{daily['ganho_h'].max():.1f} h" if len(daily) else "—")
    else:
        st.info("O histórico aparece depois que você atualizar sua posição em pelo menos dois dias "
                "diferentes. Cada atualização é registrada automaticamente.")

    if remaining_s > 0:
        st.markdown("**Simulador de ritmo** — quanto tempo levaria com outras cargas diárias:")
        sim = []
        for h in (0.5, 1, 1.5, 2, 3, 4, 6):
            secs = remaining_s / (h * 3600 * dpw / 7) * 86400
            sim.append({"Horas/dia": h, "Previsão de término": f"{now + timedelta(seconds=secs):%d/%m/%Y}",
                        "Tempo corrido": breakdown_text(secs)})
        st.dataframe(pd.DataFrame(sim), hide_index=True, width="stretch")

# ── Vídeos ──
with tab4:
    if idx < n:
        st.markdown(f"**Próximos 10 vídeos** (a partir do atual)")
        nxt = df.iloc[idx: idx + 10][["#", "Vídeo", "Duração", "Status"]]
        st.dataframe(nxt, hide_index=True, width="stretch")
        pend = df.iloc[idx:].nlargest(10, "Duração (s)")[["#", "Vídeo", "Duração"]]
        st.markdown("**10 maiores vídeos ainda pendentes**")
        st.dataframe(pend, hide_index=True, width="stretch")
    st.markdown("**Lista completa**")
    f1, f2 = st.columns([3, 2])
    q = f1.text_input("Buscar vídeo", "")
    stt = f2.multiselect("Status", ["✅ Concluído", "▶️ Atual", "⏳ Pendente"],
                         default=["✅ Concluído", "▶️ Atual", "⏳ Pendente"])
    view = df[df["Status"].isin(stt)]
    if q:
        view = view[view["Vídeo"].str.contains(q, case=False, regex=False)]
    st.dataframe(view[["#", "Vídeo", "Módulo", "Duração", "Status"]], hide_index=True,
                 width="stretch", height=450)
