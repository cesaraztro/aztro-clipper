"""CLI de aztro-clipper. Cada etapa es un comando; `clipper run` las encadena."""
import argparse
import sys
import time

from . import config


def _ep(a):
    return config.Episodio(a.episodio)


def cmd_doctor(a):
    from .etapas import doctor
    sys.exit(doctor.correr())


def cmd_setup(a):
    from .etapas import setup
    sys.exit(setup.correr(sin_ffmpeg=a.sin_ffmpeg, sin_skills=a.sin_skills, modelos=a.modelos,
                          marca=a.marca, nombre=a.nombre))


def cmd_marca(a):
    d = config.crear_marca(a.id, a.nombre)
    print(f"Marca lista en {d}\nEdita marca.json (colores, vocabulario, CTA, música) y criterio.md (qué temas funcionan).")


def cmd_actualizar(a):
    import subprocess
    if not (config.REPO / ".git").exists():
        raise SystemExit("Esta instalación no viene de git. Reinstala siguiendo INSTALAR.md.")
    subprocess.run(["git", "-C", str(config.REPO), "pull", "--ff-only"], check=True)
    subprocess.run(["uv", "tool", "install", "--python", "3.12", "--force", "-e", str(config.REPO)], check=True)
    from .etapas import setup
    setup.instalar_skills()
    print("aztro-clipper actualizado.")


def cmd_ingest(a):
    from .etapas import ingest
    ingest.correr(a.videos, a.marca, slug=a.slug, audio=a.audio, guion=a.guion, hablantes=a.hablantes,
                  url_largo=a.url, palabra=a.palabra)


def cmd_transcribe(a):
    from .etapas import segment, transcribe
    ep = _ep(a)
    transcribe.correr(ep, forzar=a.forzar)
    segment.correr(ep)


def cmd_select(a):
    from .etapas import select
    ep = _ep(a)
    if a.validar:
        select.validar(ep)
    elif a.llm:
        select.con_llm(ep)
    else:
        print(f"Instrucciones para el agente: {select.instrucciones(ep)}")


def cmd_plan(a):
    from .etapas import plan
    plan.correr(_ep(a), solo=a.clips)


def cmd_reframe(a):
    from .etapas import reframe
    reframe.correr(_ep(a), solo=a.clips)


def cmd_render(a):
    from .etapas import render
    render.correr(_ep(a), solo=a.clips, forzar=a.forzar)


def cmd_qa(a):
    from .etapas import qa
    ok = qa.correr(_ep(a), solo=a.clips, rapido=a.rapido)
    sys.exit(0 if ok else 1)


def cmd_package(a):
    from .etapas import package
    package.correr(_ep(a), solo=a.clips)


def cmd_cta(a):
    from .etapas import cta
    ep = _ep(a)
    if a.confirmar:
        cta.confirmar(ep); print("Marcada como configurada en ManyChat."); return
    if a.palabra or a.url:
        palabra = a.palabra or ep.meta.get("palabra_cta")
        url = a.url or ep.meta.get("url_largo")
        if not (palabra and url):
            raise SystemExit("Necesito --palabra y --url (link del video largo en YouTube).")
        print(f"Registrada: {cta.registrar(ep, palabra, url)} → {url}")
    print(f"Checklist de ManyChat: {cta.checklist(ep)}")


def cmd_approve(a):
    from .etapas import publish
    publish.aprobar(_ep(a), a.clips, quien=a.por)


def cmd_publish(a):
    from .etapas import publish
    publish.correr(_ep(a), inicio=a.desde, mejores_horas=a.mejores_horas)


