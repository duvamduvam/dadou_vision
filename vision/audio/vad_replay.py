"""Rejeu du VAD de PRODUCTION sur un enregistrement — mesure combien de fois
EnergyVad déclencherait sur du son capté en conditions réelles (lot D0,
campagne de mesures rue, cf. dadou_robot_ros/docs/
etude-declenchement-conversation.md §5.5/§7 « D0 — Mesures & calibration »).

QUOI : module PUR (aucun rclpy, aucun subprocess arecord) qui rejoue un
       tampon PCM déjà enregistré à travers EXACTEMENT le même code que la
       prod : vision.audio.vad.EnergyVad (la machine à états), alimenté par
       vision.audio.mic.frame_rms (même calcul de RMS que MicCapture — extrait
       en fonction pure PRÉCISÉMENT pour cette raison, cf. son docstring).
POURQUOI réutiliser EnergyVad/frame_rms plutôt que réécrire un calcul
       équivalent ici : règle du projet — « la vérification doit exécuter le
       MÊME code que la prod » (cf. CLAUDE.md) — une réimplémentation, même
       fidèle en apparence, pourrait diverger silencieusement (un paramètre
       VadConfig oublié, un arrondi différent) et fausser la mesure de la
       campagne D0 sans que personne ne s'en aperçoive.
POURQUOI aucun resampling : le pipeline chat (MicCapture) enregistre en
       16 kHz mono 16 bits (cf. vision.nodes.chat_node.MIC_SAMPLE_RATE) — un
       wav dans un autre format donnerait un RMS/un timing qui NE correspond
       PAS à ce que vivrait la vraie chaîne micro -> VAD. Mieux vaut un refus
       explicite (message clair) qu'une mesure trompeuse : enregistrez au bon
       format dès le départ, cf. conf/scripts/enregistre-rue.sh.
"""
from __future__ import annotations

import sys
import wave
from typing import List, Tuple

from vision.audio.mic import frame_rms
from vision.audio.vad import EnergyVad

# Durée d'une trame (ms) — MÊME valeur que côté chat_node (cf.
# vision.nodes.chat_node.MIC_FRAME_MS) : le rejeu doit découper le flux
# EXACTEMENT comme le fait MicCapture en prod, sinon la temporisation du VAD
# (calibration_ms, end_silence_ms...) ne mesure pas la même chose. Reprise en
# dur ici (pas importée depuis chat_node, qui importe rclpy et échouerait sur
# le host/CI, cf. CLAUDE.md) — ce commentaire est le garde-fou qui relie les
# deux valeurs si l'une des deux change un jour.
FRAME_MS = 30

# Largeur d'un échantillon S16_LE mono (octets) — même contrainte que
# vision.audio.mic._BYTES_PER_SAMPLE (non importé : privé à ce module-là,
# dupliquer une constante aussi simple est plus sûr qu'un import d'un symbole
# underscore d'un autre module).
_BYTES_PER_SAMPLE = 2


def replay(pcm: bytes, sample_rate: int, frame_ms: int, vad: EnergyVad) -> List[Tuple[float, str]]:
    """Rejoue `pcm` (S16_LE mono brut) trame par trame à travers `vad` — MÊME
    découpage en trames de taille fixe que MicCapture.read_frame (la dernière
    trame partielle, si le fichier ne tombe pas juste, est ignorée plutôt que
    complétée par du padding qui fausserait son RMS). Retourne les
    événements dans l'ordre, chacun sous la forme (t_secondes, kind) avec
    kind = "speech_start" | "speech_end"."""
    frame_bytes = int(round(sample_rate * frame_ms / 1000)) * _BYTES_PER_SAMPLE
    events: List[Tuple[float, str]] = []

    offset = 0
    frame_index = 0
    while offset + frame_bytes <= len(pcm):
        frame = pcm[offset:offset + frame_bytes]
        level = frame_rms(frame)
        event = vad.feed(level)
        if event is not None:
            # Horodatage à la FIN de la trame qui a produit l'événement :
            # cohérent avec EnergyVad, qui incrémente ses compteurs internes
            # de frame_ms AVANT de tester ses seuils (cf. _feed_speech/
            # _feed_idle dans vision.audio.vad) — l'événement est donc bien
            # "connu" au terme de cette trame, pas à son début.
            t = (frame_index + 1) * frame_ms / 1000
            events.append((t, event.kind))
        offset += frame_bytes
        frame_index += 1

    return events