def cmd_run(a):
    """Corre de punta a punta lo que no requiere decisión humana; se detiene en la selección si falta."""
    from .etapas import plan, qa, reframe, render, select, package
    ep = _ep(a)
    t0 = time.time()
    if not ep.ruta("04_segment", "transcripcion.md").exists():
        cmd_transcribe(a)
    if not ep.ruta("05_select", "seleccion.json").exists():
        print(f"\nAlto: falta elegir clips. Instrucciones: {select.instrucciones(ep)}")
        return
    select.validar(ep)
    plan.correr(ep, solo=a.clips)
    reframe.correr(ep, solo=a.clips)
    render.correr(ep, solo=a.clips, forzar=a.forzar)
    ok = qa.correr(ep, solo=a.clips)
    package.correr(ep, solo=a.clips)
    print(f"\nListo en {(time.time() - t0) / 60:.1f} min · QA {'OK' if ok else 'con observaciones'} · {ep.ruta('entregables')}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="clipper", description="De un video largo a clips verticales con CTA.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setup", help="Instala lo que falte (ffmpeg, skills de agentes, modelos) en Mac, Windows o Linux")
    s.add_argument("--sin-ffmpeg", action="store_true"); s.add_argument("--sin-skills", action="store_true")
    s.add_argument("--modelos", action="store_true", help="Descarga ya el modelo de transcripción (~1.5 GB)")
    s.add_argument("--marca", help="Crea una marca con este id"); s.add_argument("--nombre", help="Nombre visible de la marca")
    s.set_defaults(f=cmd_setup)
    s = sub.add_parser("doctor", help="Verifica la instalación"); s.set_defaults(f=cmd_doctor)
    s = sub.add_parser("marca", help="Crea una marca nueva desde la plantilla")
    s.add_argument("id"); s.add_argument("--nombre"); s.set_defaults(f=cmd_marca)
    s = sub.add_parser("actualizar", help="Baja la última versión del repo"); s.set_defaults(f=cmd_actualizar)

    s = sub.add_parser("ingest", help="Registra un video largo (o crudos de cámara) como episodio")
    s.add_argument("videos", nargs="+"); s.add_argument("--marca", required=True); s.add_argument("--slug")
    s.add_argument("--audio", help="Audio externo (WAV) a sincronizar con la cámara")
    s.add_argument("--guion", help="Guion en PDF (opcional)")
    s.add_argument("--hablantes", type=int, help="Número de personas que hablan")
    s.add_argument("--url", help="Link del video largo en YouTube"); s.add_argument("--palabra", help="Palabra CTA")
    s.set_defaults(f=cmd_ingest)

    def ep_cmd(nombre, ayuda, f, clips=True):
        s = sub.add_parser(nombre, help=ayuda); s.add_argument("episodio"); s.set_defaults(f=f)
        if clips:
            s.add_argument("--clips", nargs="*", help="Solo estos clips (ids)")
        return s

    s = ep_cmd("transcribe", "Transcribe y divide en oraciones", cmd_transcribe, clips=False)
    s.add_argument("--forzar", action="store_true")
    s = ep_cmd("select", "Prepara, valida o resuelve (LLM) la selección de clips", cmd_select, clips=False)
    s.add_argument("--validar", action="store_true"); s.add_argument("--llm", action="store_true")
    ep_cmd("plan", "Convierte la selección en recetas de montaje (clip.json)", cmd_plan)
    ep_cmd("reframe", "Encuadre vertical siguiendo a quien habla", cmd_reframe)
    s = ep_cmd("render", "Renderiza los clips", cmd_render); s.add_argument("--forzar", action="store_true")
    s = ep_cmd("qa", "Control de calidad automático", cmd_qa); s.add_argument("--rapido", action="store_true", help="Sin re-transcribir")
    ep_cmd("package", "Copy por red, portada y entregables", cmd_package)
    s = ep_cmd("cta", "Registra la palabra CTA y genera el checklist de ManyChat", cmd_cta, clips=False)
    s.add_argument("--palabra"); s.add_argument("--url"); s.add_argument("--confirmar", action="store_true")
    s = ep_cmd("approve", "Aprueba clips para publicar (guarda la huella de cada video)", cmd_approve)
    s.add_argument("--por", default="humano", help="Quién aprueba")
    s = ep_cmd("publish", "Propone el calendario de publicación (Metricool)", cmd_publish, clips=False)
    s.add_argument("--desde", help="Fecha de inicio AAAA-MM-DD (por defecto: mañana)")
    s.add_argument("--mejores-horas", help="JSON con mejores horas por red (de Metricool)")
    s = ep_cmd("run", "Corre todas las etapas pendientes", cmd_run); s.add_argument("--forzar", action="store_true")

    for flujo in (sys.stdout, sys.stderr):  # la consola de Windows no siempre es UTF-8 (✓, ✗, acentos)
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    a = p.parse_args(argv)
    try:
        a.f(a)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