def _load_wav_pcm(path: str) -> Tuple[bytes, int]:
    """Charge un wav mono 16 bits TEL QUEL (aucun resampling, cf. docstring de
    module) — lève ValueError avec un message qui dit explicitement quoi
    corriger si le format ne convient pas (pas d'exception wave.Error brute,
    peu exploitable pour quelqu'un en pleine campagne de mesures)."""
    with wave.open(path, "rb") as wav_file:
        channels = wav_file.getnchannels()
        sampwidth = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        pcm = wav_file.readframes(wav_file.getnframes())

    if channels != 1 or sampwidth != _BYTES_PER_SAMPLE:
        raise ValueError(
            f"{path} : format non supporté (canaux={channels}, "
            f"largeur_echantillon={sampwidth * 8} bits) — ce rejeu n'effectue "
            "AUCUN resampling (mesurerait autre chose que la vraie chaîne "
            "micro -> VAD, cf. docstring de vision.audio.vad_replay). "
            "Enregistrez en 16 kHz mono 16 bits, cf. "
            "conf/scripts/enregistre-rue.sh."
        )
    return pcm, sample_rate


def _summarize(path: str, events: List[Tuple[float, str]], duration_s: float) -> None:
    """Imprime les événements horodatés puis un résumé par fichier : durée,
    nb de speech_start, durée totale de « parole » détectée, taux de
    déclenchement par minute — les quatre chiffres attendus par la campagne
    D0 (cf. docstring de module)."""
    print(f"\n=== {path} ===")
    for t, kind in events:
        print(f"  t={t:7.3f}s  {kind}")

    starts = [(t, kind) for t, kind in events if kind == "speech_start"]
    ends = [(t, kind) for t, kind in events if kind == "speech_end"]
    # Durée de parole : somme des intervalles [speech_start, speech_end]
    # appariés DANS L'ORDRE — un speech_start sans speech_end correspondant
    # (fichier coupé en pleine parole) n'est pas compté, sa durée est inconnue.
    speech_duration = sum(
        end_t - start_t for (start_t, _), (end_t, _) in zip(starts, ends)
    )
    rate_per_minute = (len(starts) / (duration_s / 60)) if duration_s > 0 else 0.0

    print(f"  Durée du fichier               : {duration_s:.1f} s")
    print(f"  Déclenchements (speech_start)  : {len(starts)}")
    print(f"  Durée totale « parole » détectée : {speech_duration:.1f} s")
    print(f"  Taux de déclenchement          : {rate_per_minute:.2f} / minute")


def main(argv=None) -> int:
    """CLI : `python -m vision.audio.vad_replay fichier.wav [autres.wav...]`.
    Un fichier en échec (format non conforme, absent) n'arrête pas les
    autres — best-effort, cf. philosophie des scripts de campagne D0
    (conf/scripts/*.sh) : on veut le maximum de mesures exploitables, pas un
    outil qui s'arrête au premier wav mal enregistré sur le terrain."""
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(
            "Usage : python -m vision.audio.vad_replay fichier.wav [autres.wav...]",
            file=sys.stderr,
        )
        return 2

    # Import différé de la config (pas en tête de module) : vision_config
    # peut charger conf/secret selon les cas d'usage futurs — un simple test
    # de replay() ne doit pas en dépendre, seul main() (le vrai rejeu CLI) a
    # besoin de config["chat_vad"] (RÈGLE du projet : même VadConfig que la
    # prod, cf. docstring de module).
    from vision.vision_config import config

    exit_code = 0
    for path in argv:
        try:
            pcm, sample_rate = _load_wav_pcm(path)
        except (ValueError, wave.Error, FileNotFoundError) as exc:
            print(f"{path} : {exc}", file=sys.stderr)
            exit_code = 1
            continue

        # Une instance FRAÎCHE d'EnergyVad par fichier : la calibration
        # initiale (1re seconde, cf. VadConfig.calibration_ms) ne doit pas
        # hériter du seuil d'un fichier précédent — chaque enregistrement rue
        # a son propre bruit de fond.
        vad = EnergyVad(config["chat_vad"], frame_ms=FRAME_MS)
        events = replay(pcm, sample_rate, FRAME_MS, vad)
        duration_s = len(pcm) / (sample_rate * _BYTES_PER_SAMPLE)
        _summarize(path, events, duration_s)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
